"""Dify tool for retrieving a specific memory from Mem0 by ID."""

import asyncio
from collections.abc import Generator
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import GET_OPERATION_TIMEOUT
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class GetMemoryTool(Tool):
    """Tool that retrieves a specific memory by its ID."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        memory_id = tool_parameters["memory_id"]

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"
            # Get timeout from parameters, use default if not provided
            timeout = tool_parameters.get("timeout")
            if timeout is None:
                timeout = GET_OPERATION_TIMEOUT
            else:
                try:
                    timeout = float(timeout)
                except (TypeError, ValueError):
                    logger.warning(
                        "Invalid timeout value: %s, using default: %d",
                        timeout,
                        GET_OPERATION_TIMEOUT,
                    )
                    timeout = GET_OPERATION_TIMEOUT
            # Initialize result with default value to ensure it's always defined
            result: dict[str, Any] | None = None
            if async_mode:
                # Note: get_async_local_client() reuses instances when config is unchanged.
                # Resources are managed at plugin lifecycle level via shutdown()
                client = get_async_local_client(self.runtime.credentials)
                # ensure_bg_loop() returns a long-lived, reusable event loop
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(client.get(memory_id), loop)
                try:
                    result = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    # Cancel the future to prevent the background task from hanging
                    future.cancel()
                    logger.exception(
                        "Get operation timed out after %s seconds (%s, memory_id: %s)",
                        timeout,
                        mode_str,
                        memory_id,
                    )
                    # Service degradation: return None to trigger "not found" handling
                    result = None
                except Exception as e:
                    # Catch all other exceptions (network errors, connection errors, DNS failures,
                    # SSL errors, authentication failures, etc.) to ensure service degradation
                    # works for all failure scenarios, not just timeouts
                    logger.exception(
                        "Get operation failed with error: %s (%s, memory_id: %s)",
                        type(e).__name__,
                        mode_str,
                        memory_id,
                    )
                    # Service degradation: return None to trigger "not found" handling
                    result = None
            else:
                # Sync mode: no timeout protection (blocking call)
                # If timeout protection is needed, use async_mode=true
                client = get_local_client(self.runtime.credentials)
                try:
                    result = client.get(memory_id)
                except Exception as e:
                    # Catch all exceptions for sync mode to ensure service degradation
                    logger.exception(
                        "Get operation failed with error: %s (%s, memory_id: %s)",
                        type(e).__name__,
                        mode_str,
                        memory_id,
                    )
                    # Service degradation: return None to trigger "not found" handling
                    result = None

            # Check if memory exists
            if not result or not isinstance(result, dict):
                logger.warning("Memory not found: %s", memory_id)
                error_message = f"Memory not found: {memory_id}"
                yield self.create_json_message(
                    {"status": "ERROR", "messages": error_message, "results": {}})
                yield self.create_text_message(f"Error: {error_message}")
                return
            logger.info(
                "Get memory completed successfully (%s, memory_id: %s, result: %s)",
                mode_str,
                memory_id,
                result,
            )

            yield self.create_json_message({
                "status": "SUCCESS",
                "messages": {"memory_id": memory_id},
                "results": {
                    "id": result.get("id"),
                    "memory": result.get("memory"),
                    "metadata": result.get("metadata", {}),
                    "created_at": result.get("created_at"),
                    "updated_at": result.get("updated_at", ""),
                },
            })

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
            logger.exception("Error getting memory %s", memory_id)
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": {}})
            yield self.create_text_message(f"Failed to get memory: {error_message}")
