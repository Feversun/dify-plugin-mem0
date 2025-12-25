"""Client adapter for Mem0 local mode only."""

from __future__ import annotations

import asyncio
import concurrent.futures
import contextlib
import hashlib
import json
import threading
import time
from typing import TYPE_CHECKING, Any, ClassVar, TypeVar

from mem0 import AsyncMemory, Memory

from .config_builder import build_local_mem0_config, get_int_credential
from .constants import (
    ADD_SKIP_RESULT,
    CUSTOM_PROMPT,
    MAX_CONCURRENT_MEMORY_OPERATIONS,
    MAX_PENDING_TASKS_MULTIPLIER,
    READ_OPERATION_TIMEOUT,
    WRITE_OPERATION_TIMEOUT,
)
from .logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

T = TypeVar("T")


class QueueOverloadError(Exception):
    """Raised when the background task queue is overloaded."""


def _get_config_hash(credentials: dict[str, Any]) -> str:
    """Generate a hash from credentials for cache key.

    This function creates a hash of the credentials to detect configuration changes.
    The hash is used only for in-memory comparison and is never logged or included
    in exception messages to avoid exposing sensitive information.

    Security notes:
    - Uses SHA256 (one-way hash) - credentials cannot be recovered from the hash
    - Hash value is only stored in memory, never logged or printed
    - Hash includes all credential fields (including sensitive ones like api_key,
      password, token) but the hash itself is safe to use for comparison

    Args:
        credentials: Configuration dictionary (may contain sensitive fields like
            api_key, password, token, etc.).

    Returns:
        str: SHA256 hash of the serialized credentials (hex digest).

    """
    try:
        cred_str = json.dumps(credentials, sort_keys=True)
        return hashlib.sha256(cred_str.encode()).hexdigest()
    except Exception as e:
        # If serialization fails, log the error and return empty string to disable caching
        logger.exception(
            "Failed to generate config hash from credentials: %s",
            type(e).__name__,
        )
        return ""


# Module-level client instances and locks
_local_client: LocalClient | None = None
_local_client_config_hash: str | None = None
_local_client_lock = threading.Lock()

_async_client: AsyncLocalClient | None = None
_async_client_config_hash: str | None = None
_async_client_lock = threading.Lock()


def _normalize_search_results(results: object) -> list[dict[str, Any]]:
    """Normalize Mem0 search results into a list of dicts."""
    normalized: list[dict[str, Any]] = []
    if not results:
        return normalized

    items = results
    if isinstance(results, dict) and "results" in results:
        items = results["results"]

    for r in items or []:
        if not isinstance(r, dict):
            continue
        normalized.append(
            {
                "id": r.get("id") or r.get("memory_id") or "",
                "memory": r.get("memory") or r.get("text") or "",
                "score": r.get("score") or r.get("similarity", 0.0),
                "metadata": r.get("metadata") or {},
                "created_at": r.get("created_at") or r.get("timestamp") or "",
            },
        )
    return normalized


