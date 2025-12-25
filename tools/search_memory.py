"""Dify tool to package search payload for mem0 client and return results."""

import asyncio
import json
import time
from collections.abc import Generator
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import READ_OPERATION_TIMEOUT, SEARCH_DEFAULT_TOP_K
from utils.helpers import format_recent_timestamp, parse_timeout
from utils.logger import get_logger
from utils.mem0_client import (
    QueueOverloadError,
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class SearchMemoryTool(Tool):
    """Tool that builds a search payload and delegates to mem0_client.search."""

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
    ) -> Generator[ToolInvokeMessage, None, None]:
        # Get request ID for tracing (not used for memory filtering)
        # Only use run_id if explicitly provided; no auto-generation to avoid fragmented call chains
        request_id = tool_parameters.get("run_id") or "no-run-id"
        start_time = time.time()

        # Validate required fields
        query = tool_parameters.get("query", "")
        if not query:
            error_message = "query is required"
            logger.error("[req:%s] Search memory failed: %s", request_id, error_message)
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to search memory: {error_message}")
            return

        user_id = tool_parameters.get("user_id")
        if not user_id:
            error_message = "user_id is required"
            logger.error("[req:%s] Search memory failed: %s", request_id, error_message)
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to search memory: {error_message}")
            return

        # Build payload
        payload: dict[str, Any] = {"query": query, "user_id": user_id}

        # Optional advanced filters (JSON)
        filters_value = tool_parameters.get("filters")
        if filters_value:
            try:
                payload["filters"] = (
                    json.loads(filters_value)
                    if isinstance(filters_value, str)
                    else filters_value
                )
            except json.JSONDecodeError as json_err:
                msg = f"Invalid JSON in filters: {json_err}"
                logger.exception("[req:%s] Search memory failed: %s", request_id, msg)
                yield self.create_json_message(
                    {"status": "ERROR", "messages": msg, "results": []},
                )
                yield self.create_text_message(f"Failed to search memory: {msg}")
                return
        # Optional scoping fields
        # NOTE: run_id is NOT included in payload - it's only used for request tracing
        agent_id = tool_parameters.get("agent_id")
        if agent_id:
            payload["agent_id"] = agent_id

        # Optional top_k -> limit mapping for mem0_client (default 5)
        top_k = tool_parameters.get("top_k")
        if top_k is None:
            payload["limit"] = SEARCH_DEFAULT_TOP_K
        else:
            try:
                payload["limit"] = int(top_k)
            except (TypeError, ValueError):
                payload["limit"] = top_k

        try:
            async_mode = is_async_mode(self.runtime.credentials)
            mode_str = "async" if async_mode else "sync"
            timeout = parse_timeout(
                tool_parameters.get("timeout"),
                READ_OPERATION_TIMEOUT,
                logger,
                "search",
            )

            # Log operation start
            logger.info(
                "[req:%s] Search started (mode: %s, user_id: %s)",
                request_id,
                mode_str,
                user_id,
            )

            # Initialize results with default value to ensure it's always defined
            results: list[dict[str, Any]] = []
            error_type = None  # Track error type for enhanced result
            if async_mode:
                # Note: get_async_local_client() reuses instances when config is unchanged.
                # Resources are managed at plugin lifecycle level via shutdown()
                client = get_async_local_client(self.runtime.credentials)
                # Submit to background loop and wait on future to avoid nested event loop issues
                # ensure_bg_loop() returns a long-lived, reusable event loop
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(
                    client.search(payload, timeout_s=timeout),
                    loop,
                )
                client.track_bg_task(
                    future,
                    f"search_memory(user_id={user_id}, req_id={request_id})",
                )
                try:
                    failsafe_timeout = timeout + 1.0
                    results = future.result(timeout=failsafe_timeout)
                except asyncio.TimeoutError:
                    # Timeout already logged by _run_with_semaphore - don't duplicate
                    error_type = "TIMEOUT"
                    results = []
                except FuturesTimeoutError:
                    # Failsafe timeout - this is a second layer of protection
                    future.cancel()
                    elapsed = time.time() - start_time
                    logger.warning(
                        "[req:%s] Search operation failsafe timeout after %s seconds "
                        "(mode: %s, user_id: %s, duration: %.2fs)",
                        request_id,
                        failsafe_timeout,
                        mode_str,
                        user_id,
                        elapsed,
                    )
                    error_type = "TIMEOUT"
                    results = []
                except QueueOverloadError:
                    # Queue overload already logged by _run_with_semaphore - don't duplicate
                    error_type = "OVERLOAD"
                    results = []
                except Exception as e:
                    # Catch all other exceptions (network errors, connection errors, DNS failures,
                    # SSL errors, authentication failures, etc.) to ensure service degradation
                    # works for all failure scenarios, not just timeouts
                    elapsed = time.time() - start_time
                    logger.exception(
                        "[req:%s] Search operation failed with error: %s "
                        "(mode: %s, user_id: %s, duration: %.2fs)",
                        request_id,
                        type(e).__name__,
                        mode_str,
                        user_id,
                        elapsed,
                    )
                    error_type = "ERROR"
                    results = []
            else:
                # Sync mode: no timeout protection (blocking call)
                # If timeout protection is needed, use async_mode=true
                client = get_local_client(self.runtime.credentials)
                try:
                    results = client.search(payload)
                except Exception as e:
                    # Catch all exceptions for sync mode to ensure service degradation
                    elapsed = time.time() - start_time
                    logger.exception(
                        "[req:%s] Search operation failed with error: %s "
                        "(mode: %s, user_id: %s, duration: %.2fs)",
                        request_id,
                        type(e).__name__,
                        mode_str,
                        user_id,
                        elapsed,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []

            # JSON output
            norm_results = []
            for r in results or []:
                if not isinstance(r, dict):
                    continue
                timestamp = format_recent_timestamp(
                    r.get("created_at"),
                    r.get("updated_at"),
                )
                entry = {
                    "id": r.get("id"),
                    "memory": r.get("memory"),
                    "score": r.get("score", 0.0),
                    "metadata": r.get("metadata", {}),
                }
                if timestamp:
                    entry["timestamp"] = timestamp
                norm_results.append(entry)

            # Log search results (only for sync mode; async mode logs in callback)
            if not async_mode:
                elapsed = time.time() - start_time
                logger.info(
                    "[req:%s] Search completed (mode: %s, user_id: %s, "
                    "found %d results, duration: %.2fs)",
                    request_id,
                    mode_str,
                    user_id,
                    len(norm_results),
                    elapsed,
                )

            # Build result with appropriate status and message
            if error_type:
                # Operation failed - return error status with descriptive message
                if error_type == "TIMEOUT":
                    status = "TIMEOUT"
                    messages = "Operation timed out, returning empty results"
                elif error_type == "OVERLOAD":
                    status = "OVERLOAD"
                    messages = "System overloaded, returning empty results"
                else:
                    status = "ERROR"
                    messages = "Operation failed, returning empty results"
            else:
                # Operation succeeded - return success with result summary
                status = "SUCCESS"
                messages = f"Found {len(norm_results)} matching memories"

            yield self.create_json_message({
                "status": status,
                "messages": messages,
                "results": norm_results,
            })

            # Text output (detailed for downstream workflow consumption)
            lines = [f"Query: {payload.get('query', '')}", "", "Results:"]
            if norm_results:
                for idx, r in enumerate(norm_results, 1):
                    lines.append("")
                    lines.append(f"{idx}. Memory: {r.get('memory', '')}")
                    score = r.get("score")
                    if isinstance(score, (int, float)):
                        lines.append(f"   Score: {score:.2f}")
                    md = r.get("metadata")
                    if md:
                        lines.append(f"   Metadata: {md}")
                    ts_value = r.get("timestamp")
                    if ts_value:
                        lines.append(f"   Timestamp: {ts_value}")
            else:
                lines.append("")
                lines.append("No results found.")

            yield self.create_text_message("\n".join(lines))

        except json.JSONDecodeError as e:
            # Should not happen here, but guard anyway
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Error parsing JSON during search (user_id: %s, duration: %.2fs)",
                request_id,
                user_id,
                elapsed,
            )
            error_message = f"Error parsing JSON: {e}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to search memory: {error_message}")
        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            elapsed = time.time() - start_time
            logger.exception(
                "[req:%s] Search failed (user_id: %s, duration: %.2fs)",
                request_id,
                user_id,
                elapsed,
            )
            error_message = f"Error: {e}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []},
            )
            yield self.create_text_message(f"Failed to search memory: {error_message}")
