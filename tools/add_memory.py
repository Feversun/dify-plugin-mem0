"""Dify tool for adding a memory via Mem0 client."""

import asyncio
import time
from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import (
    ADD_ACCEPT_RESULT,
    ADD_SKIP_RESULT,
    WRITE_OPERATION_TIMEOUT,
)
from utils.helpers import parse_timeout
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class AddMemoryTool(Tool):
    """Tool to add user/assistant messages as a memory."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Get request ID for tracing (not used for memory filtering)
        # Only use run_id if explicitly provided; no auto-generation to avoid fragmented call chains
        request_id = tool_parameters.get("run_id") or "no-run-id"
        start_time = time.time()

        # Required user_id
        user_id = tool_parameters.get("user_id")
        if not user_id:
            error_message = "user_id is required"
            logger.error("[req:%s] Add memory failed: %s", request_id, error_message)
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": {}},
            )
            yield self.create_text_message(f"Failed to add memory: {error_message}")
            return

        # Collect inputs (strip whitespace to avoid empty-only content)
        user_text = (tool_parameters.get("user") or "").strip()
        assistant_text = (tool_parameters.get("assistant") or "").strip()
        agent_id = tool_parameters.get("agent_id")
        app_id = tool_parameters.get("app_id")
        metadata = tool_parameters.get("metadata")  # client parses JSON if string

        # Build messages
        messages = []
        if user_text:
            messages.append({"role": "user", "content": user_text})
        # Only add assistant message if it's different from user message
        if assistant_text and assistant_text != user_text:
            messages.append({"role": "assistant", "content": assistant_text})

        # Build payload (only include optional fields if provided)
        # NOTE: run_id is NOT included in payload - it's only used for request tracing
        payload: dict[str, Any] = {"messages": messages, "user_id": user_id}
        if agent_id:
            payload["agent_id"] = agent_id
        if app_id:
            payload["app_id"] = app_id
        if metadata:
            payload["metadata"] = metadata

        try:
            # Skip when no messages prepared or only blank content
            if (
                not messages
                or not any(
                    isinstance(m.get("content"), str) and m["content"].strip()
                    for m in messages
                )
            ):
                logger.debug(
                    "[req:%s] Skipping memory addition for empty messages (user_id: %s)",
                    request_id,
                    user_id,
                )
                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": messages,
                    **ADD_SKIP_RESULT,
                })
                yield self.create_text_message("Skipped memory addition for empty messages.")
                return

            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"

            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                WRITE_OPERATION_TIMEOUT,
                logger,
                "add",
            )

            # Log operation start
            logger.info(
                "[req:%s] Add memory started (mode: %s, user_id: %s)",
                request_id,
                mode_str,
                user_id,
            )

            if async_mode:
                client = get_async_local_client(self.runtime.credentials)
                # Submit add to background event loop without awaiting (non-blocking)
                # Fire-and-forget: exceptions in background execution won't be caught here
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(
                    client.add(payload, timeout_s=timeout),
                    loop,
                )
                client.track_bg_task(
                    future,
                    f"add_memory(user_id={user_id}, req_id={request_id})",
                )
                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": messages,
                    **ADD_ACCEPT_RESULT,
                })
                yield self.create_text_message(
                    "Memory addition has been accepted and will be processed asynchronously.",
                )
            else:
                client = get_local_client(self.runtime.credentials)
                result = client.add(payload)
                elapsed = time.time() - start_time
                logger.info(
                    "[req:%s] Add memory completed (mode: %s, user_id: %s, duration: %.2fs)",
                    request_id,
                    mode_str,
                    user_id,
                    elapsed,
                )
                yield self.create_json_message({
                    "status": "SUCCESS",
                    "messages": messages,
                    "results": result,
                })
                yield self.create_text_message("Memory added synchronously.")

        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Add memory failed (user_id: %s, duration: %.2fs)",
                request_id,
                user_id,
                elapsed,
            )
            error_message = f"Error: {e!s}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": {}},
            )
            yield self.create_text_message(f"Failed to add memory: {error_message}")
