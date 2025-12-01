"""Build Mem0 local configuration from provider credentials.

This module parses simplified JSON blocks for local mode:
- local_llm_json
- local_embedder_json
- local_reranker_json (optional)
- local_vector_db_json
- local_graph_db_json (optional)

Each is expected to be a JSON object with at least {"provider": ..., "config": {...}}.
"""

from __future__ import annotations

import ast
import hashlib
import json
import threading
from typing import Any
from urllib.parse import quote_plus

from .constants import PGVECTOR_MAX_CONNECTIONS, PGVECTOR_MIN_CONNECTIONS
from .logger import get_logger

logger = get_logger(__name__)


def _raise_config_error(msg: str) -> None:
    """Raise a ValueError for configuration errors with logging.

    Args:
        msg: Error message to log and raise.

    """
    logger.error(msg)
    raise ValueError(msg)


def _parse_json_block(raw: str | dict[str, Any] | None, field_name: str) -> dict[str, Any] | None:

    if raw is None:
        return None
    # Accept already-parsed dicts from upstream runtimes
    if isinstance(raw, dict):
        data = raw
    else:
        text = str(raw).strip()
        if text == "":
            return None
        # Strip code fences if user pasted with ```json ... ```
        if text.startswith("```"):
            lines = text.splitlines()
            # Drop first fence line and possible trailing fence
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        # First try strict JSON
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            # Fallback: accept Python-literal style dicts (single quotes, etc.)
            try:
                candidate = ast.literal_eval(text)
                if not isinstance(candidate, dict):
                    msg = f"{field_name} must be a JSON object"
                    _raise_config_error(msg)
                data = candidate
            except Exception:
                msg = f"{field_name} is not valid JSON"
                logger.exception("Failed to parse %s", field_name)
                _raise_config_error(msg)
    if not isinstance(data, dict):
        msg = f"{field_name} must be a JSON object"
        _raise_config_error(msg)
    provider = data.get("provider")
    cfg = data.get("config")
    if not provider or not isinstance(cfg, dict):
        msg = f"{field_name} must include 'provider' and 'config' object"
        _raise_config_error(msg)
    logger.debug("Successfully parsed %s with provider: %s", field_name, provider)
    return data


def _normalize_pgvector_config(config: dict[str, Any]) -> dict[str, Any]:
    """Normalize pgvector config according to Mem0 official documentation.

    Supports three connection methods (in priority order):
    1. connection_pool (highest priority) - psycopg2 connection pool object
    2. connection_string - PostgreSQL connection string
    3. Individual parameters - user, password, host, port, dbname, sslmode

    Also sets default connection pool settings (minconn/maxconn) if not provided.
    Preserves all valid pgvector config keys and removes discrete connection parameters
    when connection_string or connection_pool is used.

    Reference: Mem0 pgvector configuration documentation
    """
    normalized: dict[str, Any] = {}

    # Valid pgvector config keys according to official documentation
    valid_keys = (
        "dbname",
        "collection_name",
        "embedding_model_dims",
        "user",
        "password",
        "host",
        "port",
        "diskann",
        "hnsw",
        "sslmode",
        "connection_string",
        "connection_pool",
        "minconn",
        "maxconn",
        "metric",  # Additional key that may be used
    )

    # Preserve all valid keys from config
    for key in valid_keys:
        if key in config and config[key] is not None:
            normalized[key] = config[key]

    # Handle connection parameters according to priority:
    # 1. connection_pool (highest priority) - overrides everything
    if "connection_pool" in normalized:
        logger.debug("Using connection_pool (highest priority)")
        # Remove connection_string and individual connection parameters
        # as connection_pool overrides them
        normalized.pop("connection_string", None)
        normalized.pop("user", None)
        normalized.pop("password", None)
        normalized.pop("host", None)
        normalized.pop("port", None)
        normalized.pop("sslmode", None)
        # dbname may still be needed for some operations, keep it if provided
    # 2. connection_string (second priority) - overrides individual parameters
    elif "connection_string" in normalized and isinstance(
        normalized["connection_string"], str,
    ):
        logger.debug("Using connection_string (second priority)")
        # Remove individual connection parameters as connection_string overrides them
        normalized.pop("user", None)
        normalized.pop("password", None)
        normalized.pop("host", None)
        normalized.pop("port", None)
        normalized.pop("sslmode", None)
        # dbname is included in connection_string, but keep it if explicitly provided
        # for compatibility (Mem0 may use it for some operations)
    # 3. Individual parameters (lowest priority) - build connection_string
    else:
        # Extract connection parameters
        dbname = normalized.get("dbname") or normalized.get("database") or "postgres"
        user = normalized.get("user") or ""
        password = normalized.get("password") or ""
        host = normalized.get("host") or "localhost"
        port = str(normalized.get("port") or "5432")
        sslmode = normalized.get("sslmode")  # e.g., "disable" | "require"

        if not user:
            # If user is not provided, return as-is; Mem0 may handle other forms.
            logger.warning(
                "Insufficient pgvector connection parameters (user is required)",
            )
            return config

        # Build connection_string from individual parameters
        user_enc = quote_plus(str(user))
        pwd_enc = quote_plus(str(password))
        # psycopg2 accepts postgresql:// URI; do NOT include '+psycopg2'
        dsn = f"postgresql://{user_enc}:{pwd_enc}@{host}:{port}/{dbname}"
        if sslmode:
            dsn = f"{dsn}?sslmode={quote_plus(str(sslmode))}"

        normalized["connection_string"] = dsn
        logger.debug("Built connection_string from individual parameters")

        # Remove individual connection parameters as they're now in connection_string
        normalized.pop("user", None)
        normalized.pop("password", None)
        normalized.pop("host", None)
        normalized.pop("port", None)
        normalized.pop("sslmode", None)
        # Keep dbname as it may be used for some operations

    # Set connection pool settings if not already provided
    # Use default constants to ensure sufficient connections for concurrent operations
    if "minconn" not in normalized or normalized.get("minconn") is None:
        normalized["minconn"] = PGVECTOR_MIN_CONNECTIONS
        logger.debug(
            "Setting pgvector minconn to default: %d",
            PGVECTOR_MIN_CONNECTIONS,
        )
    if "maxconn" not in normalized or normalized.get("maxconn") is None:
        normalized["maxconn"] = PGVECTOR_MAX_CONNECTIONS
        logger.debug(
            "Setting pgvector maxconn to default: %d",
            PGVECTOR_MAX_CONNECTIONS,
        )

    return normalized


