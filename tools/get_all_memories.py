"""Dify tool for retrieving all memories from Mem0 for a specific user."""

import asyncio
import json
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


class GetAllMemoriesTool(Tool):
    """Tool that retrieves all memories for a specific user, with optional filtering."""

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Get request ID for tracing (not used for memory filtering)
        # Only use run_id if explicitly provided; no auto-generation to avoid fragmented call chains
        request_id = tool_parameters.get("run_id") or "no-run-id"
        start_time = time.time()

        # Validate required user_id
        user_id = tool_parameters.get("user_id")
        if not user_id:
            error_message = "user_id is required"
            logger.error("[req:%s] Get all memories failed: %s", request_id, error_message)
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Error: {error_message}")
            return

        # Build params (NOTE: run_id is NOT included - it's only used for request tracing)
        params: dict[str, Any] = {"user_id": user_id}
        if tool_parameters.get("agent_id"):
            params["agent_id"] = tool_parameters["agent_id"]
        if tool_parameters.get("limit"):
            params["limit"] = tool_parameters.get("limit")

        # Parse filters if provided (JSON string)
        filters_str = tool_parameters.get("filters")
        if filters_str:
            try:
                params["filters"] = json.loads(filters_str)
            except json.JSONDecodeError:
                error_message = "Invalid JSON format for filters"
                logger.exception("[req:%s] Get all memories failed: %s", request_id, error_message)
                yield self.create_json_message(
                    {"status": "ERROR", "messages": error_message, "results": []},
                )
                yield self.create_text_message(f"Error: {error_message}")
                return

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"

            # Log operation start
            logger.info(
                "[req:%s] Get all memories started (mode: %s, user_id: %s)",
                request_id,
                mode_str,
                user_id,
            )

            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                READ_OPERATION_TIMEOUT,
                logger,
                "get_all",
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
                    client.get_all(params, timeout_s=timeout),
                    loop,
                )
                client.track_bg_task(
                    future,
                    f"get_all_memories(user_id={user_id}, req_id={request_id})",
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
                        "[req:%s] Get all operation failsafe timeout after %s seconds "
                        "(mode: %s, user_id: %s, duration: %.2fs)",
                        request_id,
                        failsafe_timeout,
                        mode_str,
                        user_id,
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
                        "[req:%s] Get all operation failed with error: %s "
                        "(mode: %s, user_id: %s, duration: %.2fs)",
                        request_id,
                        type(e).__name__,
                        mode_str,
                        user_id,
                        elapsed,
                    )
                    error_type = "ERROR"
                    results = []
            else:
                # Sync mode: no timeout protection (blocking call)
                # If timeout protection is needed, use async_mode=true
                client = get_local_client(self.runtime.credentials)
                try:
                    results = client.get_all(params)
                except Exception as e:
                    # Catch all exceptions for sync mode to ensure service degradation
                    elapsed = time.time() - start_time
                    logger.exception(
                        "[req:%s] Get all operation failed with error: %s "
                        "(mode: %s, user_id: %s, duration: %.2fs)",
                        request_id,
                        type(e).__name__,
                        mode_str,
                        user_id,
                        elapsed,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []

            # Log completion (only for sync mode; async mode logs in callback)
            if not async_mode:
                elapsed = time.time() - start_time
                logger.info(
                    "[req:%s] Get all memories completed (mode: %s, found %d memories, "
                    "user_id: %s, duration: %.2fs)",
                    request_id,
                    mode_str,
                    len(results),
                    user_id,
                    elapsed,
                )

            # JSON output
            memories = []
            for r in results or []:
                if not isinstance(r, dict):
                    continue
                memories.append(
                    {
                        "id": r.get("id"),
                        "memory": r.get("memory"),
                        "metadata": r.get("metadata", {}),
                        "created_at": r.get("created_at"),
                        "updated_at": r.get("updated_at", ""),
                    },
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
                messages = f"Found {len(memories)} memories"

            yield self.create_json_message({
                "status": status,
                "messages": messages,
                "results": memories,
            })

            # Text output
            text_response = f"Found {len(memories)} memories\n\n"
            if memories:
                for idx, r in enumerate(memories, 1):
                    text_response += (
                        f"{idx}. ID: {r.get('id', '')}\n"
                        f"   Memory: {r.get('memory', '')}\n"
                        f"   Metadata: {r.get('metadata', {})}\n"
                        f"   Created: {r.get('created_at', '')}\n"
                        f"   Updated: {r.get('updated_at', '')}\n\n"
                    )
            yield self.create_text_message(text_response)

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Get all memories failed (user_id: %s, duration: %.2fs)",
                request_id,
                user_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to get memories: {error_message}")
