"""Mem0 provider for Dify plugin system (local mode only).

This module implements a tool provider for Mem0 in local mode. The provider
handles credential validation and provides an interface for Dify to interact
with Mem0's memory capabilities in a self-hosted/local setup.
"""

from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from utils.mem0_client import LocalClient


class Mem0Provider(ToolProvider):
    """Tool provider for Mem0 (local).

    Validates simplified JSON configs for local LLM/Embedder/Reranker/Vector/Graph
    and performs a lightweight sanity search to ensure configuration is valid.
    """

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            client = LocalClient(credentials)
            # Local mode: sanity check by performing a no-op search
            _ = client.search({"query": "test", "user_id": "validation_test"})
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
