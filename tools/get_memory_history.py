"""Dify tool for retrieving memory history from Mem0."""

import asyncio
import time
from collections.abc import Generator
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import READ_OPERATION_TIMEOUT
from utils.helpers import parse_timeout
from utils.logger import get_logger
from utils.mem0_client import (
    QueueOverloadError,
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class GetMemoryHistoryTool(Tool):
    """Tool that retrieves the change history of a specific memory by ID."""

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Get request ID for tracing (not used for memory filtering)
        # Only use run_id if explicitly provided; no auto-generation to avoid fragmented call chains
        request_id = tool_parameters.get("run_id") or "no-run-id"
        start_time = time.time()

        memory_id = tool_parameters["memory_id"]

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"

            # Log operation start
            logger.info(
                "[req:%s] Get memory history started (mode: %s, memory_id: %s)",
                request_id,
                mode_str,
                memory_id,
            )

            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                READ_OPERATION_TIMEOUT,
                logger,
                "history",
            )
            # Initialize results with default value to ensure it's always defined
            results: list[dict[str, Any]] = []
            error_type = None  # Track error type for enhanced result
            if async_mode:
                # Note: get_async_local_client() reuses instances when config is unchanged.
                # Resources are managed at plugin lifecycle level via shutdown()
                client = get_async_local_client(self.runtime.credentials)
                # ensure_bg_loop() returns a long-lived, reusable event loop
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(
                    client.history(memory_id, timeout_s=timeout),
                    loop,
                )
                client.track_bg_task(
                    future,
                    f"get_memory_history(memory_id={memory_id}, req_id={request_id})",
                )
                try:
                    failsafe_timeout = timeout + 1.0
                    results = future.result(timeout=failsafe_timeout)
                except asyncio.TimeoutError:
                    # Timeout already logged by _run_with_semaphore - don't duplicate
                    error_type = "TIMEOUT"
                    results = []
                except FuturesTimeoutError:
                    # Failsafe timeout - this is a second layer of protection
                    future.cancel()
                    elapsed = time.time() - start_time
                    logger.warning(
                        "[req:%s] History operation failsafe timeout after %s seconds "
                        "(mode: %s, memory_id: %s, duration: %.2fs)",
                        request_id,
                        failsafe_timeout,
                        mode_str,
                        memory_id,
                        elapsed,
                    )
                    error_type = "TIMEOUT"
                    results = []
                except QueueOverloadError:
                    # Queue overload already logged by _run_with_semaphore - don't duplicate
                    error_type = "OVERLOAD"
                    results = []
                except Exception as e:
                    # Catch all other exceptions (network errors, connection errors, DNS failures,
                    # SSL errors, authentication failures, etc.) to ensure service degradation
                    # works for all failure scenarios, not just timeouts
                    elapsed = time.time() - start_time
                    logger.exception(
                        "[req:%s] History operation failed with error: %s "
                        "(mode: %s, memory_id: %s, duration: %.2fs)",
                        request_id,
                        type(e).__name__,
                        mode_str,
                        memory_id,
                        elapsed,
                    )
                    error_type = "ERROR"
                    results = []
            else:
                # Sync mode: no timeout protection (blocking call)
                # If timeout protection is needed, use async_mode=true
                client = get_local_client(self.runtime.credentials)
                try:
                    results = client.history(memory_id)
                except Exception as e:
                    # Catch all exceptions for sync mode to ensure service degradation
                    elapsed = time.time() - start_time
                    logger.exception(
                        "[req:%s] History operation failed with error: %s "
                        "(mode: %s, memory_id: %s, duration: %.2fs)",
                        request_id,
                        type(e).__name__,
                        mode_str,
                        memory_id,
                        elapsed,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []

            # JSON output
            history = []
            for h in results or []:
                if not isinstance(h, dict):
                    continue
                history.append(
                    {
                        "memory_id": h.get("memory_id"),
                        "old_memory": h.get("old_memory"),
                        "new_memory": h.get("new_memory"),
                        "event": h.get("event"),
                        "created_at": h.get("created_at"),
                        "updated_at": h.get("updated_at"),
                        "is_deleted": h.get("is_deleted", False),
                    },
                )

            # Log history information (only for sync mode; async mode logs in callback)
            if not async_mode:
                elapsed = time.time() - start_time
                logger.info(
                    "[req:%s] Get memory history completed (mode: %s, memory_id: %s, "
                    "records: %d, duration: %.2fs)",
                    request_id,
                    mode_str,
                    memory_id,
                    len(history),
                    elapsed,
                )

            # Build result with appropriate status and message
            if error_type:
                # Operation failed - return error status with descriptive message
                if error_type == "TIMEOUT":
                    status = "TIMEOUT"
                    messages = "Operation timed out, returning empty results"
                elif error_type == "OVERLOAD":
                    status = "OVERLOAD"
                    messages = "System overloaded, returning empty results"
                else:
                    status = "ERROR"
                    messages = "Operation failed, returning empty results"
            else:
                # Operation succeeded - return success with result summary
                status = "SUCCESS"
                messages = f"Found {len(history)} history records"

            yield self.create_json_message({
                "status": status,
                "messages": messages,
                "results": history,
            })

            # Text output
            text_response = (
                f"Found {len(history)} history records for memory {memory_id}\n\n"
            )
            if history:
                for idx, h in enumerate(history, 1):
                    text_response += (
                        f"{idx}. Memory ID: {h.get('memory_id', '')}\n"
                        f"   Old Memory: {h.get('old_memory', '')}\n"
                        f"   New Memory: {h.get('new_memory', '')}\n"
                        f"   Event: {h.get('event', '')}\n"
                        f"   Created: {h.get('created_at', '')}\n"
                        f"   Updated: {h.get('updated_at', '')}\n"
                        f"   Is Deleted: {h.get('is_deleted', False)}\n\n"
                    )
            yield self.create_text_message(text_response)

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Get memory history failed (memory_id: %s, duration: %.2fs)",
                request_id,
                memory_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(
                f"Failed to get memory history: {error_message}",
            )
