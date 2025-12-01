# Mem0 Dify Plugin - Changelog

## Version 0.1.4 (2025-11-23)

### 🔍 Logging Investigation & Documentation Update

This release documents logging-related investigations and discussions, with no code changes.

#### Highlights
- **Logging Issue Investigation**: Identified and documented logging output behavior
  - Discovered that logs may appear twice in command line output (JSON format from Dify plugin handler and standard format from Python root logger)
  - Identified Unicode encoding in JSON format logs (Chinese characters displayed as `\uXXXX` format)
  - Investigated potential solutions including disabling logger propagation and custom formatters
- **Documentation Updates**: Updated all markdown files to reflect current version and maintain consistency

#### 🔧 Technical Details
- **Logging Behavior Analysis**:
  - Dify's `plugin_logger_handler` outputs logs in JSON format: `{"event": "log", "data": {"level": "INFO", "message": "...", "timestamp": ...}}`
  - Python's root logger may also output logs in standard format: `INFO:tools.update_memory:...`
  - This can result in duplicate log output when logger propagation is enabled
  - JSON format uses `ensure_ascii=True` by default, causing Unicode characters to be encoded as `\uXXXX`
- **Investigation Notes**:
  - Considered setting `logger.propagate = False` to prevent duplicate logs
  - Considered custom formatter with standard format and timestamp
  - Current implementation uses Dify's official plugin logger handler as-is

#### ⚠️ Known Issues
- Logs may appear twice in command line output (JSON format + standard format)
- JSON format logs display Chinese characters as Unicode escape sequences (`\uXXXX`)
- These are framework-level behaviors from Dify's plugin logger handler

#### 📝 Notes
- No code changes in this release
- Documentation updated to maintain consistency across all markdown files
- Version number incremented to 0.1.4

---

## Version 0.1.3 (2025-11-22)

### 🎯 Logging, Configuration & Database Connection Pool Optimization

This release focuses on improving logging infrastructure, optimizing configuration handling, and enhancing database connection pool management for better production stability.

#### Highlights
- **Unified Logging Configuration**: Implemented centralized logging using Dify's official plugin logger handler (`plugin_logger_handler`) to ensure all logs are properly output to the Dify plugin container
  - Created `utils/logger.py` module with `get_logger()` function for consistent logger initialization
  - All Python modules now use the unified logger configuration
  - Logs are correctly routed to Dify's logging system for better debugging and monitoring
- **Constant Naming Optimization**: Renamed `MAX_CONCURRENT_MEM_ADDS` to `MAX_CONCURRENT_MEMORY_OPERATIONS` to accurately reflect its purpose
  - The constant controls concurrency for all async memory operations (search, add, get, get_all, update, delete, delete_all, history), not just add operations
  - Updated default value from 5 to 40 to support higher concurrency
- **Database Connection Pool Configuration**: Added automatic connection pool settings for pgvector
  - New constants: `PGVECTOR_MIN_CONNECTIONS` (10) and `PGVECTOR_MAX_CONNECTIONS` (40)
  - Connection pool settings are automatically applied when initializing pgvector if not explicitly provided
  - Pool size aligns with `MAX_CONCURRENT_MEMORY_OPERATIONS` to ensure sufficient database connections
- **PGVector Configuration Optimization**: Enhanced pgvector configuration handling according to Mem0 official documentation
  - Properly handles parameter priority: `connection_pool` (highest) > `connection_string` > individual parameters
  - Automatically builds `connection_string` from discrete parameters (dbname, user, password, host, port, sslmode)
  - Cleans up redundant connection parameters based on priority
  - Preserves all valid pgvector config keys (collection_name, embedding_model_dims, diskann, hnsw, etc.)

#### 🔧 Technical Details
- **Logging Infrastructure**:
  - Created `utils/logger.py` with `get_logger(name: str)` function
  - Uses `dify_plugin.config.logger_format.plugin_logger_handler` for proper log routing
  - All tool files, utility modules, and main.py updated to use unified logger
  - Prevents duplicate log handlers with `if not logger.handlers` check
