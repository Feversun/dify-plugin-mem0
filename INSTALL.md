# Mem0 Dify Plugin v0.1.5 - 安装指南

## 📦 安装步骤

### 1. 安装插件

按照 Dify 官方插件安装指南进行安装：

1. **登录 Dify**
   - 访问你的 Dify 实例（自建或 Dify 云）
   - 例如：`https://your-dify-instance.com` 或 `https://cloud.dify.ai`

2. **进入插件管理**
   - 导航到 **Settings** → **Plugins**
   - 或直接访问 `/plugins` 路径

3. **安装插件**
   - 点击 **"Install from GitHub"** 或 **"上传插件"** 按钮
   - 如果从 GitHub 安装：输入仓库 URL
   - 如果从包安装：选择 `mem0ai-0.1.5.difypkg` 文件
   - 等待上传和安装完成

### 2. 配置插件

安装完成后，按照以下步骤配置插件：

#### 步骤 1：选择运行模式

首先选择插件的运行模式：

- **异步模式**（推荐用于生产环境）
  - 设置 `async_mode` 为 `true`（默认值）
  - 支持高并发
  - 写操作（Add/Update/Delete）非阻塞，立即返回
  - 读操作（Search/Get）等待结果，具有超时保护
  - 适合生产环境的高流量场景

- **同步模式**（推荐用于测试环境）
  - 设置 `async_mode` 为 `false`
  - 所有操作阻塞直到完成
  - 可以立即看到每次记忆操作的实际返回结果
  - 适合测试和调试
  - **注意**：同步模式没有超时保护。如果需要超时保护，请使用 `async_mode=true`

#### 步骤 2：配置模型和数据库

