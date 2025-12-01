"""Dify tool for retrieving memory history from Mem0."""

import asyncio
from collections.abc import Generator
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import HISTORY_OPERATION_TIMEOUT
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class GetMemoryHistoryTool(Tool):
    """Tool that retrieves the change history of a specific memory by ID."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        memory_id = tool_parameters["memory_id"]

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"
            # Get timeout from parameters, use default if not provided
            timeout = tool_parameters.get("timeout")
            if timeout is None:
                timeout = HISTORY_OPERATION_TIMEOUT
            else:
                try:
                    timeout = float(timeout)
                except (TypeError, ValueError):
                    logger.warning(
                        "Invalid timeout value: %s, using default: %d",
                        timeout,
                        HISTORY_OPERATION_TIMEOUT,
                    )
                    timeout = HISTORY_OPERATION_TIMEOUT
            # Initialize results with default value to ensure it's always defined
            results: list[dict[str, Any]] = []
            if async_mode:
                # Note: get_async_local_client() reuses instances when config is unchanged.
                # Resources are managed at plugin lifecycle level via shutdown()
                client = get_async_local_client(self.runtime.credentials)
                # ensure_bg_loop() returns a long-lived, reusable event loop
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(client.history(memory_id), loop)
                try:
                    results = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    # Cancel the future to prevent the background task from hanging
                    future.cancel()
                    logger.exception(
                        "History operation timed out after %s seconds (%s, memory_id: %s)",
                        timeout,
                        mode_str,
                        memory_id,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []
                except Exception as e:
                    # Catch all other exceptions (network errors, connection errors, DNS failures,
                    # SSL errors, authentication failures, etc.) to ensure service degradation
                    # works for all failure scenarios, not just timeouts
                    logger.exception(
                        "History operation failed with error: %s (%s, memory_id: %s)",
                        type(e).__name__,
                        mode_str,
                        memory_id,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []
            else:
                # Sync mode: no timeout protection (blocking call)
                # If timeout protection is needed, use async_mode=true
                client = get_local_client(self.runtime.credentials)
                try:
                    results = client.history(memory_id)
                except Exception as e:
                    # Catch all exceptions for sync mode to ensure service degradation
                    logger.exception(
                        "History operation failed with error: %s (%s, memory_id: %s)",
                        type(e).__name__,
                        mode_str,
                        memory_id,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []

            # JSON output
            history = []
            for h in results or []:
                if not isinstance(h, dict):
                    continue
                history.append({
                    "memory_id": h.get("memory_id"),
                    "old_memory": h.get("old_memory"),
                    "new_memory": h.get("new_memory"),
                    "event": h.get("event"),
                    "created_at": h.get("created_at"),
                    "updated_at": h.get("updated_at"),
                    "is_deleted": h.get("is_deleted", False),
                })

            # Log history information
            logger.info(
                "Get memory history completed (%s, memory_id: %s, history: %s)",
                mode_str,
                memory_id,
                history,
            )

            yield self.create_json_message({
                "status": "SUCCESS",
                "messages": {"memory_id": memory_id},
                "results": history,
            })

            # Text output
            text_response = f"Found {len(history)} history records for memory {memory_id}\n\n"
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
            logger.exception("Error getting memory history for %s", memory_id)
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
            yield self.create_text_message(f"Failed to get memory history: {error_message}")
