"""Dify tool for adding a memory via Mem0 client."""

import asyncio
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import ADD_ACCEPT_RESULT, ADD_SKIP_RESULT
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class AddMemoryTool(Tool):
    """Tool to add user/assistant messages as a memory."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Required user_id
        user_id = tool_parameters.get("user_id")
        if not user_id:
            error_message = "user_id is required"
            logger.error("Add memory failed: %s", error_message)
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
            yield self.create_text_message(f"Failed to add memory: {error_message}")
            return

        # Collect inputs (strip whitespace to avoid empty-only content)
        user_text = (tool_parameters.get("user") or "").strip()
        assistant_text = (tool_parameters.get("assistant") or "").strip()
        agent_id = tool_parameters.get("agent_id")
        app_id = tool_parameters.get("app_id")
        run_id = tool_parameters.get("run_id")
        metadata = tool_parameters.get("metadata")  # client parses JSON if string
        output_format = tool_parameters.get("output_format")

        # Build messages
        messages = []
        if user_text:
            messages.append({"role": "user", "content": user_text})
        # Only add assistant message if it's different from user message
        if assistant_text and assistant_text != user_text:
            messages.append({"role": "assistant", "content": assistant_text})

        # Build payload (only include optional fields if provided)
        payload: dict[str, Any] = {"messages": messages, "user_id": user_id}
        if agent_id:
            payload["agent_id"] = agent_id
        if app_id:
            payload["app_id"] = app_id
        if run_id:
            payload["run_id"] = run_id
        if metadata:
            payload["metadata"] = metadata
        if output_format:
            payload["output_format"] = output_format

        try:
            # Skip when no messages prepared or only blank content
            if (
                not messages
                or not any(
                    isinstance(m.get("content"), str) and m["content"].strip()
                    for m in messages
                )
            ):
                logger.info("Skipping memory addition for empty messages (user_id: %s)", user_id)
                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": messages,
                    **ADD_SKIP_RESULT,
                })
                yield self.create_text_message("Skipped memory addition for empty messages.")
                return

            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"
            if async_mode:
                client = get_async_local_client(self.runtime.credentials)
                # Submit add to background event loop without awaiting (non-blocking)
                loop = client.ensure_bg_loop()
                asyncio.run_coroutine_threadsafe(client.add(payload), loop)
                logger.info(
                    "Memory addition submitted to background loop (%s, user_id: %s)",
                    mode_str,
                    user_id,
                )

                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": messages,
                    **ADD_ACCEPT_RESULT,
                })
                yield self.create_text_message("Asynchronous memory addition has been accepted.")
            else:
                client = get_local_client(self.runtime.credentials)
                result = client.add(payload)
                logger.info(
                    "Memory added successfully (%s, user_id: %s, result: %s)",
                    mode_str,
                    user_id,
                    result,
                )
                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": messages,
                    "results": result,
                })
                yield self.create_text_message("Memory added synchronously.")

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            logger.exception("Error adding memory for user_id: %s", user_id)
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
            yield self.create_text_message(f"Failed to add memory: {error_message}")
