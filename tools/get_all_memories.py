"""Dify tool for retrieving all memories from Mem0 for a specific user."""

import asyncio
import json
from collections.abc import Generator
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import GET_ALL_OPERATION_TIMEOUT
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class GetAllMemoriesTool(Tool):
    """Tool that retrieves all memories for a specific user, with optional filtering."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Validate required user_id
        user_id = tool_parameters.get("user_id")
        if not user_id:
            error_message = "user_id is required"
            logger.error("Get all memories failed: %s", error_message)
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
            yield self.create_text_message(f"Error: {error_message}")
            return

        # Build params
        params: dict[str, Any] = {"user_id": user_id}
        if tool_parameters.get("agent_id"):
            params["agent_id"] = tool_parameters["agent_id"]
        if tool_parameters.get("run_id"):
            params["run_id"] = tool_parameters["run_id"]
        if tool_parameters.get("limit"):
            params["limit"] = tool_parameters.get("limit")

        # Parse filters if provided (JSON string)
        filters_str = tool_parameters.get("filters")
        if filters_str:
            try:
                params["filters"] = json.loads(filters_str)
            except json.JSONDecodeError:
                error_message = "Invalid JSON format for filters"
                logger.exception("Get all memories failed: %s", error_message)
                yield self.create_json_message(
                    {"status": "ERROR", "messages": error_message, "results": []})
                yield self.create_text_message(f"Error: {error_message}")
                return

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"
            # Get timeout from parameters, use default if not provided
            timeout = tool_parameters.get("timeout")
            if timeout is None:
                timeout = GET_ALL_OPERATION_TIMEOUT
            else:
                try:
                    timeout = float(timeout)
                except (TypeError, ValueError):
                    logger.warning(
                        "Invalid timeout value: %s, using default: %d",
                        timeout,
                        GET_ALL_OPERATION_TIMEOUT,
                    )
                    timeout = GET_ALL_OPERATION_TIMEOUT
            # Initialize results with default value to ensure it's always defined
            results: list[dict[str, Any]] = []
            if async_mode:
                # Note: get_async_local_client() reuses instances when config is unchanged.
                # Resources are managed at plugin lifecycle level via shutdown()
                client = get_async_local_client(self.runtime.credentials)
                # ensure_bg_loop() returns a long-lived, reusable event loop
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(client.get_all(params), loop)
                try:
                    results = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    # Cancel the future to prevent the background task from hanging
                    future.cancel()
                    logger.exception(
                        "Get all operation timed out after %s seconds (%s, user_id: %s)",
                        timeout,
                        mode_str,
                        user_id,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []
                except Exception as e:
                    # Catch all other exceptions (network errors, connection errors, DNS failures,
                    # SSL errors, authentication failures, etc.) to ensure service degradation
                    # works for all failure scenarios, not just timeouts
                    logger.exception(
                        "Get all operation failed with error: %s (%s, user_id: %s)",
                        type(e).__name__,
                        mode_str,
                        user_id,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []
            else:
                # Sync mode: no timeout protection (blocking call)
                # If timeout protection is needed, use async_mode=true
                client = get_local_client(self.runtime.credentials)
                try:
                    results = client.get_all(params)
                except Exception as e:
                    # Catch all exceptions for sync mode to ensure service degradation
                    logger.exception(
                        "Get all operation failed with error: %s (%s, user_id: %s)",
                        type(e).__name__,
                        mode_str,
                        user_id,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []
            logger.info(
                "Get all memories completed (%s, found %d results, user_id: %s)",
                mode_str,
                len(results),
                user_id,
            )

            # JSON output
            memories = []
            for r in results or []:
                if not isinstance(r, dict):
                    continue
                memories.append({
                    "id": r.get("id"),
                    "memory": r.get("memory"),
                    "metadata": r.get("metadata", {}),
                    "created_at": r.get("created_at"),
                    "updated_at": r.get("updated_at", ""),
                })

            yield self.create_json_message({
                "status": "SUCCESS",
                "messages": params,
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
            logger.exception("Error getting all memories for user_id: %s", user_id)
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
            yield self.create_text_message(f"Failed to get memories: {error_message}")
