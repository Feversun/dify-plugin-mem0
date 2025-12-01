"""Dify tool to package search payload for mem0 client and return results."""

import asyncio
import json
from collections.abc import Generator
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from utils.config_builder import is_async_mode
from utils.constants import SEARCH_DEFAULT_TOP_K, SEARCH_OPERATION_TIMEOUT
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class SearchMemoryTool(Tool):
    """Tool that builds a search payload and delegates to mem0_client.search."""

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Validate required fields
        query = tool_parameters.get("query", "")
        if not query:
            error_message = "query is required"
            logger.error("Search memory failed: %s", error_message)
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
            yield self.create_text_message(f"Failed to search memory: {error_message}")
            return

        user_id = tool_parameters.get("user_id")
        if not user_id:
            error_message = "user_id is required"
            logger.error("Search memory failed: %s", error_message)
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
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
                logger.exception("Search memory failed: %s", msg)
                yield self.create_json_message({"status": "ERROR", "messages": msg, "results": []})
                yield self.create_text_message(f"Failed to search memory: {msg}")
                return
        # Optional scoping fields
        agent_id = tool_parameters.get("agent_id")
        run_id = tool_parameters.get("run_id")
        if agent_id:
            payload["agent_id"] = agent_id
        if run_id:
            payload["run_id"] = run_id

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
            # Get timeout from parameters, use default if not provided
            timeout = tool_parameters.get("timeout")
            if timeout is None:
                timeout = SEARCH_OPERATION_TIMEOUT
            else:
                try:
                    timeout = float(timeout)
                except (TypeError, ValueError):
                    logger.warning(
                        "Invalid timeout value: %s, using default: %d",
                        timeout,
                        SEARCH_OPERATION_TIMEOUT,
                    )
                    timeout = SEARCH_OPERATION_TIMEOUT
            # Initialize results with default value to ensure it's always defined
            results: list[dict[str, Any]] = []
            if async_mode:
                # Note: get_async_local_client() reuses instances when config is unchanged.
                # Resources are managed at plugin lifecycle level via shutdown()
                client = get_async_local_client(self.runtime.credentials)
                # Submit to background loop and wait on future to avoid nested event loop issues
                # ensure_bg_loop() returns a long-lived, reusable event loop
                loop = client.ensure_bg_loop()
                future = asyncio.run_coroutine_threadsafe(client.search(payload), loop)
                try:
                    results = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    # Cancel the future to prevent the background task from hanging
                    future.cancel()
                    logger.exception(
                        "Search operation timed out after %s seconds (%s, query: %s..., user_id: %s)",
                        timeout,
                        mode_str,
                        query[:50],
                        user_id,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []
                except Exception as e:
                    # Catch all other exceptions (network errors, connection errors, DNS failures,
                    # SSL errors, authentication failures, etc.) to ensure service degradation
                    # works for all failure scenarios, not just timeouts
                    logger.exception(
                        "Search operation failed with error: %s (%s, query: %s..., user_id: %s)",
                        type(e).__name__,
                        mode_str,
                        query[:50],
                        user_id,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []
            else:
                # Sync mode: no timeout protection (blocking call)
                # If timeout protection is needed, use async_mode=true
                client = get_local_client(self.runtime.credentials)
                try:
                    results = client.search(payload)
                except Exception as e:
                    # Catch all exceptions for sync mode to ensure service degradation
                    logger.exception(
                        "Search operation failed with error: %s (%s, query: %s..., user_id: %s)",
                        type(e).__name__,
                        mode_str,
                        query[:50],
                        user_id,
                    )
                    # Service degradation: return empty results to allow workflow to continue
                    results = []

            # JSON output
            norm_results = []
            for r in results or []:
                if not isinstance(r, dict):
                    continue
                norm_results.append(
                    {
                        "id": r.get("id"),
                        "memory": r.get("memory"),
                        "score": r.get("score", 0.0),
                        "metadata": r.get("metadata", {}),
                        "created_at": r.get("created_at", ""),
                    },
                )

            # Log search results
            logger.info(
                "Search completed (%s, query: %s..., user_id: %s, found %d results, results: %s)",
                mode_str,
                query[:50],
                user_id,
                len(norm_results),
                norm_results,
            )

            yield self.create_json_message({
                "status": "SUCCESS",
                "messages": payload.get("query", ""),
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
            else:
                lines.append("")
                lines.append("No results found.")

            yield self.create_text_message("\n".join(lines))

        except json.JSONDecodeError as e:
            # Should not happen here, but guard anyway
            logger.exception(
                "Error parsing JSON during search (query: %s..., user_id: %s)",
                query[:50],
                user_id,
            )
            error_message = f"Error parsing JSON: {e}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
            yield self.create_text_message(f"Failed to search memory: {error_message}")
        except Exception as e:
            # Catch all exceptions to ensure workflow continues
            logger.exception(
                "Error during memory search (query: %s..., user_id: %s)",
                query[:50],
                user_id,
            )
            error_message = f"Error: {e}"
            yield self.create_json_message(
                {"status": "ERROR", "messages": error_message, "results": []})
            yield self.create_text_message(f"Failed to search memory: {error_message}")
