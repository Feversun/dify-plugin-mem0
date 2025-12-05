# Plugin Submission Form

## 1. Metadata

<!--
Please provide the following metadata of your plugin to make it easier for the reviewer to check the changes.

  - Plugin Author : The author of the plugin which is defined in your manifest.yaml

  - Plugin Name   : The name of the plugin which is defined in your manifest.yaml

  - Repository URL: The URL of the repository where the source code of your plugin is hosted

-->

- **Plugin Author**: beersoccer

- **Plugin Name**: mem0ai

- **Repository URL**: https://github.com/beersoccer/mem0_dify_plugin

## 2. Submission Type

- [ ] New plugin submission

- [x] Version update for existing plugin

## 3. Description

<!-- Please briefly describe the purpose of the new plugin or the updates made to the existing plugin -->

This version update (v0.1.6) brings significant security enhancements and production-ready performance optimizations to the Mem0 Dify Plugin. The plugin integrates [Mem0 AI](https://mem0.ai)'s intelligent memory layer into Dify, providing comprehensive memory management capabilities for AI applications. The plugin operates exclusively in **local mode**, allowing users to configure and manage their own LLM, embedding models, vector databases, graph databases, and rerankers.

### What's New in v0.1.6:

- **🔒 Security Enhancement**: All sensitive configuration fields now use `secret-input` type to protect API keys and credentials in the Dify UI
  - All JSON configuration fields (`local_llm_json`, `local_embedder_json`, `local_vector_db_json`, `local_graph_db_json`, `local_reranker_json`) are now hidden in the UI
  - Sensitive information (API keys, passwords, tokens) is protected from accidental exposure

- **⚙️ User-Configurable Performance Parameters**: Added three new optional configuration parameters for production environments
  - `max_concurrent_memory_operations` - Control maximum concurrent async operations (default: 40, recommended > 20 for production)
  - `pgvector_min_connections` - Set PGVector connection pool minimum size (default: 10)
  - `pgvector_max_connections` - Set PGVector connection pool maximum size (default: 40, recommended to match max_concurrent_memory_operations)

- **🐛 Bug Fixes**: Fixed Dify plugin framework compatibility issue (changed `type: number` to `type: text-input` for numeric configuration fields)

### Previous Updates (v0.1.5):

- **📅 Search Memory Timestamp Support**: Added timestamp field to search results, displaying the most recent timestamp (created_at or updated_at) in second precision format (`2025-11-03T20:06:27`)
- **🔧 Code Refactoring**: Created `utils/helpers.py` to centralize common utility functions for better code maintainability
- **✨ Code Quality Improvements**: Removed unused imports, fixed indentation errors, improved code organization

### Key Features:

- **8 Complete Memory Management Tools**:
  - Add Memory - Intelligently add, update, or delete memories based on user interactions
  - Search Memory - Search with advanced filters (AND/OR logic) and top_k limiting, returns timestamp field
  - Get All Memories - List memories with pagination
  - Get Memory - Fetch specific memory details
  - Update Memory - Modify existing memories
  - Delete Memory - Remove individual memories
  - Delete All Memories - Batch delete with filters
  - Get Memory History - View change history

- **Flexible Operation Modes**:
  - **Async Mode** (default): Recommended for production, supports high concurrency with non-blocking write operations
  - **Sync Mode**: Recommended for testing, all operations block until completion for immediate result visibility

- **Local-Only Architecture**:
  - All data stored in user's own infrastructure (vector database, graph database)
  - No data sent to external servers
  - Complete user control over data storage and processing

- **Production-Ready Features**:
  - Comprehensive timeout protection and service degradation
  - Robust error handling ensuring workflow continuity
  - Database connection pool optimization for high concurrency (now user-configurable)
  - Unified logging configuration for better debugging

### Configuration:

Users configure the plugin by:
1. Choosing operation mode (async/sync)
2. Providing JSON configurations for:
   - LLM provider (required)
   - Embedding model (required)
   - Vector database (required, e.g., pgvector)
   - Graph database (optional, e.g., Neo4j)
   - Reranker (optional)
3. (Optional) Configuring performance parameters for production environments

**Note**: All JSON configuration fields are displayed as password fields (hidden input) in the Dify UI to protect sensitive information.

For detailed configuration options, users are directed to the [Mem0 Official Configuration Documentation](https://docs.mem0.ai/open-source/configuration).

## 4. Checklist

- [x] I have read and followed the Publish to Dify Marketplace guidelines

- [x] I have read and comply with the Plugin Developer Agreement

- [x] I confirm my plugin works properly on both Dify Community Edition and Cloud Version

- [x] I confirm my plugin has been thoroughly tested for completeness and functionality

- [x] My plugin brings new value to Dify

## 5. Documentation Checklist

Please confirm that your plugin README includes all necessary information:

- [x] Step-by-step setup instructions

- [x] Detailed usage instructions

- [x] All required APIs and credentials are clearly listed

- [x] Connection requirements and configuration details

- [x] Link to the repository for the plugin source code

**Documentation Details:**

- **README.md**: Project overview, quick start guide, feature highlights, and brief usage examples with references to detailed documentation
- **CONFIG.md**: Complete installation and configuration guide with detailed examples for all providers, troubleshooting, and operational notes
- **PRIVACY.md**: Complete privacy policy explaining local mode operation and data handling
- **CHANGELOG.md**: Detailed version history and changes for all versions

**Documentation Improvements in v0.1.6:**
- Eliminated duplicate content across markdown files
- Established clear cross-references between documents
- Added comprehensive configuration examples for all supported providers
- Updated all examples to use placeholder values (no sensitive information)
- Enhanced troubleshooting section with production-specific guidance

All configuration examples follow the format specified in Mem0 official documentation, and users are directed to the official docs for advanced configuration options.

## 6. Privacy Protection Information

Based on Dify Plugin Privacy Protection [Guidelines](https://docs.dify.ai/plugins/publish-plugins/publish-to-dify-marketplace/plugin-privacy-protection-guidelines):

### Data Collection

**No user personal data is collected by this plugin.**

This plugin operates exclusively in **local mode**, which means:

- **All data is stored in the user's own infrastructure** - Users configure and manage their own vector database and graph database
- **No data is sent to external servers** - All processing happens locally using user-configured services (LLM, embedding models, databases)
- **Complete user control** - Users have full control over where and how their data is stored

The plugin only processes:
- Conversation history (chat messages) - stored in user's own vector database
- User IDs, Agent IDs, Run IDs - used for data partitioning and scoping within user's own database
- Message metadata (timestamps, roles) - stored in user's own database

**No personal identification information (PII) is required or collected beyond user-provided identifiers (user_id, agent_id, run_id).**

**Security Enhancements in v0.1.6:**
- All sensitive configuration fields (API keys, passwords, tokens) are now hidden in the Dify UI using `secret-input` type
- Configuration fields appear as password fields (hidden input) to prevent accidental exposure
- No functional changes to data handling - only UI display behavior improved for security

All API keys and credentials are stored locally in the user's Dify instance configuration and are not shared with any third parties. The plugin only communicates with services configured by the user (their LLM, embedding, and database services).

### Privacy Policy

- [x] I confirm that I have prepared and included a privacy policy in my plugin package based on the Plugin Privacy Protection Guidelines

**Privacy Policy Location**: `PRIVACY.md` is included in the plugin package and clearly explains:
- Local mode operation and data storage
- Information processed by the plugin
- User's complete control over data
- No third-party data sharing
- User's responsibility for data security and compliance