在插件设置中配置以下 JSON 块。详细的配置选项和支持的提供者，请参考 [Mem0 官方配置文档](https://docs.mem0.ai/open-source/configuration)。

**必填项：**
- `local_llm_json` - LLM 提供者配置
- `local_embedder_json` - 嵌入模型配置
- `local_vector_db_json` - 向量数据库配置

**可选项：**
- `local_graph_db_json` - 图数据库配置（如 Neo4j）
- `local_reranker_json` - 重排序器配置

---

## 🔧 配置示例

> **📚 参考文档**：详细的配置选项和支持的提供者，请参考 [Mem0 官方配置文档](https://docs.mem0.ai/open-source/configuration)。

### LLM 配置 (`local_llm_json`)

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

### Embedder 配置 (`local_embedder_json`)

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

### Vector Store 配置 (`local_vector_db_json`)

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

### Graph Store 配置 (`local_graph_db_json`) - 可选

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

### Reranker 配置 (`local_reranker_json`) - 可选

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

---

## ✅ 验证安装

配置完成后，你应该能在 Dify 工作流中使用以下 8 个工具：

### 核心功能工具
1. ✅ **Add Memory** - 智能管理记忆（添加/更新/删除）
2. ✅ **Search Memory** - 搜索记忆（支持过滤器和 top_k）
3. ✅ **Get All Memories** - 获取所有记忆
4. ✅ **Get Memory** - 获取单条记忆详情
5. ✅ **Update Memory** - 更新记忆
6. ✅ **Delete Memory** - 删除单条记忆
7. ✅ **Delete All Memories** - 批量删除记忆
8. ✅ **Get Memory History** - 查看记忆历史

---

## 🧪 快速测试

### 测试 1：添加记忆
```json
{
  "user": "I love Italian food",
  "assistant": "Great! I'll remember that.",
  "user_id": "test_user_001",
  "metadata": "{\"category\": \"food_preferences\"}"
}
```

### 测试 2：搜索记忆
```json
{
  "query": "What food does the user like?",
  "user_id": "test_user_001",
  "top_k": 5
}
```

### 测试 3：使用过滤器
```json
{
  "query": "user preferences",
  "filters": "{\"AND\": [{\"user_id\": \"test_user_001\"}]}"
}
```

---

## 🔧 故障排查

### 问题 1：上传失败
**原因**：文件损坏或格式不正确
**解决**：
```bash
# 重新生成插件包
cd <your-plugin-directory>
./build_package.sh
```

### 问题 2：工具无法使用
**原因**：配置缺失或无效
**解决**：
1. 确认已选择运行模式（`async_mode`）
2. 确认已填写必填项：`local_llm_json`、`local_embedder_json`、`local_vector_db_json`
3. 检查 JSON 结构是否为 `{ "provider": ..., "config": { ... } }`
4. 验证所有 API keys 和数据库连接信息是否正确

### 问题 3：过滤器 JSON 报错
**原因**：JSON 格式错误
**解决**：
- 确保 `filters` 参数是有效的 JSON 字符串
- 使用在线 JSON 验证器检查格式
- 参考 CHANGELOG.md 中的示例

### 问题 4：HTTP 超时
**原因**：数据库/图数据库连接问题
**解决**：
- 检查向量库（如 pgvector/pinecone）或图数据库（Neo4j）连接配置
- 确认凭证、地址与端口正确

---

## 📚 更多资源

- **插件更新日志**: 查看 `CHANGELOG.md`
- **Mem0 官方文档**: https://docs.mem0.ai
- **Dify 插件文档**: https://docs.dify.ai/docs/plugins
- **问题反馈**: 联系插件开发者

---

## 🔄 更新插件

### 从旧版本升级
如果你已经安装了旧版：

1. **备份数据**（可选）
   - 导出现有的记忆数据
   - 记录当前配置

2. **卸载旧版本**
   - 在 Dify 插件管理中卸载旧版本
   - 或使用 CLI：`dify plugin uninstall mem0ai`

3. **安装新版本**
   - 按照上述步骤安装 v0.1.5
   - 重新配置运行模式和所有 JSON 凭证

4. **验证功能**
   - 测试 8 个工具
   - 验证过滤器与 `top_k`
   - 根据选择的模式验证操作行为

### 运行模式说明

- **异步模式** (`async_mode=true`，默认)：
  - 写操作（Add/Update/Delete/Delete_All）：非阻塞，立即返回 ACCEPT 状态
  - 读操作（Search/Get/Get_All/History）：等待结果，具有超时保护（默认 30 秒）
  - 适合生产环境，支持高并发

- **同步模式** (`async_mode=false`)：
  - 所有操作阻塞直到完成
  - 可以立即看到每次操作的实际返回结果
  - 适合测试和调试
  - **注意**：同步模式没有超时保护。如果需要超时保护，请使用 `async_mode=true`

---

## 🎉 开始使用

安装完成后，你可以：

1. **在 Workflow 中使用**
   - 拖拽 Mem0 工具到工作流
   - 配置参数
   - 连接其他节点

2. **在 Agent 中使用**
   - 为 Agent 添加 Mem0 工具
   - Agent 将自动使用记忆功能
   - 支持长期记忆和上下文

3. **通过 API 调用**
   - 使用 Dify API 调用 Mem0 工具
   - 集成到你的应用中
   - 实现自定义记忆逻辑

---

## ⚠️ 重要提示

1. **API Key 安全**
   - 不要在公共场合分享 API Key
   - 定期更换 API Key
   - 使用环境变量存储敏感信息

2. **记忆管理**
   - 定期清理不需要的记忆
   - 使用 metadata 组织记忆
   - 注意记忆存储配额

3. **性能优化**
   - 使用 `top_k/limit` 控制返回数量（默认 5）
   - 合理使用过滤器减少查询范围
   - pgvector 连接池自动配置：最小连接数 10，最大连接数 40，支持高并发场景

4. **可配置超时（v0.1.2+）**
   - 所有读操作（Search/Get/Get_All/History）支持用户可配置的超时值
   - 超时参数在 Dify 插件配置界面中作为手动输入字段提供
   - 如果未指定，工具使用默认值（30 秒）
   - 无效的超时值会被捕获并记录警告，回退到默认值

---

**祝你使用愉快！** 🚀

如有问题，请查看 CHANGELOG.md 或联系支持团队。