# Cache for built configurations to avoid redundant logging
_built_config_cache: dict[str, dict[str, Any]] = {}
_build_config_lock = threading.Lock()


def build_local_mem0_config(credentials: dict[str, Any]) -> dict[str, Any]:
    """Construct mem0 local config dict from simplified JSON credential blocks.

    Required: local_llm_json, local_embedder_json, local_vector_db_json
    Optional: local_reranker_json, local_graph_db_json
    """
    # Create a cache key from credentials to detect if config was already built
    try:
        cred_str = json.dumps(credentials, sort_keys=True)
        cache_key = hashlib.md5(cred_str.encode()).hexdigest()  # noqa: S324
    except Exception:  # noqa: BLE001
        # If serialization fails, don't cache
        cache_key = None

    # Check cache first
    if cache_key and cache_key in _built_config_cache:
        return _built_config_cache[cache_key]

    # Build new config
    with _build_config_lock:
        # Double-check after acquiring lock
        if cache_key and cache_key in _built_config_cache:
            return _built_config_cache[cache_key]

        logger.info("Building Mem0 local configuration from credentials")
        llm = _parse_json_block(credentials.get("local_llm_json"), "local_llm_json")
        embedder = _parse_json_block(credentials.get("local_embedder_json"), "local_embedder_json")
        vector_store = _parse_json_block(
            credentials.get("local_vector_db_json"), "local_vector_db_json",
        )

        if llm is None:
            msg = "LLM configuration (local_llm_json) is required in Local mode"
            _raise_config_error(msg)
        if embedder is None:
            msg = "Embedder configuration (local_embedder_json) is required in Local mode"
            _raise_config_error(msg)
        if vector_store is None:
            msg = "Vector Database configuration (local_vector_db_json) is required in Local mode"
            _raise_config_error(msg)

        # Normalize pgvector config shape if necessary
        if (
            vector_store.get("provider") == "pgvector"
            and isinstance(vector_store.get("config"), dict)
        ):
            logger.debug("Normalizing pgvector configuration")
            vector_store["config"] = _normalize_pgvector_config(
                vector_store["config"],
            )  # type: ignore[index]

        reranker = _parse_json_block(
            credentials.get("local_reranker_json"), "local_reranker_json",
        )
        graph_store = _parse_json_block(
            credentials.get("local_graph_db_json"), "local_graph_db_json",
        )

        config: dict[str, Any] = {
            "llm": llm,
            "embedder": embedder,
            "vector_store": vector_store,
        }
        if reranker:
            config["reranker"] = reranker
            logger.debug("Reranker configuration included")
        if graph_store:
            config["graph_store"] = graph_store
            logger.debug("Graph store configuration included")

        logger.info("Mem0 local configuration built successfully")

        # Cache the config if we have a valid cache key
        if cache_key:
            _built_config_cache[cache_key] = config

        return config


def is_async_mode(credentials: dict[str, Any]) -> bool:
    """Read async_mode from credentials and coerce to boolean.

    Defaults to True (异步模式). Accepts common truthy/falsey string values.
    """
    value = credentials.get("async_mode")
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "1", "yes", "y", "on"}:
            return True
        if text in {"false", "0", "no", "n", "off"}:
            return False
    # Default: async enabled
    return True