- **Constants Updates**:
  - Renamed `MAX_CONCURRENT_MEM_ADDS` → `MAX_CONCURRENT_MEMORY_OPERATIONS` (default: 40)
  - Added `PGVECTOR_MIN_CONNECTIONS: int = 10`
  - Added `PGVECTOR_MAX_CONNECTIONS: int = 40`
- **PGVector Configuration**:
  - Updated `_normalize_pgvector_config()` to handle three connection methods with proper priority
  - Automatically sets `minconn` and `maxconn` if not provided in user configuration
  - Supports both `connection_string` and discrete parameter forms
  - Validates and preserves all official pgvector config keys

#### ⚠️ Migration Notes
- No breaking changes in API or behavior
- Constant name change: `MAX_CONCURRENT_MEM_ADDS` → `MAX_CONCURRENT_MEMORY_OPERATIONS` (internal only, no user impact)
- Connection pool settings are automatically applied to pgvector configurations
- If custom connection pool settings are needed, they can be explicitly set in pgvector config

#### 🐛 Bug Fixes
- Fixed logging output routing to ensure logs appear in Dify plugin container
- Fixed constant naming to accurately reflect its purpose
- Improved pgvector configuration handling to match Mem0 official documentation

---

## Version 0.1.2 (2025-11-21)

### 🎯 Configurable Timeout & Code Quality Improvements

This release introduces configurable timeout parameters for all read operations and optimizes default timeout values for better performance and reliability.

#### Highlights
- **Configurable Timeout Parameters**: All read operations (Search/Get/Get_All/History) now support user-configurable timeout values through the Dify plugin configuration interface
  - Timeout parameters are set as `form: form` (manual input), not exposed to LLM for inference
  - If not specified, tools use default values from `constants.py`
  - Allows users to customize timeout behavior per tool based on their specific needs
- **Optimized Default Timeouts**: Reduced default timeout values for better responsiveness:
  - `MAX_REQUEST_TIMEOUT`: 120 seconds → **60 seconds**
  - `SEARCH_OPERATION_TIMEOUT`: 60 seconds → **30 seconds**
  - `GET_ALL_OPERATION_TIMEOUT`: 60 seconds → **30 seconds**
  - `GET_OPERATION_TIMEOUT`: 30 seconds → **30 seconds** (unchanged)
  - `HISTORY_OPERATION_TIMEOUT`: 30 seconds → **30 seconds** (unchanged)
- **Code Quality**: Added missing module and class docstrings, fixed formatting issues to comply with Python best practices

#### 🔧 Technical Details
- **Timeout Configuration**:
  - Added `timeout` parameter to `search_memory.yaml`, `get_all_memories.yaml`, `get_memory.yaml`, `get_memory_history.yaml`
  - Parameters are optional and use `form: form` (manual configuration, not LLM inference)
  - Tools read timeout from `tool_parameters.get("timeout")` and fall back to constants if not provided
  - Invalid timeout values are caught and logged with a warning, defaulting to constants
- **Default Timeout Values**:
  - All read operations now default to 30 seconds (previously 60s for Search/Get_All)
  - `MAX_REQUEST_TIMEOUT` reduced to 60 seconds for faster failure detection
- **Code Quality**:
  - Added module docstrings to all tool files
  - Added class docstrings to all tool classes
  - Fixed formatting issues (blank lines after class docstrings)

#### ⚠️ Migration Notes
- No breaking changes in API or behavior
- Default timeout values have changed (60s → 30s for Search/Get_All operations)
- Users can now configure custom timeout values per tool in the Dify plugin configuration interface
- If custom timeout values are needed, they should be set in the tool configuration

#### 🐛 Bug Fixes
- Fixed missing module and class docstrings in tool files
- Fixed formatting issues (missing blank lines after class docstrings)

