"""Dify tool for retrieving a specific memory from Mem0 by ID."""

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


class GetMemoryTool(Tool):
    """Tool that retrieves a specific memory by its ID."""

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
            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                READ_OPERATION_TIMEOUT,
                logger,
                "get",
            )

            # Log operation start
            logger.info(
                "[req:%s] Get memory started (mode: %s, memory_id: %s)",
                request_id,
                mode_str,
                memory_id,
            )

            # Initialize result and error_type with default values
            # to ensure they're always defined
            result: dict[str, Any] | None = None
            error_type: str | None = None  # Track error type for enhanced result

            if async_mode:
                # Note: get_async_local_client() reuses instances when config is unchanged.
                # Resources are managed at plugin lifecycle level via shutdown()
                client = get_async_local_client(self.runtime.credentials)
                # ensure_bg_loop() returns a long-lived, reusable event loop
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(
                    client.get(memory_id, timeout_s=timeout),
                    loop,
                )
                client.track_bg_task(
                    future,
                    f"get_memory(memory_id={memory_id}, req_id={request_id})",
                )
                try:
                    failsafe_timeout = timeout + 1.0
                    result = future.result(timeout=failsafe_timeout)
                except asyncio.TimeoutError:
                    # Timeout already logged by _run_with_semaphore - don't duplicate
                    # Service degradation: set error type for result enhancement
                    error_type = "TIMEOUT"
                    result = None
                except FuturesTimeoutError:
                    # Failsafe timeout - this is a second layer of protection
                    # Log only at failsafe level (different from asyncio.TimeoutError)
                    future.cancel()
                    elapsed = time.time() - start_time
                    logger.warning(
                        "[req:%s] Get operation failsafe timeout after %s seconds "
                        "(mode: %s, memory_id: %s, duration: %.2fs)",
                        request_id,
                        failsafe_timeout,
                        mode_str,
                        memory_id,
                        elapsed,
                    )
                    error_type = "TIMEOUT"
                    result = None
                except QueueOverloadError:
                    # Queue overload already logged by _run_with_semaphore - don't duplicate
                    # Service degradation: set error type for result enhancement
                    error_type = "OVERLOAD"
                    result = None
                except Exception as e:
                    # Catch all other exceptions (network errors, connection errors,
                    # DNS failures, SSL errors, authentication failures, etc.)
                    # to ensure service degradation works for all failure scenarios
                    elapsed = time.time() - start_time
                    logger.exception(
                        "[req:%s] Get operation failed with error: %s "
                        "(mode: %s, memory_id: %s, duration: %.2fs)",
                        request_id,
                        type(e).__name__,
                        mode_str,
                        memory_id,
                        elapsed,
                    )
                    error_type = "ERROR"
                    result = None
            else:
                # Sync mode: no timeout protection (blocking call)
                # If timeout protection is needed, use async_mode=true
                client = get_local_client(self.runtime.credentials)
                try:
                    result = client.get(memory_id)
                except (ValueError, AttributeError):
                    # Mem0 throws ValueError or AttributeError when memory not found
                    elapsed = time.time() - start_time
                    logger.warning(
                        "[req:%s] Memory not found (memory_id: %s, duration: %.2fs)",
                        request_id,
                        memory_id,
                        elapsed,
                    )
                    error_type = "NOT_FOUND"
                    result = None
                except Exception as e:
                    # Catch all other exceptions for sync mode to ensure
                    # service degradation
                    elapsed = time.time() - start_time
                    logger.exception(
                        "[req:%s] Get operation failed with error: %s "
                        "(mode: %s, memory_id: %s, duration: %.2fs)",
                        request_id,
                        type(e).__name__,
                        mode_str,
                        memory_id,
                        elapsed,
                    )
                    # Unknown error type - use ERROR status
                    error_type = "ERROR"
                    # Service degradation: return None to trigger error handling
                    result = None

            # Check if memory exists or if operation failed
            if not result or not isinstance(result, dict):
                elapsed = time.time() - start_time
                # Provide specific error message based on error type
                if error_type == "TIMEOUT":
                    status = "TIMEOUT"
                    messages = (
                        f"Operation timed out while retrieving memory: {memory_id}"
                    )
                elif error_type == "OVERLOAD":
                    status = "OVERLOAD"
                    messages = (
                        f"System overloaded, unable to retrieve memory: {memory_id}"
                    )
                elif error_type == "NOT_FOUND":
                    status = "NOT_FOUND"
                    messages = f"Memory not found: {memory_id}"
                elif error_type == "ERROR":
                    status = "ERROR"
                    messages = (
                        f"Operation failed while retrieving memory: {memory_id}"
                    )
                else:
                    # No error_type means memory genuinely not found
                    # (None returned from mem0)
                    status = "NOT_FOUND"
                    messages = f"Memory not found: {memory_id}"

                logger.warning(
                    "[req:%s] Get memory result: %s (memory_id: %s, duration: %.2fs)",
                    request_id,
                    status,
                    memory_id,
                    elapsed,
                )
                yield self.create_json_message(
                    {
                        "status": status,
                        "messages": messages,
                        "results": {},
                    },
                )
                yield self.create_text_message(f"Error: {messages}")
                return

            # Log completion (only for sync mode; async mode logs in callback)
            if not async_mode:
                elapsed = time.time() - start_time
                logger.info(
                    "[req:%s] Get memory completed (mode: %s, memory_id: %s, duration: %.2fs)",
                    request_id,
                    mode_str,
                    memory_id,
                    elapsed,
                )

            yield self.create_json_message(
                {
                    "status": "SUCCESS",
                    "messages": "Memory retrieved successfully",
                    "results": {
                        "id": result.get("id"),
                        "memory": result.get("memory"),
                        "metadata": result.get("metadata", {}),
                        "created_at": result.get("created_at"),
                        "updated_at": result.get("updated_at", ""),
                    },
                },
            )

            text_response = (
                f"Memory Details:\n\n"
                f"ID: {result.get('id', '')}\n"
                f"Memory: {result.get('memory', '')}\n"
                f"Metadata: {result.get('metadata', {})}\n"
                f"Created: {result.get('created_at', '')}\n"
                f"Updated: {result.get('updated_at', '')}\n"
            )

            yield self.create_text_message(text_response)

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Get memory failed (memory_id: %s, duration: %.2fs)",
                request_id,
                memory_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": {}},
            )
            yield self.create_text_message(f"Failed to get memory: {error_message}")
