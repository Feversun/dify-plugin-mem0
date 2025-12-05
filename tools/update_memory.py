import asyncio
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import UPDATE_ACCEPT_RESULT
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class UpdateMemoryTool(Tool):
    """Tool that updates a memory by ID."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """Invoke the tool.

        Args:
            tool_parameters (dict): Tool parameters.

        Returns:
            Generator[ToolInvokeMessage, None, None]: Generator of tool invoke messages.

        """
        memory_id = tool_parameters["memory_id"]
        text = tool_parameters["text"]

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"

            # In sync mode, check if memory exists before updating
            if not async_mode:
                client = get_local_client(self.runtime.credentials)
                # Check if memory exists
                existing = client.get(memory_id)
                if not existing or not isinstance(existing, dict):
                    logger.warning("Memory not found: %s", memory_id)
                    error_message = f"Memory not found: {memory_id}"
                    yield self.create_json_message(
                        {"status": "ERROR", "messages": error_message, "results": {}})
                    yield self.create_text_message(f"Error: {error_message}")
                    return

                # Wrap update call in try-except to catch Mem0 internal errors
                try:
                    result = client.update(memory_id, {"text": text})
                    logger.info(
                        "Memory updated successfully (%s, memory_id: %s, new_text: %s, result: %s)",
                        mode_str,
                        memory_id,
                        text,
                        result,
                    )
                except AttributeError:
                    # Mem0 internal error: memory was deleted between get() and update()
                    logger.warning("Memory %s not found or already deleted", memory_id)
                    error_message = f"Memory not found or already deleted: {memory_id}"
                    yield self.create_json_message(
                        {"status": "ERROR", "messages": error_message, "results": {}})
                    yield self.create_text_message(f"Error: {error_message}")
                    return

                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": {"memory_id": memory_id, "text": text},
                    "results": result,
                })
                yield self.create_text_message(
                    f"Memory {memory_id} updated to '{text}' successfully!")
            else:
                client = get_async_local_client(self.runtime.credentials)
                # Submit update to background event loop without awaiting (non-blocking)
                loop = client.ensure_bg_loop()
                asyncio.run_coroutine_threadsafe(client.update(memory_id, {"text": text}), loop)
                logger.info(
                    "Memory update submitted to background loop (%s, memory_id: %s, new_text: %s)",
                    mode_str,
                    memory_id,
                    text,
                )

                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": {"memory_id": memory_id, "text": text},
                    **UPDATE_ACCEPT_RESULT,
                })
                yield self.create_text_message("Asynchronous memory update has been accepted.")

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            logger.exception("Error updating memory %s", memory_id)
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
            yield self.create_text_message(f"Failed to update memory: {error_message}")