---

## Version 0.1.1 (2025-11-20)

### 🎯 Production Stability & Timeout Protection

This release addresses critical production issues where tools would hang indefinitely, implementing comprehensive timeout mechanisms and service degradation strategies to ensure reliable operation in production environments.

#### Highlights
- **Timeout Protection**: Added timeout mechanisms for all async read operations (Search/Get/Get_All/History) to prevent indefinite hanging
  - Search Memory: 60 seconds timeout
  - Get All Memories: 60 seconds timeout
  - Get Memory: 30 seconds timeout
  - Get Memory History: 30 seconds timeout
- **Service Degradation**: When operations timeout or encounter errors, the plugin gracefully degrades by:
  - Logging the event with full exception details
  - Cancelling background tasks to prevent resource leaks
  - Returning default/empty results (empty list `[]` for Search/Get_All/History, `None` for Get)
  - Ensuring Dify workflow continues execution without interruption
- **Robust Error Handling**: Enhanced exception handling to catch all error types (network errors, connection failures, SSL errors, etc.), not just specific exceptions
- **Resource Management**: Improved background task cancellation on timeout using `future.cancel()` to prevent hanging tasks and resource leaks

#### 🔧 Technical Details
- **Timeout Implementation**:
  - Added timeout constants in `utils/constants.py`: `SEARCH_OPERATION_TIMEOUT`, `GET_OPERATION_TIMEOUT`, `GET_ALL_OPERATION_TIMEOUT`, `HISTORY_OPERATION_TIMEOUT`
  - Applied timeouts to `future.result(timeout=...)` calls in all async read operations
  - Used `concurrent.futures.TimeoutError` (aliased as `FuturesTimeoutError`) for correct exception handling
  - **Note**: Sync mode has no timeout protection (blocking calls). If timeout protection is needed, use `async_mode=true`
- **Service Degradation**:
  - All tools now initialize result variables with default values before `try` blocks
  - Timeout handlers call `future.cancel()` to prevent background tasks from hanging
  - Exception handlers catch all `Exception` types, not just specific ones
  - Tools return empty/default results on any error to ensure workflow continuity
