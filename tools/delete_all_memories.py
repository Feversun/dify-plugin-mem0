"""Dify tool for deleting all memories from Mem0 for a specific user."""

import asyncio
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import DELETE_ALL_ACCEPT_RESULT
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class DeleteAllMemoriesTool(Tool):
    """Tool that deletes all memories for a specific user, with optional filtering."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Validate required user_id
        user_id = tool_parameters.get("user_id")
        if not user_id:
            error_message = "user_id is required"
            logger.error("Delete all memories failed: %s", error_message)
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

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"
            if async_mode:
                client = get_async_local_client(self.runtime.credentials)
                # Submit delete_all to background event loop without awaiting (non-blocking)
                loop = client.ensure_bg_loop()
                asyncio.run_coroutine_threadsafe(client.delete_all(params), loop)
                logger.info(
                    "Delete all memories submitted to background loop (%s, user_id: %s)",
                    mode_str,
                    user_id,
                )

                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": {"filters": params},
                    **DELETE_ALL_ACCEPT_RESULT,
                })
                yield self.create_text_message(
                    "Asynchronous batch memory deletion has been accepted.")
            else:
                client = get_local_client(self.runtime.credentials)
                result = client.delete_all(params)
                logger.info(
                    "All memories deleted successfully (%s, user_id: %s, result: %s)",
                    mode_str,
                    user_id,
                    result,
                )
                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": {"filters": params},
                    "results": result,
                })
                yield self.create_text_message(
                    f"All memories deleted successfully with filters : {params}")

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            logger.exception("Error deleting all memories for user_id: %s", user_id)
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
            yield self.create_text_message(f"Failed to delete memories: {error_message}")
