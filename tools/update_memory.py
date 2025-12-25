"""Dify tool for updating a memory in Mem0 by ID."""

import asyncio
import time
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import UPDATE_ACCEPT_RESULT, WRITE_OPERATION_TIMEOUT
from utils.helpers import parse_timeout
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
        # Get request ID for tracing (not used for memory filtering)
        # Only use run_id if explicitly provided; no auto-generation to avoid fragmented call chains
        request_id = tool_parameters.get("run_id") or "no-run-id"
        start_time = time.time()

        memory_id = tool_parameters["memory_id"]
        text = tool_parameters["text"]

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"

            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                WRITE_OPERATION_TIMEOUT,
                logger,
                "update",
            )

            # Log operation start
            logger.info(
                "[req:%s] Update memory started (mode: %s, memory_id: %s)",
                request_id,
                mode_str,
                memory_id,
            )

            if not async_mode:
                # Sync mode: directly call update and catch exceptions
                client = get_local_client(self.runtime.credentials)
                try:
                    result = client.update(memory_id, {"text": text})
                    elapsed = time.time() - start_time
                    logger.info(
                        "[req:%s] Update memory completed "
                        "(mode: %s, memory_id: %s, duration: %.2fs)",
                        request_id,
                        mode_str,
                        memory_id,
                        elapsed,
                    )
                    yield self.create_json_message({
                        "status": "SUCCESS",
                        "messages": {"memory_id": memory_id, "text": text},
                        "results": result,
                    })
                    yield self.create_text_message(
                        f"Memory {memory_id} updated to '{text}' successfully!",
                    )
                except (ValueError, AttributeError):
                    # Mem0 throws ValueError or AttributeError when memory not found
                    elapsed = time.time() - start_time
                    logger.warning(
                        "[req:%s] Memory not found (memory_id: %s, duration: %.2fs)",
                        request_id,
                        memory_id,
                        elapsed,
                    )
                    error_message = f"Memory not found: {memory_id}"
                    yield self.create_json_message(
                        {"status": "NOT_FOUND", "messages": error_message, "results": {}},
                    )
                    yield self.create_text_message(f"Error: {error_message}")
            else:
                client = get_async_local_client(self.runtime.credentials)
                # Submit update to background event loop without awaiting (non-blocking)
                # Fire-and-forget: exceptions in background execution won't be caught here
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(
                    client.update(memory_id, {"text": text}, timeout_s=timeout),
                    loop,
                )
                client.track_bg_task(
                    future,
                    f"update_memory(memory_id={memory_id}, req_id={request_id})",
                )

                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": {"memory_id": memory_id, "text": text},
                    **UPDATE_ACCEPT_RESULT,
                })
                yield self.create_text_message(
                    "Memory update has been accepted and will be processed asynchronously.",
                )

        except Exception as e:
            # Catch all other exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Update memory failed (memory_id: %s, duration: %.2fs)",
                request_id,
                memory_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": {}},
            )
            yield self.create_text_message(f"Failed to update memory: {error_message}")
