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

- [x] New plugin submission

- [ ] Version update for existing plugin

## 3. Description

<!-- Please briefly describe the purpose of the new plugin or the updates made to the existing plugin -->

This plugin integrates [Mem0 AI](https://mem0.ai)'s intelligent memory layer into Dify, providing comprehensive memory management capabilities for AI applications. The plugin operates exclusively in **local mode**, allowing users to configure and manage their own LLM, embedding models, vector databases, graph databases, and rerankers.

### Key Features:

- **8 Complete Memory Management Tools**:
  - Add Memory - Intelligently add, update, or delete memories based on user interactions
  - Search Memory - Search with advanced filters (AND/OR logic) and top_k limiting
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
  - Database connection pool optimization for high concurrency
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

- **README.md**: Includes comprehensive installation guide, configuration examples, usage examples, and links to Mem0 official documentation
- **INSTALL.md**: Detailed installation and configuration guide in Chinese
- **GUIDE.md**: Configuration guide with detailed examples
- **PRIVACY.md**: Complete privacy policy explaining local mode operation
- **CHANGELOG.md**: Detailed version history and changes

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

All API keys and credentials are stored locally in the user's Dify instance configuration and are not shared with any third parties. The plugin only communicates with services configured by the user (their LLM, embedding, and database services).

### Privacy Policy

- [x] I confirm that I have prepared and included a privacy policy in my plugin package based on the Plugin Privacy Protection Guidelines

**Privacy Policy Location**: `PRIVACY.md` is included in the plugin package and clearly explains:
- Local mode operation and data storage
- Information processed by the plugin
- User's complete control over data
- No third-party data sharing
- User's responsibility for data security and compliance

