"""Mem0 provider for Dify plugin system (local mode only).

This module implements a tool provider for Mem0 in local mode. The provider
handles credential validation and provides an interface for Dify to interact
with Mem0's memory capabilities in a self-hosted/local setup.
"""

import asyncio
from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from utils.config_builder import is_async_mode
from utils.logger import get_logger
from utils.mem0_client import (
    get_async_local_client,
    get_local_client,
)

logger = get_logger(__name__)


class Mem0Provider(ToolProvider):
    """Tool provider for Mem0 (local).

    Validates simplified JSON configs for local LLM/Embedder/Reranker/Vector/Graph
    and performs a lightweight sanity search to ensure configuration is valid.
    """

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        logger.info("Validating Mem0 provider credentials")
        try:
            async_mode = is_async_mode(credentials)
            mode = "async" if async_mode else "sync"
            logger.info("Validating credentials in %s mode", mode)
            if async_mode:
                client = get_async_local_client(credentials)
                loop = client.ensure_bg_loop()
                # Perform a small no-op search to validate providers
                _ = asyncio.run_coroutine_threadsafe(
                    client.search({"query": "test", "user_id": "validation_test"}),
                    loop,
                ).result()
            else:
                client = get_local_client(credentials)
                _ = client.search({"query": "test", "user_id": "validation_test"})
            logger.info("Credentials validated successfully")
        except Exception as e:
            logger.exception("Credential validation failed")
            raise ToolProviderCredentialValidationError(str(e)) from e