class LocalClient:
    """Local Mem0 client using configured providers."""

    def __init__(self, credentials: dict[str, Any]) -> None:
        """Initialize the LocalClient.

        Args:
            credentials (dict): Configuration for the LocalClient.

        """
        config = build_local_mem0_config(credentials)
        self.memory = Memory.from_config(config)
        self.use_custom_prompt = True
        self.custom_prompt = CUSTOM_PROMPT
        logger.debug("LocalClient initialized")

    def search(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """Search for memories based on a query.

        Args:
            payload (dict): Search parameters. Supported keys:
                - query (str): Query to search for.
                - user_id (str, optional): ID of the user.
                - agent_id (str, optional): ID of the agent.
                - run_id (str, optional): ID of the run.
                - limit (int, optional): Max number of results.
                - filters (dict, optional): Metadata filters, supporting:
                    * {"key": "value"} (exact match)
                    * {"key": {"eq"/"ne"/"in"/"nin"/"gt"/"gte"/"lt"/"lte"/"contains"/"icontains"}: ...}
                    * {"key": "*"} (wildcard)
                    * {"AND"/"OR"/"NOT": [filters,...]} (logic ops)
                - threshold (float, optional): Minimum score (not used in local mode).

        Returns:
            list[dict]: List of memory search results.

        """  # noqa: E501
        query = payload.get("query", "")
        filters = payload.get("filters")
        limit = payload.get("limit")

        # Normalize limit to int when possible
        try:
            lim = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            lim = None

        # Build kwargs with non-empty args to simplify branching
        kwargs: dict[str, Any] = {}
        if lim is not None:
            kwargs["limit"] = lim
        if isinstance(filters, dict):
            kwargs["filters"] = filters
        else:
            if payload.get("user_id"):
                kwargs["user_id"] = payload.get("user_id")
            if payload.get("agent_id"):
                kwargs["agent_id"] = payload.get("agent_id")
            if payload.get("run_id"):
                kwargs["run_id"] = payload.get("run_id")

        try:
            results = self.memory.search(query, **kwargs)
            normalized = _normalize_search_results(results)
        except Exception:
            logger.exception("Error during memory search")
            raise
        else:
            return normalized

    def add(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Create a new memory.

        Adds new memories scoped to a single session id (e.g. user_id, agent_id, or run_id).
        One of those ids is required.

        Args:
            payload (dict): A dictionary containing all parameters for adding a memory, including:
                - messages (str or list[dict[str, str]]): The message content or list of messages
                  (e.g., [{"role": "user", "content": "Hello"}, ...]) to process and store.
                - user_id (str, optional): ID of the user creating the memory.
                - agent_id (str, optional): ID of the agent creating the memory.
                - run_id (str, optional): ID of the run creating the memory.
                - metadata (dict or str, optional): Metadata to store with the memory.
                  Can be a dict or a JSON string.
                - infer (bool, optional): If True (default), uses LLM to extract key facts
                  and manage memories.
                - memory_type (str, optional): Type of memory. Defaults to conversational or factual.
                  Use "procedural_memory" for procedural type.
                - prompt (str, optional): Custom prompt to use for memory creation.

        Returns:
            dict: Result of the memory addition, typically with items added/updated (in "results"),
            and possibly "relations" if graph store is enabled.

        """  # noqa: E501
        metadata = payload.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = None

        # Build kwargs only with provided fields (ignore app_id in local)
        kwargs: dict[str, Any] = {}
        if payload.get("user_id"):
            kwargs["user_id"] = payload.get("user_id")
        if payload.get("agent_id"):
            kwargs["agent_id"] = payload.get("agent_id")
        if payload.get("run_id"):
            kwargs["run_id"] = payload.get("run_id")
        if metadata is not None:
            kwargs["metadata"] = metadata
        if self.use_custom_prompt:
            kwargs["prompt"] = self.custom_prompt

        # Use messages directly if provided; assume upstream has validated inputs
        messages = payload.get("messages")
        try:
            result = self.memory.add(messages, **kwargs)
        except Exception:
            logger.exception("Error during memory addition")
            raise
        else:
            return result

    def get_all(self, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Get all memories based on user/agent/run identifiers with optional filters.

        Args:
            params (dict): Parameters including:
                - user_id (str, optional): User ID to filter by.
                - agent_id (str, optional): Agent ID to filter by.
                - run_id (str, optional): Run ID to filter by.
                - limit (int, optional): Maximum number of results to return.
                - filters (dict, optional): Advanced metadata filters.

        Returns:
            list[dict]: List of memory objects.

        """
        # Build kwargs with all provided parameters
        kwargs: dict[str, Any] = {}

        # Add entity IDs if provided
        if params.get("user_id"):
            kwargs["user_id"] = params.get("user_id")
        if params.get("agent_id"):
            kwargs["agent_id"] = params.get("agent_id")
        if params.get("run_id"):
            kwargs["run_id"] = params.get("run_id")

        # Add optional parameters
        limit = params.get("limit")
        if limit is not None:
            with contextlib.suppress(TypeError, ValueError):
                kwargs["limit"] = int(limit)

        filters = params.get("filters")
        if isinstance(filters, dict):
            kwargs["filters"] = filters

        # Mem0's get_all always returns {"results": [...]} format
        try:
            result = self.memory.get_all(**kwargs)
            memories = result.get("results", []) if isinstance(result, dict) else []
        except Exception:
            logger.exception("Error during get_all operation")
            raise
        else:
            return memories

    def get(self, memory_id: str) -> dict[str, Any]:
        """Get a single memory by ID.

        Args:
            memory_id (str): The ID of the memory to retrieve.

        Returns:
            dict: Memory object with id, memory, metadata, created_at, updated_at, etc.

        """
        try:
            result = self.memory.get(memory_id)
        except Exception:
            logger.exception("Error retrieving memory %s", memory_id)
            raise
        else:
            return result

    def update(self, memory_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Update a memory by ID.

        Args:
            memory_id (str): ID of the memory to update.
            payload (dict): Dictionary containing new content under the "text" key.

        Returns:
            dict: Success message indicating the memory was updated.

        """
        try:
            result = self.memory.update(memory_id, payload.get("text"))
        except Exception:
            logger.exception("Error updating memory %s", memory_id)
            raise
        else:
            return result

    def delete(self, memory_id: str) -> dict[str, Any]:
        """Delete a memory by ID.

        Args:
            memory_id (str): The ID of the memory to delete.

        Returns:
            dict: Success message, typically {"message": "Memory deleted successfully!"}.

        """
        try:
            result = self.memory.delete(memory_id)
        except Exception:
            logger.exception("Error deleting memory %s", memory_id)
            raise
        else:
            return result

    def delete_all(self, params: dict[str, Any]) -> dict[str, Any]:
        """Delete all memories matching the given filters.

        Args:
            params (dict): Parameters including:
                - user_id (str, optional): User ID to filter by.
                - agent_id (str, optional): Agent ID to filter by.
                - run_id (str, optional): Run ID to filter by.

        Returns:
            dict: Result of the deletion operation.

        """
        try:
            result = self.memory.delete_all(
                user_id=params.get("user_id"),
                agent_id=params.get("agent_id"),
                run_id=params.get("run_id"),
            )
        except Exception:
            logger.exception("Error during delete_all operation")
            raise
        else:
            return result

    def history(self, memory_id: str) -> list[dict[str, Any]]:
        """Get the history of changes for a specific memory.

        Args:
            memory_id (str): The ID of the memory to get history for.

        Returns:
            list[dict]: List of history records with old_memory, new_memory, event, created_at, etc.

        """
        try:
            result = self.memory.history(memory_id)
        except Exception:
            logger.exception("Error retrieving history for memory %s", memory_id)
            raise
        else:
            return result


class AsyncLocalClient:
    """Async local Mem0 client using configured providers."""

    # Class-level tracking of all background tasks submitted to the event loop
    # (includes both read operations that wait for results and write operations
    # that are fire-and-forget). Used for global flow control and monitoring.
    _bg_tasks: ClassVar[set[asyncio.Future]] = set()
    _bg_tasks_lock: ClassVar[threading.Lock] = threading.Lock()

    # Statistics tracking for queue monitoring
    _completed_tasks: ClassVar[int] = 0
    _total_task_duration: ClassVar[float] = 0.0
    _stats_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, credentials: dict[str, Any]) -> None:
        """Initialize the AsyncLocalClient.

        Args:
            credentials (dict): Configuration for the AsyncLocalClient.

        """
        self.config = build_local_mem0_config(credentials)
        self.memory = None
        # Async lock to protect one-time asynchronous initialization.
        self._create_lock = asyncio.Lock()
        # Semaphore to limit the concurrency of memory operations. Users can
        # optionally override the default via provider credentials;
        # if not set or invalid, MAX_CONCURRENT_MEMORY_OPERATIONS from
        # utils/constants.py is used.
        self.max_ops = get_int_credential(
            credentials,
            "max_concurrent_memory_operations",
            MAX_CONCURRENT_MEMORY_OPERATIONS,
        )
        self._semaphore = asyncio.Semaphore(self.max_ops)
        # Toggle whether to use custom prompt
        self.use_custom_prompt = True
        self.custom_prompt = CUSTOM_PROMPT
        logger.debug("AsyncLocalClient initialized")

    @classmethod
    def get_pending_tasks_count(cls) -> int:
        """Get the number of pending background tasks (read + write operations).

        This includes all memory operations submitted to the background event loop:
        - Read operations (search, get, get_all, history): submitted and awaited
        - Write operations (add, update, delete, delete_all): fire-and-forget

        Returns:
            int: Number of pending tasks across all operation types.

        Note:
            Tasks are automatically removed from _bg_tasks when they complete
            via the callback registered in track_bg_task(). This method simply
            returns the current count without additional cleanup.

        """
        with cls._bg_tasks_lock:
            return len(cls._bg_tasks)

    @classmethod
    def get_completed_stats(cls) -> tuple[int, float]:
        """Get and reset completed task statistics for queue monitoring.

        Returns:
            tuple[int, float]: (completed_count, avg_duration_seconds) since last call.
                              Returns (0, 0.0) if no tasks completed.

        Note:
            This method resets the internal counters after reading, so each call
            returns stats for the period since the last call (suitable for periodic
            monitoring).

        """
        with cls._stats_lock:
            completed = cls._completed_tasks
            avg_duration = cls._total_task_duration / completed if completed > 0 else 0.0
            # Reset counters for next monitoring period
            cls._completed_tasks = 0
            cls._total_task_duration = 0.0
        return completed, avg_duration

    @classmethod
    def track_bg_task(cls, future: asyncio.Future, task_name: str = "unknown") -> None:
        """Track a background task and log completion/errors.

        This method tracks all memory operations submitted to the background event loop,
        regardless of whether they are fire-and-forget (write ops) or awaited (read ops).

        Args:
            future: The future object returned by run_coroutine_threadsafe.
            task_name: Name of the task for logging (format: "operation(params, req_id=xxx)").

        """
        start_time = time.time()

        with cls._bg_tasks_lock:
            cls._bg_tasks.add(future)

        def _done_callback(f: asyncio.Future) -> None:
            """Task completion callback for background operations.

            This callback's sole purpose is lifecycle management:
            1. Remove task from tracking set
            2. Update statistics for queue monitoring

            Logging strategy:
            - SUCCESS: No logging (already logged by _run_with_semaphore)
            - TIMEOUT: No logging (already logged by _run_with_semaphore)
            - QUEUE_OVERLOAD: No logging (already logged by _run_with_semaphore)
            - OTHER EXCEPTIONS: No logging here; tool layer logs with business context

            The pass statements are INTENTIONAL to avoid duplicate logging.
            """
            duration = time.time() - start_time

            # Remove from tracking set
            with cls._bg_tasks_lock:
                cls._bg_tasks.discard(f)

            # Update statistics for queue monitoring (regardless of success/failure)
            with cls._stats_lock:
                cls._completed_tasks += 1
                cls._total_task_duration += duration

            # Check task result but avoid duplicate logging
            try:
                f.result()  # This will raise if the coroutine raised
            except (asyncio.CancelledError, concurrent.futures.CancelledError) as e:
                # Cancellation is expected in some flows (e.g. failsafe timeouts)
                # Log at warning level to track task cancellations
                logger.warning(
                    "Background task '%s' was cancelled (duration: %.2fs): %s",
                    task_name,
                    duration,
                    type(e).__name__,
                )
            except Exception as e:
                # All other exceptions (TimeoutError, QueueOverloadError, etc.)
                # are already logged by _run_with_semaphore or tool layer.
                # Log here for completeness and to track duration.
                logger.exception(
                    "Background task '%s' completed with exception (duration: %.2fs): %s",
                    task_name,
                    duration,
                    type(e).__name__,
                )

        future.add_done_callback(_done_callback)

    async def create(self) -> AsyncMemory:
        """Lazily create AsyncMemory once."""
        if self.memory is not None:
            return self.memory
        async with self._create_lock:
            if self.memory is None:
                self.memory = await AsyncMemory.from_config(self.config)
                logger.debug("AsyncMemory instance created")
        return self.memory

    async def aclose(self) -> None:
        """Close and cleanup resources held by AsyncMemory.

        Mem0's resources (PGVector, SQLiteManager, etc.) all implement __del__
        methods that automatically clean up when objects are garbage collected.
        However, for long-running processes, explicit cleanup is recommended.

        This method explicitly closes critical resources (connection pools, database
        connections) and then clears the reference to allow GC to handle the rest.

        Note: Designed to be called from the background event loop via
        `asyncio.run_coroutine_threadsafe()`.

        """
        if self.memory is None:
            return

        logger.debug("Closing AsyncMemory resources")
        try:
            loop = asyncio.get_running_loop()

            # Explicitly close critical resources (connection pools, DB connections)
            # Other resources will be cleaned up by __del__ methods during GC

            # PGVector connection pool
            vs = getattr(self.memory, "vector_store", None)
            if vs and hasattr(vs, "connection_pool") and vs.connection_pool:
                try:
                    pool = vs.connection_pool
                    if hasattr(pool, "close"):
                        await loop.run_in_executor(None, pool.close)
                    elif hasattr(pool, "closeall"):
                        await loop.run_in_executor(None, pool.closeall)
                except Exception:
                    logger.exception("Error closing vector store connection pool")

            # Graph store (Neo4jGraph)
            graph = getattr(self.memory, "graph", None)
            if graph:
                try:
                    if hasattr(graph, "close") and not asyncio.iscoroutinefunction(
                        graph.close,
                    ):
                        await loop.run_in_executor(None, graph.close)
                    elif hasattr(graph, "aclose"):
                        await graph.aclose()
                    elif hasattr(graph, "driver") and hasattr(graph.driver, "close"):
                        await loop.run_in_executor(None, graph.driver.close)
                except Exception:
                    logger.exception("Error closing graph store")

            # SQLite connection
            db = getattr(self.memory, "db", None)
            if db and hasattr(db, "close"):
                try:
                    await loop.run_in_executor(None, db.close)
                except Exception:
                    logger.exception("Error closing database connection")

        except Exception:
            logger.exception("Error during AsyncMemory resource cleanup")
        finally:
            # Clear reference - remaining resources will be cleaned up by __del__ methods
            self.memory = None
            logger.debug("AsyncMemory resources closed")

    # Background event loop (class-level, process-wide)
    _bg_loop: asyncio.AbstractEventLoop | None = None
    _bg_thread: threading.Thread | None = None
    _bg_ready = threading.Event()
    _bg_lock = threading.Lock()

    @classmethod
    def ensure_bg_loop(cls) -> asyncio.AbstractEventLoop:
        """Ensure that a background asyncio event loop is running in a dedicated thread.

        This method provides a long-lived, reusable, process-wide background event loop
        for submitting and running coroutines from synchronous code or from threads that
        do not have a running event loop. The loop is created once and reused for the
        entire plugin lifecycle, ensuring efficient resource usage and avoiding the
        overhead of creating new loops for each operation.

        The event loop runs in a dedicated daemon thread and persists until the plugin
        is shut down via shutdown(). This design ensures:
        - Long lifecycle: Loop exists for the entire plugin runtime
        - Reusability: Same loop instance is returned for all operations
        - Thread safety: Access is guarded by a class-level lock
        - Resource efficiency: No per-operation loop creation overhead

        Returns:
            asyncio.AbstractEventLoop: The long-lived, reusable background event loop object.

        Raises:
            RuntimeError: If the background event loop fails to start.

        """
        with cls._bg_lock:
            # Reuse the existing long-lived loop if already running
            if cls._bg_loop and cls._bg_thread and cls._bg_thread.is_alive():
                logger.debug("Reusing existing long-lived background event loop")
                return cls._bg_loop

            logger.debug("Starting new long-lived background event loop")

            # Define the function that runs in the new background thread
            def _runner() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                cls._bg_loop = loop
                cls._bg_ready.set()
                logger.debug("Background event loop started (long-lived)")
                loop.run_forever()  # Run the event loop forever (long lifecycle)

            # Prepare to start a new background thread
            cls._bg_ready.clear()
            t = threading.Thread(target=_runner, name="mem0-bg-loop", daemon=True)
            t.start()
            cls._bg_thread = t
            cls._bg_ready.wait()  # Wait until the loop is ready

            loop = cls._bg_loop
            if loop is None:
                msg = "Background event loop failed to start"
                logger.error(msg)
                raise RuntimeError(msg)
            logger.debug("Background event loop ready (long-lived, reusable)")
            return loop

    @classmethod
    def shutdown(cls, timeout: float = 3.0) -> None:
        """Best-effort graceful shutdown of the background event loop.

        - Attempts to wait up to `timeout` seconds for pending tasks to finish.
        - Stops the loop and joins the background thread (best-effort).
        - Safe to call multiple times.
        """
        loop = cls._bg_loop
        thread = cls._bg_thread
        if loop is None:
            logger.debug("No background event loop to shutdown")
            return

        logger.debug("Shutting down background event loop (timeout: %s)", timeout)

        async def _drain_tasks(t: float) -> None:
            # Exclude the current task and wait for others (best-effort)
            with contextlib.suppress(Exception):
                pending = [
                    tsk
                    for tsk in asyncio.all_tasks()
                    if tsk is not asyncio.current_task()
                ]
                if pending:
                    logger.debug(
                        "Waiting for %d pending tasks to complete",
                        len(pending),
                    )
                    await asyncio.wait(pending, timeout=t)

        fut = asyncio.run_coroutine_threadsafe(_drain_tasks(timeout), loop)
        with contextlib.suppress(Exception):
            fut.result(timeout=timeout + 1.0)
        with contextlib.suppress(Exception):
            loop.call_soon_threadsafe(loop.stop)
        if thread and thread.is_alive():
            with contextlib.suppress(Exception):
                thread.join(timeout=timeout)
        # Clear references
        cls._bg_loop = None
        cls._bg_thread = None
        logger.debug("Background event loop shutdown completed")

    async def search(
        self,
        payload: dict[str, Any],
        timeout_s: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search for memories based on a query.

        Args:
            payload (dict): Search parameters. Supported keys:
                - query (str): Query to search for.
                - user_id (str, optional): ID of the user.
                - agent_id (str, optional): ID of the agent.
                - run_id (str, optional): ID of the run.
                - limit (int, optional): Max number of results.
                - filters (dict, optional): Metadata filters, supporting:
                    * {"key": "value"} (exact match)
                    * {"key": {"eq"/"ne"/"in"/"nin"/"gt"/"gte"/"lt"/"lte"/"contains"/"icontains"}: ...}
                    * {"key": "*"} (wildcard)
                    * {"AND"/"OR"/"NOT": [filters,...]} (logic ops)
                - threshold (float, optional): Minimum score (not used in local mode).
            timeout_s (int | None, optional): Timeout seconds for this read operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to READ_OPERATION_TIMEOUT.

        Returns:
            list[dict]: List of memory search results.

        """  # noqa: E501
        query = payload.get("query", "")
        filters = payload.get("filters")
        limit = payload.get("limit")

        # Normalize limit to int when possible
        lim: int | None
        try:
            lim = int(limit) if limit is not None else None
        except (TypeError, ValueError):
            lim = None

        # Build kwargs with non-empty args to simplify branching
        kwargs: dict[str, Any] = {}
        if lim is not None:
            kwargs["limit"] = lim
        if isinstance(filters, dict):
            kwargs["filters"] = filters
        else:
            if payload.get("user_id"):
                kwargs["user_id"] = payload.get("user_id")
            if payload.get("agent_id"):
                kwargs["agent_id"] = payload.get("agent_id")
            if payload.get("run_id"):
                kwargs["run_id"] = payload.get("run_id")

        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=READ_OPERATION_TIMEOUT,
        )

        async def _call() -> object:
            return await self.memory.search(query, **kwargs)

        results = await self._run_with_semaphore(
            "search",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Read operations check queue
        )
        return _normalize_search_results(results)

    async def add(
        self,
        payload: dict[str, Any],
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Create a new memory.

        Adds new memories scoped to a single session id (e.g. user_id, agent_id, or run_id).
        One of those ids is required.

        Args:
            payload (dict): A dictionary containing all parameters for adding a memory, including:
                - messages (str or list[dict[str, str]]): The message content or list of messages
                  (e.g., [{"role": "user", "content": "Hello"}, ...]) to process and store.
                - user_id (str, optional): ID of the user creating the memory.
                - agent_id (str, optional): ID of the agent creating the memory.
                - run_id (str, optional): ID of the run creating the memory.
                - metadata (dict or str, optional): Metadata to store with the memory.
                  Can be a dict or a JSON string.
                - infer (bool, optional): If True (default), uses LLM to extract key facts
                  and manage memories.
                - memory_type (str, optional): Type of memory. Defaults to conversational or factual.
                  Use "procedural_memory" for procedural type.
                - prompt (str, optional): Custom prompt to use for memory creation.
            timeout_s (int | None, optional): Timeout seconds for this write operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to WRITE_OPERATION_TIMEOUT.

        Returns:
            dict: Result of the memory addition, typically with items added/updated (in "results"),
            and possibly "relations" if graph store is enabled.

        """  # noqa: E501
        await self.create()
        metadata = payload.get("metadata")
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = None

        kwargs: dict[str, Any] = {}
        if payload.get("user_id"):
            kwargs["user_id"] = payload.get("user_id")
        if payload.get("agent_id"):
            kwargs["agent_id"] = payload.get("agent_id")
        if payload.get("run_id"):
            kwargs["run_id"] = payload.get("run_id")
        if metadata is not None:
            kwargs["metadata"] = metadata
        if self.use_custom_prompt:
            kwargs["prompt"] = self.custom_prompt

        messages = payload.get("messages")
        # Skip add when messages is empty/blank, return response aligned with mem0 add result shape
        if (
            messages is None
            or (isinstance(messages, str) and messages.strip() == "")
            or (isinstance(messages, (list, tuple)) and len(messages) == 0)
        ):
            return ADD_SKIP_RESULT

        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=WRITE_OPERATION_TIMEOUT,
        )

        async def _call() -> object:
            return await self.memory.add(messages, **kwargs)

        return await self._run_with_semaphore(
            "add",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Write operations check queue
        )

    async def get_all(
        self,
        params: dict[str, Any],
        timeout_s: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get all memories based on user/agent/run identifiers with optional filters.

        Args:
            params (dict): Parameters including:
                - user_id (str, optional): User ID to filter by.
                - agent_id (str, optional): Agent ID to filter by.
                - run_id (str, optional): Run ID to filter by.
                - limit (int, optional): Maximum number of results to return.
                - filters (dict, optional): Advanced metadata filters.
            timeout_s (int | None, optional): Timeout seconds for this read operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to READ_OPERATION_TIMEOUT.

        Returns:
            list[dict]: List of memory objects.

        """
        # Build kwargs with all provided parameters
        kwargs: dict[str, Any] = {}

        # Add entity IDs if provided
        if params.get("user_id"):
            kwargs["user_id"] = params.get("user_id")
        if params.get("agent_id"):
            kwargs["agent_id"] = params.get("agent_id")
        if params.get("run_id"):
            kwargs["run_id"] = params.get("run_id")

        # Add optional parameters
        limit = params.get("limit")
        if limit is not None:
            with contextlib.suppress(TypeError, ValueError):
                kwargs["limit"] = int(limit)

        filters = params.get("filters")
        if isinstance(filters, dict):
            kwargs["filters"] = filters

        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=READ_OPERATION_TIMEOUT,
        )
        async def _call() -> dict[str, Any]:
            return await self.memory.get_all(**kwargs)

        # Mem0's get_all always returns {"results": [...]} format
        result = await self._run_with_semaphore(
            "get_all",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Read operations check queue
        )
        return result.get("results", []) if isinstance(result, dict) else []

    async def get(
        self,
        memory_id: str,
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Get a single memory by ID.

        Args:
            memory_id (str): The ID of the memory to retrieve.
            timeout_s (int | None, optional): Timeout seconds for this read operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to READ_OPERATION_TIMEOUT.

        Returns:
            dict: Memory object with id, memory, metadata, created_at, updated_at, etc.

        """
        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=READ_OPERATION_TIMEOUT,
        )

        async def _call() -> dict[str, Any]:
            return await self.memory.get(memory_id)

        return await self._run_with_semaphore(
            "get",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Read operations check queue
        )

    async def update(
        self,
        memory_id: str,
        payload: dict[str, Any],
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Update a memory by ID.

        Args:
            memory_id (str): ID of the memory to update.
            payload (dict): Dictionary containing new content under the "text" key.
            timeout_s (int | None, optional): Timeout seconds for this write operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to WRITE_OPERATION_TIMEOUT.

        Returns:
            dict: Success message indicating the memory was updated.

        """
        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=WRITE_OPERATION_TIMEOUT,
        )

        async def _call() -> dict[str, Any]:
            return await self.memory.update(memory_id, payload.get("text"))

        return await self._run_with_semaphore(
            "update",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Write operations check queue
        )

    async def delete(
        self,
        memory_id: str,
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Delete a memory by ID.

        Args:
            memory_id (str): The ID of the memory to delete.
            timeout_s (int | None, optional): Timeout seconds for this write operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to WRITE_OPERATION_TIMEOUT.

        Returns:
            dict: Success message, typically {"message": "Memory deleted successfully!"}.

        """
        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=WRITE_OPERATION_TIMEOUT,
        )

        async def _call() -> dict[str, Any]:
            return await self.memory.delete(memory_id)

        return await self._run_with_semaphore(
            "delete",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Write operations check queue
        )

    async def delete_all(
        self,
        params: dict[str, Any],
        timeout_s: int | None = None,
    ) -> dict[str, Any]:
        """Delete all memories matching the given filters.

        Args:
            params (dict): Parameters including:
                - user_id (str, optional): User ID to filter by.
                - agent_id (str, optional): Agent ID to filter by.
                - run_id (str, optional): Run ID to filter by.
            timeout_s (int | None, optional): Timeout seconds for this write operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to WRITE_OPERATION_TIMEOUT.

        Returns:
            dict: Result of the deletion operation.

        """
        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=WRITE_OPERATION_TIMEOUT,
        )

        async def _call() -> dict[str, Any]:
            return await self.memory.delete_all(
                user_id=params.get("user_id"),
                agent_id=params.get("agent_id"),
                run_id=params.get("run_id"),
            )

        return await self._run_with_semaphore(
            "delete_all",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Write operations check queue
        )

    async def history(
        self,
        memory_id: str,
        timeout_s: int | None = None,
    ) -> list[dict[str, Any]]:
        """Get the history of changes for a specific memory.

        Args:
            memory_id (str): The ID of the memory to get history for.
            timeout_s (int | None, optional): Timeout seconds for this read operation.
                Timeout covers create() + waiting for semaphore + actual Mem0 operation.
                If None, defaults to READ_OPERATION_TIMEOUT.

        Returns:
            list[dict]: List of history records with old_memory, new_memory, event, created_at, etc.

        """
        timeout = self._get_operation_timeout_s(
            timeout_s=timeout_s,
            default_s=READ_OPERATION_TIMEOUT,
        )

        async def _call() -> list[dict[str, Any]]:
            return await self.memory.history(memory_id)

        return await self._run_with_semaphore(
            "history",
            _call,
            timeout_s=timeout,
            check_queue=True,  # Read operations check queue
        )

    def _get_operation_timeout_s(
        self,
        timeout_s: int | None,
        default_s: int,
    ) -> int:
        """Resolve a safe timeout for async operations (read or write).

        Args:
            timeout_s: Optional timeout in seconds (int). If None, uses default_s.
            default_s: Default timeout in seconds (int).

        Returns:
            int: Valid timeout value in seconds.

        """
        if timeout_s is None:
            return default_s
        # Ensure is valid non-negative integer
        try:
            int_value = int(timeout_s)
        except (TypeError, ValueError):
            return default_s
        if int_value < 0:
            return default_s
        return int_value

    async def _run_with_semaphore(
        self,
        op_name: str,
        fn: Callable[[], Awaitable[T]],
        timeout_s: int | None = None,
        *,
        check_queue: bool = True,
    ) -> T:
        """Unified method to run async operations with queue check, semaphore, and timeout.

        This method provides:
        1. Optional queue overload check before execution
        2. Semaphore-controlled concurrency
        3. Detailed timing logs (wait time + execution time)
        4. Optional timeout protection

        Logging strategy:
        - Queue overload: Logged here with technical details
        - Timeout: Logged here with technical details
        - Tool layer should NOT duplicate these logs, but should enhance return results
          with error context for upstream applications

        Args:
            op_name: Operation name for logging (e.g., "search", "add").
            fn: Async function to execute within semaphore.
            timeout_s: Optional timeout in seconds (int). If None, no timeout limit.
            check_queue: Whether to check queue length before execution.

        Returns:
            Result from fn().

        Raises:
            QueueOverloadError: If queue is overloaded and check_queue is True.
            asyncio.TimeoutError: If operation exceeds timeout_s.

        """
        # 1. Queue overload check (optional, for both read and write operations)
        # Log at first occurrence - tool layer should NOT duplicate this log
        if check_queue:
            pending = self.get_pending_tasks_count()
            if pending > self.max_ops * MAX_PENDING_TASKS_MULTIPLIER:
                logger.warning(
                    "%s operation rejected: queue overloaded (%d pending tasks, max: %d)",
                    op_name.capitalize(),
                    pending,
                    self.max_ops * MAX_PENDING_TASKS_MULTIPLIER,
                )
                error_msg = (
                    f"Queue overloaded: {pending} pending tasks "
                    f"(max: {self.max_ops * MAX_PENDING_TASKS_MULTIPLIER})"
                )
                raise QueueOverloadError(error_msg)

        # 2. Execute operation with timing and semaphore control
        async def _inner() -> T:
            await self.create()

            # Record semaphore wait time
            wait_start = time.time()
            async with self._semaphore:
                wait_time = time.time() - wait_start

                # Record Mem0 execution time
                exec_start = time.time()
                result = await fn()
                exec_time = time.time() - exec_start

                # Log timing breakdown
                logger.info(
                    "%s operation timing: wait=%.3fs, exec=%.3fs, total=%.3fs",
                    op_name.capitalize(),
                    wait_time,
                    exec_time,
                    wait_time + exec_time,
                )

                return result

        # 3. Apply timeout protection if specified
        # Log timeout at first occurrence - tool layer should NOT duplicate this log
        if timeout_s is not None:
            try:
                return await asyncio.wait_for(_inner(), timeout=timeout_s)
            except asyncio.TimeoutError:
                logger.warning(
                    "%s operation timed out after %ds (asyncio.TimeoutError)",
                    op_name.capitalize(),
                    timeout_s,
                )
                raise
        else:
            # No timeout limit
            return await _inner()


def _cleanup_async_client(client: AsyncLocalClient, context: str = "cleanup") -> None:
    """Cleanup AsyncLocalClient resources via background event loop.

    This helper function provides a unified way to cleanup AsyncLocalClient
    instances, avoiding code duplication.

    Args:
        client: The AsyncLocalClient instance to cleanup.
        context: Context string for logging (e.g., "replacement", "reset").

    """
    if client is None:
        return

    loop = AsyncLocalClient._bg_loop  # noqa: SLF001
    if loop is not None and loop.is_running():
        try:
            fut = asyncio.run_coroutine_threadsafe(client.aclose(), loop)
            # Waiting for cleanup to complete
            fut.result(timeout=2.0)
        except Exception:
            logger.exception(
                "Failed to cleanup async client resources during %s",
                context,
            )
    else:
        logger.debug(
            "No background loop available for async cleanup during %s",
            context,
        )


def get_local_client(credentials: dict[str, Any]) -> LocalClient:
    """Get or create LocalClient instance, recreating if config changed.

    This function provides a module-level factory for LocalClient instances,
    ensuring resource reuse while supporting configuration changes.

    All reads and writes to module-level variables are protected by
    threading.Lock to ensure thread safety in multi-threaded environments.

    Args:
        credentials: Configuration dictionary for the LocalClient.

    Returns:
        LocalClient: The LocalClient instance, reused if config unchanged.

    """
    global _local_client, _local_client_config_hash  # noqa: PLW0603

    config_hash = _get_config_hash(credentials)

    # All reads and writes are protected by lock to ensure thread safety
    with _local_client_lock:
        # If config changed or client doesn't exist, create new instance
        if _local_client is None or _local_client_config_hash != config_hash:
            # LocalClient resources (PGVector, SQLiteManager) have __del__ methods
            # that will be called during GC when the old reference is overwritten.
            # LocalClient doesn't have a close() method, so we rely on __del__
            # methods in mem0 resources for cleanup.
            if _local_client is not None:
                logger.debug("Replacing LocalClient due to config change")
            _local_client = LocalClient(credentials)
            _local_client_config_hash = config_hash
        return _local_client


def get_async_local_client(credentials: dict[str, Any]) -> AsyncLocalClient:
    """Get or create AsyncLocalClient instance, recreating if config changed.

    This function provides a module-level factory for AsyncLocalClient instances,
    ensuring resource reuse while supporting configuration changes.

    All reads and writes to module-level variables are protected by
    threading.Lock to ensure thread safety in multi-threaded environments.

    Args:
        credentials: Configuration dictionary for the AsyncLocalClient.

    Returns:
        AsyncLocalClient: The AsyncLocalClient instance, reused if config unchanged.

    """
    global _async_client, _async_client_config_hash  # noqa: PLW0603

    config_hash = _get_config_hash(credentials)

    # All reads and writes are protected by lock to ensure thread safety
    with _async_client_lock:
        # If config changed or client doesn't exist, create new instance
        if _async_client is None or _async_client_config_hash != config_hash:
            # Cleanup old client before creating new one to prevent resource leaks
            old_client = _async_client
            if old_client is not None:
                logger.debug(
                    "Replacing AsyncLocalClient due to config change, cleaning up old instance",
                )
                _cleanup_async_client(old_client, context="replacement")
            _async_client = AsyncLocalClient(credentials)
            _async_client_config_hash = config_hash

            # Initialize queue monitor on first client creation
            _init_queue_monitor(credentials)
        return _async_client


def _init_queue_monitor(_credentials: dict[str, Any]) -> None:
    """Initialize queue monitor with default interval.

    Args:
        _credentials: Configuration dictionary (unused, kept for compatibility).

    Note:
        queue_monitor_interval configuration has been removed.
        Queue monitor now uses a fixed default interval of 300 seconds (5 minutes).

    """
    try:
        # Use fixed default interval (300 seconds = 5 minutes)
        # queue_monitor_interval configuration has been removed from credentials
        interval = 300

        if interval > 0:
            from .queue_monitor import QueueMonitor

            monitor = QueueMonitor.get_instance(interval)
            monitor.start(
                AsyncLocalClient.get_pending_tasks_count,
                AsyncLocalClient.get_completed_stats,
            )
            logger.debug("Queue monitor initialized (interval: %ds)", interval)
        else:
            logger.debug("Queue monitor disabled (interval: 0)")
    except Exception:
        logger.exception("Failed to initialize queue monitor, continuing without it")


def reset_clients() -> None:
    """Reset client instances (useful for testing).

    This function clears the cached client instances, forcing new instances
    to be created on the next call to get_local_client() or get_async_local_client().

    For AsyncLocalClient, this also attempts to cleanup resources (HTTP sessions,
    database connections, etc.) to prevent resource leaks.

    """
    global _local_client, _local_client_config_hash  # noqa: PLW0603
    global _async_client, _async_client_config_hash  # noqa: PLW0603

    with _local_client_lock:
        _local_client = None
        _local_client_config_hash = None

    with _async_client_lock:
        # Cleanup async client resources before resetting
        old_client = _async_client
        if old_client is not None:
            _cleanup_async_client(old_client, context="reset")

        _async_client = None
        _async_client_config_hash = None