- **Unified Exception Handling**:
  - Removed redundant outer `except FuturesTimeoutError` blocks (sync mode doesn't throw this exception)
  - Unified exception handling pattern: async mode handles timeout and general exceptions, sync mode handles general exceptions only
  - Both modes implement service degradation (return default/empty results) to ensure workflow continuity
- **Code Quality**:
  - Ensured `ensure_bg_loop()` guarantees a long-lived, reusable event loop
  - Added comprehensive documentation for timeout and service degradation mechanisms
  - Improved error logging with `logger.exception` for detailed stack traces
  - Simplified code structure by removing duplicate exception handling blocks

#### ⚠️ Migration Notes
- No breaking changes in API or behavior
- Tools now have timeout protection, which may cause operations to return empty results if they exceed timeout limits
- Workflows should handle empty results gracefully (which they already should)
- Production environments will benefit from improved stability and reliability

#### 🐛 Bug Fixes
- Fixed production issue where `Search memory` tool would hang indefinitely without proper termination
- Fixed issue where tools would fail without proper error handling, causing workflow interruptions
- Fixed resource leaks from hanging background tasks after timeouts

---

## Version 0.1.0 (2025-11-19)

### 🎯 Smart Memory Management & Robustness

This release transforms the `add_memory` tool into a smart memory manager and significantly improves the plugin's stability by handling edge cases and race conditions.

#### Highlights
- **Smart Memory Management**: The `add_memory` tool description has been updated to reflect its true capability. It leverages Mem0's intelligence to automatically decide whether to add, update, or delete memories based on user interaction context.
- **Robust Error Handling**: Operations on non-existent memories (Get/Update/Delete) now return clear, friendly error messages instead of crashing with internal Python exceptions.
- **Race Condition Protection**: Implemented a multi-layer defense mechanism for `update` and `delete` operations to handle concurrent modifications safely.

#### 🔧 Technical Details
- **Tool Updates**:
  - `add_memory`: Updated YAML description to emphasize intelligent memory management (Add/Update/Delete).
  - `get_all_memories`: Fixed a bug where results were empty due to incorrect parsing of Mem0's dictionary response format.
  - `get_memory`: Added checks for `None` results to prevent `AttributeError`.
  - `update_memory` / `delete_memory`: Added pre-checks and internal `try-except` blocks to catch `AttributeError` caused by Mem0's internal race conditions when operating on deleted memories.
- **Documentation**:
  - Added "Important Notes" section in README/GUIDE about `delete_all` triggering "Resetting index" warnings (normal behavior).
  - Clarified vector store connection settings for Debug vs Production modes.

#### ⚠️ Migration Notes
- No breaking changes in API.
- `add_memory` tool description is updated, but the tool name and label remain "Add Memory".

---

## Version 0.0.9 (2025-11-17)

### 🎯 Unified Return Format & Enhanced Async Operations

This release focuses on standardizing tool outputs and extending non-blocking async behavior to all write operations.

#### Highlights
- **Unified JSON Return Structure**:
  - All tools now return consistent format: `{"status": "SUCCESS/ERROR", "messages": {...}, "results": {...}}`
  - `status`: Operation status (SUCCESS or ERROR)
  - `messages`: Context information (query params, filters, IDs, etc.)
  - `results`: Actual data (memories, history, operation results)
  
- **Enhanced Async Operations**:
  - Write operations (Add/Update/Delete/Delete_All) are now non-blocking in async mode
  - Return ACCEPT messages immediately: `UPDATE_ACCEPT_RESULT`, `DELETE_ACCEPT_RESULT`, `DELETE_ALL_ACCEPT_RESULT`
  - Read operations (Search/Get/Get_All/History) always wait for results
  
- **Standardized Return Fields**:
  - Search/Get/Get_All: `id`, `memory`, `metadata`, `created_at`, `updated_at`
  - History: `memory_id`, `old_memory`, `new_memory`, `event`, `created_at`, `updated_at`, `is_deleted`
  - Removed redundant fields: `hash`, `user_id`, `agent_id`, `run_id` from individual memory objects
  
- **Extended Constants** (`utils/constants.py`):
  - Added `UPDATE_ACCEPT_RESULT`: `{"message": "Memory update has been accepted"}`
  - Added `DELETE_ACCEPT_RESULT`: `{"message": "Memory deletion has been accepted"}`
  - Added `DELETE_ALL_ACCEPT_RESULT`: `{"message": "Batch memory deletion has been accepted"}`
  
- **Complete Documentation**:
  - All methods in `LocalClient` and `AsyncLocalClient` now have comprehensive docstrings
  - Consistent parameter descriptions and return value documentation
  - Clear async vs sync behavior documentation

#### Technical Details
- **Async Mode Behavior**:
  - When `async_mode=true` (default):
    - Add/Update/Delete/Delete_All: Submit to background loop without waiting, return ACCEPT status
    - Search/Get/Get_All/History: Wait for results via `asyncio.run_coroutine_threadsafe().result()`
  - When `async_mode=false`:
    - All operations use `LocalClient` and block until completion
    
- **Error Handling**:
  - All error responses include `"results": []` for consistency
  - Exception types unified: `(ValueError, RuntimeError, TypeError)`

#### Migration Notes
- Tool outputs now use `status` instead of `event` for top-level status indicator
- If your workflow parses tool outputs, update to use the new field names
- Async write operations now return ACCEPT messages instead of actual results

---

## Version 0.0.8 (2025-11-11)

- Add async_mode provider credential (default true) with clear runtime behavior
- Tools route to LocalClient/AsyncLocalClient based on async_mode for all operations
- Provider validation aligns with async_mode
- Docs updated (README/INSTALL/GUIDE/manifest) to reflect async vs sync behavior

## Version 0.0.7 (2025-11-08)

### 🚀 Local-only, async client, graceful shutdown

This release focuses on stability, local-only operation, and developer ergonomics.

#### Highlights
- Centralized constants in `utils/constants.py`:
  - `MAX_CONCURRENT_MEMORY_OPERATIONS` (default: 5, renamed from MAX_CONCURRENT_MEM_ADDS)
  - `SEARCH_DEFAULT_TOP_K` (default: 5)
  - `MAX_REQUEST_TIMEOUT` (default: 120)
  - Shared response shapes: `ADD_SKIP_RESULT`, `ADD_ACCEPT_RESULT`
  - `CUSTOM_PROMPT` for memory distillation (optional)
- Background event loop:
  - Single process-wide loop created once and reused
  - Tools dispatch async operations via `asyncio.run_coroutine_threadsafe(...)`
- Graceful shutdown:
  - `AsyncLocalClient.shutdown()` drains pending tasks briefly and stops the loop
  - Registered via `atexit` and SIGTERM/SIGINT in `main.py`
- Non-blocking add:
  - `AddMem0Tool` enqueues add and returns immediately with `{"status": "queued", ...}`
  - Skips empty/blank messages with `{"status": "skipped", "reason": "no messages", ...}`
- Search improvements:
  - Executes on the background loop
  - Returns normalized JSON and a detailed text message for downstream nodes

#### Removals/Cleanups
- SaaS mode and API version parameters removed
- Deprecated `run_async_task` and background task tracking removed
- Input validation for empty messages centralized in tool layer

---

## Version 0.0.3 (2025-10-05)

### 🎉 Major Update: Full Mem0 API v2 Support

This version brings complete support for Mem0's latest API features, including v2 advanced filtering and full CRUD operations.

---

## ✨ New Features

### 📦 6 New Tools Added

1. **Get All Memories** (`get_all_memories`)
   - Retrieve all memories for a user, agent, app, or run
   - Supports pagination with limit parameter
   - Multi-entity filtering support

2. **Get Memory** (`get_memory`)
   - Fetch a specific memory by its ID
   - Returns complete memory details including metadata

3. **Update Memory** (`update_memory`)
   - Update existing memory content
   - Preserves memory metadata and entity associations

4. **Delete Memory** (`delete_memory`)
   - Delete a specific memory by ID
   - Safe deletion with confirmation

5. **Delete All Memories** (`delete_all_memories`)
   - Batch delete memories by entity filters
   - Requires at least one entity ID for safety

6. **Get Memory History** (`get_memory_history`)
   - View complete change history of a memory
   - Shows previous and new values for each change

---

## 🔄 Enhanced Existing Tools

### **Add Memory** (Enhanced)
**New Parameters:**
- `agent_id` - Associate memory with an agent
- `app_id` - Associate memory with an application
- `run_id` - Associate memory with a specific run
- `metadata` - Custom metadata as JSON string
- `output_format` - Choose between v1.0, v1.1, or v2 output formats

**Breaking Changes:**
- `user_id` is now optional (at least one entity ID should be provided)

### **Search Memory** (Enhanced)
**New Parameters:**
- `agent_id` - Filter by agent ID
- `run_id` - Filter by run ID
- `filters` - Advanced AND/OR logic filters (JSON string)
- `top_k` - Maximum number of results

**Advanced Filters Example:**
```json
{
  "AND": [
    {"user_id": "alex"},
    {
      "OR": [
        {"agent_id": "travel_agent"},
        {"agent_id": "food_agent"}
      ]
    }
  ]
}
```

---

## 🌟 Key Improvements

### Multi-Entity Support
All tools now support multiple entity types:
- `user_id` - User-specific memories (required for add_memory)
- `agent_id` - Agent-specific memories
- `run_id` - Run-specific memories

### Metadata Support
- Add custom metadata when creating memories
- Retrieve and filter by metadata
- Supports any JSON-serializable data

### Output Format
- Choose output format (v1.0/v1.1/v2) via `output_format` parameter
- Different formats provide varying levels of detail
- Default is v1.1

### Enhanced Error Handling
- Better error messages for invalid JSON
- Clear validation for required parameters
- HTTP status code specific error handling

---

## 📋 Complete Tool List

### Memory Management (8 Tools)
1. ✅ Add Memory - Create new memories
2. ✅ Search Memory - Search memories with advanced filters
3. ✅ Get All Memories - List all memories
4. ✅ Get Memory - Get single memory details
5. ✅ Update Memory - Modify existing memories
6. ✅ Delete Memory - Remove single memory
7. ✅ Delete All Memories - Batch delete memories
8. ✅ Get Memory History - View memory change history

---

## 🔧 Technical Details

### Local Mode Implementation
- This plugin runs in **Local-only** mode using Mem0 SDK
- All operations use local Mem0 client (not HTTP API)
- Requires local configuration for LLM, Embedder, and Vector DB

### Dependencies
- `mem0` - Mem0 SDK for local mode
- `dify_plugin` - Dify plugin framework
- Python 3.12

### Configuration Updates
- Updated `provider/mem0.yaml` with all 8 tools
- Updated `manifest.yaml` to version 0.0.3
- Enhanced tool descriptions with local mode features

---

## 🌍 Internationalization

All new features include complete translations:
- 🇺🇸 English (en_US)
- 🇨🇳 Simplified Chinese (zh_Hans)
- 🇧🇷 Portuguese (pt_BR)
- 🇯🇵 Japanese (ja_JP)

---

## 🚀 Migration Guide

### From v0.0.2 to v0.0.3

**Breaking Changes:**
1. `user_id` in `add_memory` is required
   - **Action**: Always provide `user_id` when adding memories

2. `user_id` in `search_memory` is required
   - **Action**: Always provide `user_id` when searching memories

**Recommended Updates:**
1. Start using `metadata` for richer context
2. Migrate to v2 API for advanced filtering
3. Use entity IDs to organize memories by context

**Backward Compatibility:**
- All v0.0.2 workflows continue to work
- No code changes required for existing implementations
- New parameters are optional

---

## 📚 Usage Examples

### Example 1: Add Memory with Metadata
```json
{
  "user": "I love Italian food",
  "assistant": "Great! I'll remember that.",
  "user_id": "alex",
  "agent_id": "food_assistant",
  "metadata": "{\"category\": \"food_preferences\", \"cuisine\": \"italian\"}"
}
```

### Example 2: Advanced Search with v2 Filters
```json
{
  "query": "What are my food preferences?",
  "version": "v2",
  "filters": "{\"AND\": [{\"user_id\": \"alex\"}, {\"agent_id\": \"food_assistant\"}]}"
}
```

### Example 3: Get All Memories for an Agent
```json
{
  "agent_id": "travel_assistant",
  "limit": 50
}
```

---

## 🐛 Bug Fixes
- Fixed JSON parsing errors with better error messages
- Improved HTTP status code handling
- Enhanced validation for required parameters

---

## 📝 Notes

- Plugin runs in Local-only mode (no SaaS/API mode)
- All operations use Mem0 SDK (not HTTP API)
- JSON responses include both structured data and human-readable text
- Supports all Mem0 Local mode features

---

## 🙏 Credits

- Based on [Mem0 AI](https://mem0.ai) SDK and documentation
- Compatible with Dify Plugin Framework

---

## 📞 Support

For issues or questions:
- Check the official [Mem0 Documentation](https://docs.mem0.ai)
- Review the tool YAML files for parameter details
- Test with Dify Plugin Debugger

---

**Full Changelog**: v0.0.2 → v0.0.3
