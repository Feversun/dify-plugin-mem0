# Mem0 Dify Plugin - Configuration Guide

This guide provides detailed configuration instructions for the Mem0 Dify Plugin.

## Installation

Follow the official Dify plugin installation guide:
1. Go to `Settings` → `Plugins` in Dify Dashboard
2. Install the plugin from GitHub or upload the plugin package
3. Wait for installation to complete

## Configuration Steps

### Step 1: Choose Operation Mode

First, select the operation mode in plugin credentials:

- **Async Mode** (`async_mode=true`, default)
  - Recommended for production environments
  - Supports high concurrency
  - Write operations (Add/Update/Delete/Delete_All): non-blocking, return ACCEPT status immediately
  - Read operations (Search/Get/Get_All/History): wait for results with timeout protection (default: 30s)

- **Sync Mode** (`async_mode=false`)
  - Recommended for testing environments
  - All operations block until completion
  - You can see the actual results of each memory operation immediately
  - **Note**: Sync mode has no timeout protection. If timeout protection is needed, use `async_mode=true`

### Step 2: Configure Models and Databases

Configure the following JSON blocks in plugin settings. Each JSON must be a map with shape: `{ "provider": <string>, "config": { ... } }`. For detailed configuration options and supported providers, refer to the [Mem0 Official Configuration Documentation](https://docs.mem0.ai/open-source/configuration).

**Required:**
- `local_llm_json` - LLM provider configuration
- `local_embedder_json` - Embedding model configuration
- `local_vector_db_json` - Vector database configuration

**Optional:**
- `local_graph_db_json` - Graph database configuration (e.g., Neo4j)
- `local_reranker_json` - Reranker configuration

## Configuration Examples

> **📚 Reference**: For detailed configuration options and supported providers, please refer to the [Mem0 Official Configuration Documentation](https://docs.mem0.ai/open-source/configuration).

### LLM Configuration (`local_llm_json`)

```json
{
  "provider": "azure_openai",
  "config": {
    "model": "your-deployment-name",
    "temperature": 0.1,
    "max_tokens": 256,
    "azure_kwargs": {
      "azure_deployment": "your-deployment-name",
      "api_version": "version-to-use",
      "azure_endpoint": "your-api-base-url",
      "api_key": "your-api-key",
      "default_headers": {
        "CustomHeader": "your-custom-header"
      }
    }
  }
}
```

### Embedder Configuration (`local_embedder_json`)

```json
{
  "provider": "azure_openai",
  "config": {
    "model": "your-deployment-name",
    "azure_kwargs": {
      "api_version": "version-to-use",
      "azure_deployment": "your-deployment-name",
      "azure_endpoint": "your-api-base-url",
      "api_key": "your-api-key",
      "default_headers": {
        "CustomHeader": "your-custom-header"
      }
    }
  }
}
```

### Vector Store Configuration (`local_vector_db_json`)

```json
{
  "provider": "pgvector",
  "config": {
    "dbname": "your-vector-db-name",
    "user": "your-vector-db-user",
    "password": "your-vector-db-password",
    "host": "your-vector-db-host",
    "port": "your-vector-db-port",
    "sslmode": "require or disable"
  }
}
```

### Graph Store Configuration (`local_graph_db_json`) - Optional

```json
{
  "provider": "neo4j",
  "config": {
    "url": "neo4j+s://<HOST>",
    "username": "your-graph-db-user",
    "password": "your-graph-db-password"
  }
}
```

### Reranker Configuration (`local_reranker_json`) - Optional

```json
{
  "provider": "cohere",
  "config": {
    "model": "your-model-name",
    "api_key": "your-cohere-api-key",
    "top_k": 5
  }
}
```

## Runtime Behavior

### Async Mode (`async_mode=true`, default)

- **Write Operations** (Add/Update/Delete/Delete_All):
  - Non-blocking, return ACCEPT status immediately
  - Operations are performed in the background
  - Best for production environments with high traffic

- **Read Operations** (Search/Get/Get_All/History):
  - Wait for results and return actual data
  - **Timeout protection**: All async read operations have timeout mechanisms (default: 30s, configurable)
  - On timeout or error: logs event, cancels background tasks, returns default/empty results

### Sync Mode (`async_mode=false`)

- **All Operations**:
  - Block until completion
  - You can see the actual results of each operation immediately
  - Best for testing and debugging
  - **Note**: No timeout protection. If timeout protection is needed, use `async_mode=true`

### Service Degradation

When operations timeout or encounter errors:
- The event is logged with full exception details
- Background tasks are cancelled to prevent resource leaks (async mode only)
- Default/empty results are returned (empty list `[]` for Search/Get_All/History, `None` for Get)
- Dify workflow continues execution without interruption

### Configurable Timeout (v0.1.2+)

All read operations (Search/Get/Get_All/History) support user-configurable timeout values:
- Timeout parameters are available in the Dify plugin configuration interface as manual input fields
- If not specified, tools use default values (30 seconds for all read operations)
- Invalid timeout values are caught and logged with a warning, defaulting to constants

### Default Timeout Values

- Search Memory: 30 seconds (configurable)
- Get All Memories: 30 seconds (configurable)
- Get Memory: 30 seconds (configurable)
- Get Memory History: 30 seconds (configurable)
- `MAX_REQUEST_TIMEOUT`: 60 seconds

**Note**: Sync mode has no timeout protection (blocking calls). If timeout protection is needed, use `async_mode=true`

## Important Operational Notes

### Delete All Memories Operation

> **Note**: When using the `delete_all_memories` tool to delete memories in batch, Mem0 will automatically reset the vector index to optimize performance and reclaim space. You may see a log message like `WARNING: Resetting index mem0...` during this operation. This is a **normal and expected behavior** — the warning indicates that the vector store table is being dropped and recreated to ensure optimal query performance after bulk deletion. No action is needed from your side.

### PGVector Configuration

- **Connection Pool**: Automatically configured with min=10, max=40 connections to align with concurrent operation limits
- **Parameter Priority**: The plugin handles pgvector configuration according to Mem0 official documentation:
  1. `connection_pool` (highest priority) - psycopg2 connection pool object
  2. `connection_string` (second priority) - PostgreSQL connection string
  3. Individual parameters (lowest priority) - user, password, host, port, dbname, sslmode
- **Automatic Connection String Building**: If discrete parameters are provided, the plugin automatically builds a `connection_string` and removes redundant parameters
- **Custom Pool Settings**: If `minconn` or `maxconn` are explicitly provided in pgvector config, they will be used instead of defaults

## Additional Resources

- **Privacy Policy**: See [PRIVACY.md](PRIVACY.md) for details about data handling in local mode
- **Changelog**: See [CHANGELOG.md](CHANGELOG.md) for detailed version history
- **Mem0 Official Docs**: https://docs.mem0.ai
- **Dify Plugin Docs**: https://docs.dify.ai/docs/plugins