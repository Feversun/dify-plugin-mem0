"""Dify tool for deleting a memory from Mem0 by ID."""

import asyncio
import time
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import DELETE_ACCEPT_RESULT, WRITE_OPERATION_TIMEOUT
from utils.helpers import parse_timeout
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class DeleteMemoryTool(Tool):
    """Tool that deletes a specific memory by its ID."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
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
                WRITE_OPERATION_TIMEOUT,
                logger,
                "delete",
            )

            # Log operation start
            logger.info(
                "[req:%s] Delete memory started (mode: %s, memory_id: %s)",
                request_id,
                mode_str,
                memory_id,
            )

            if not async_mode:
                # Sync mode: directly call delete and catch exceptions
                client = get_local_client(self.runtime.credentials)
                try:
                    result = client.delete(memory_id)
                    elapsed = time.time() - start_time
                    logger.info(
                        "[req:%s] Delete memory completed "
                        "(mode: %s, memory_id: %s, duration: %.2fs)",
                        request_id,
                        mode_str,
                        memory_id,
                        elapsed,
                    )
                    yield self.create_json_message({
                        "status": "SUCCESS",
                        "messages": {"memory_id": memory_id},
                        "results": result,
                    })
                    yield self.create_text_message(f"Memory {memory_id} deleted successfully!")
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
                # Submit delete to background event loop without awaiting (non-blocking)
                # Fire-and-forget: exceptions in background execution won't be caught here
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(
                    client.delete(memory_id, timeout_s=timeout),
                    loop,
                )
                client.track_bg_task(
                    future,
                    f"delete_memory(memory_id={memory_id}, req_id={request_id})",
                )

                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": {"memory_id": memory_id},
                    **DELETE_ACCEPT_RESULT,
                })
                yield self.create_text_message(
                    "Memory deletion has been accepted and will be processed asynchronously.",
                )

        except Exception as e:
            # Catch all other exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Delete memory failed (memory_id: %s, duration: %.2fs)",
                request_id,
                memory_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": {}},
            )
            yield self.create_text_message(f"Failed to delete memory: {error_message}")
