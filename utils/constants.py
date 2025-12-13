"""Project-wide constants for mem0 Dify plugin."""

# Standardized add-operation return shapes
ADD_SKIP_RESULT: dict[str, object] = {
    "results": [
        {
            "id": "",
            "memory": "",
            "event": "SKIP",
        },
    ],
}

ADD_ACCEPT_RESULT: dict[str, object] = {
    "results": [
        {
            "id": "",
            "memory": "",
            "event": "ACCEPT",
        },
    ],
}

UPDATE_ACCEPT_RESULT: dict[str, object] = {
    "results": {
        "message": "Memory update has been accepted",
    },
}

DELETE_ACCEPT_RESULT: dict[str, object] = {
    "results": {
        "message": "Memory deletion has been accepted",
    },
}

DELETE_ALL_ACCEPT_RESULT: dict[str, object] = {
    "results": {
        "message": "Batch memory deletion has been accepted",
    },
}

# The maximum timeout (in seconds) for a single request, to avoid long waits or hanging connections.
MAX_REQUEST_TIMEOUT: int = 60

# Operation timeouts (in seconds) for individual Mem0 operations
# These should be less than MAX_REQUEST_TIMEOUT to allow for error handling
SEARCH_OPERATION_TIMEOUT: int = 30
GET_OPERATION_TIMEOUT: int = 30
GET_ALL_OPERATION_TIMEOUT: int = 30
HISTORY_OPERATION_TIMEOUT: int = 30

# Concurrency controls
# Maximum concurrent async memory operations per process to avoid exhausting DB/vector store pools
# Applies to all async operations: search, add, get, get_all, update, delete, delete_all, history
MAX_CONCURRENT_MEMORY_OPERATIONS: int = 40
# Warn when semaphore wait exceeds this threshold (milliseconds)
SEMAPHORE_WAITING_THRESHOLD: float = 100.0

# Database connection pool settings for pgvector
# These values should align with MAX_CONCURRENT_MEMORY_OPERATIONS to ensure sufficient connections
PGVECTOR_MIN_CONNECTIONS: int = 10  # Minimum number of connections in the pool
# Maximum number of connections in the pool (should match MAX_CONCURRENT_MEMORY_OPERATIONS)
PGVECTOR_MAX_CONNECTIONS: int = 40

# Default top_k for search
SEARCH_DEFAULT_TOP_K: int = 5
