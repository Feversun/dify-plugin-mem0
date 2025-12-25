"""Dify tool for deleting all memories from Mem0 for a specific user."""

import asyncio
import time
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import DELETE_ALL_ACCEPT_RESULT, WRITE_OPERATION_TIMEOUT
from utils.helpers import parse_timeout
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class DeleteAllMemoriesTool(Tool):
    """Tool that deletes all memories for a specific user, with optional filtering."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Get request ID for tracing (not used for memory filtering)
        # Only use run_id if explicitly provided; no auto-generation to avoid fragmented call chains
        request_id = tool_parameters.get("run_id") or "no-run-id"
        start_time = time.time()

        # Validate required user_id
        user_id = tool_parameters.get("user_id")
        if not user_id:
            error_message = "user_id is required"
            logger.error("[req:%s] Delete all memories failed: %s", request_id, error_message)
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": {}})
            yield self.create_text_message(f"Error: {error_message}")
            return

        # Build params (NOTE: run_id is NOT included - it's only used for request tracing)
        params: dict[str, Any] = {"user_id": user_id}
        if tool_parameters.get("agent_id"):
            params["agent_id"] = tool_parameters["agent_id"]

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"

            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                WRITE_OPERATION_TIMEOUT,
                logger,
                "delete_all",
            )

            # Log operation start
            logger.info(
                "[req:%s] Delete all memories started (mode: %s, user_id: %s)",
                request_id,
                mode_str,
                user_id,
            )
            if async_mode:
                client = get_async_local_client(self.runtime.credentials)
                # Submit delete_all to background event loop without awaiting (non-blocking)
                # Fire-and-forget: exceptions in background execution won't be caught here
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(
                    client.delete_all(params, timeout_s=timeout),
                    loop,
                )
                client.track_bg_task(
                    future,
                    f"delete_all_memories(user_id={user_id}, req_id={request_id})",
                )
                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": {"filters": params},
                    **DELETE_ALL_ACCEPT_RESULT,
                })
                yield self.create_text_message(
                    "Batch memory deletion has been accepted and will be processed asynchronously.",
                )
            else:
                client = get_local_client(self.runtime.credentials)
                result = client.delete_all(params)
                elapsed = time.time() - start_time
                logger.info(
                    "[req:%s] Delete all memories completed (mode: %s, user_id: %s, "
                    "duration: %.2fs)",
                    request_id,
                    mode_str,
                    user_id,
                    elapsed,
                )
                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": {"filters": params},
                    "results": result,
                })
                yield self.create_text_message(
                    f"All memories deleted successfully with filters : {params}",
                )

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Delete all memories failed (user_id: %s, duration: %.2fs)",
                request_id,
                user_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": {}})
            yield self.create_text_message(f"Failed to delete memories: {error_message}")
