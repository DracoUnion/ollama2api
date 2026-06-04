# 后端 API 设计文档

> 本设计基于 Flask，提供两类 API：
> 1. **OpenAI 兼容端点**（供客户端使用，模拟 OpenAI API 格式）
> 2. **管理端点**（供前端 React 应用调用，管理多后端、模型映射、查看日志）

## 一、OpenAI 兼容端点（代理转发）

### 1.1 聊天补全

**端点**：`POST /v1/chat/completions`

**功能**：接收 OpenAI 格式的聊天请求，根据模型映射随机选择一个 Ollama 后端，转换后调用 Ollama `/api/chat`，并返回 OpenAI 格式响应（支持流式/非流式）。

**请求头**：
- `Authorization: Bearer <api_key>`（如果启用了 API Key 校验）
- `Content-Type: application/json`

**请求体**（OpenAI 标准，仅列出常用字段）：

```json
{
  "model": "gpt-3.5-turbo",          // 虚拟模型名，用于映射
  "messages": [
    {"role": "system", "content": "You are a helpful assistant."},
    {"role": "user", "content": "Hello!"}
  ],
  "stream": false,                   // 是否流式
  "temperature": 0.7,
  "max_tokens": 100,
  "top_p": 0.9,
  "stop": ["\n", "User:"],
  "frequency_penalty": 0.0,
  "presence_penalty": 0.0
}
```

**响应（非流式，200 OK）**：

```json
{
  "id": "chatcmpl-xxx",
  "object": "chat.completion",
  "created": 1699000000,
  "model": "gpt-3.5-turbo",          // 虚拟模型名
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hi there! How can I help you?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 8,
    "total_tokens": 20
  },
  "x-ollama-proxy": {                // 非标准字段，用于调试
    "backend_url": "http://10.0.0.1:11434",
    "actual_model": "llama3:7b"
  }
}
```

**响应（流式，200 OK，Content-Type: text/event-stream）**：

每块 SSE 数据格式（与 OpenAI 一致）：

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1699000000,"model":"gpt-3.5-turbo","choices":[{"index":0,"delta":{"content":"Hi"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1699000000,"model":"gpt-3.5-turbo","choices":[{"index":0,"delta":{"content":" there"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1699000000,"model":"gpt-3.5-turbo","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1699000000,"model":"gpt-3.5-turbo","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

> **注意**：流式响应中不包含 `usage` 和 `x-ollama-proxy`（但可在最后一条消息后额外发送，非标准，可选）。

**错误响应**（4xx/5xx）：

```json
{
  "error": {
    "message": "No healthy backend found for model 'gpt-3.5-turbo'",
    "type": "server_error",
    "code": 503
  }
}
```

或符合 OpenAI 错误格式：
```json
{
  "error": {
    "message": "Model not found",
    "type": "invalid_request_error",
    "param": "model",
    "code": "model_not_found"
  }
}
```

---

### 1.2 查询可用模型（虚拟模型）

**端点**：`GET /v1/models`

**功能**：返回当前配置中所有**虚拟模型名**（从模型映射表的 key 中提取），同时可选返回每个虚拟模型对应的实际后端信息（非标准字段）。主要供 OpenAI SDK 的 `client.models.list()` 使用。

**响应**（200 OK）：

```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-3.5-turbo",
      "object": "model",
      "created": 1699000000,
      "owned_by": "ollama-proxy"
    },
    {
      "id": "claude-instant",
      "object": "model",
      "created": 1699000000,
      "owned_by": "ollama-proxy"
    }
  ]
}
```

> 扩展字段（可选，用于前端展示更多信息）：
> ```json
> "x-backends": [
>   {"url": "http://10.0.0.1:11434", "model": "llama3:7b"},
>   {"url": "http://10.0.0.2:11434", "model": "qwen2:7b"}
> ]
> ```

---

## 二、管理 API

> **前缀**：`/api`（与代理端点区分）
> **认证**：可选，建议在管理接口也支持 API Key（与 OpenAI 端点使用相同 key），或独立配置管理密码。

### 2.1 后端端点管理

#### 2.1.1 获取所有端点

**端点**：`GET /api/endpoints`

**响应**（200 OK）：

```json
[
  {
    "id": "ep_1",
    "url": "http://192.168.1.10:11434",
    "enabled": true,
    "healthy": true,
    "models": ["llama3:7b", "mistral:7b"],
    "last_health_check": "2025-06-03T10:30:00Z",
    "created_at": "2025-06-01T00:00:00Z"
  },
  {
    "id": "ep_2",
    "url": "http://localhost:11434",
    "enabled": true,
    "healthy": false,
    "models": [],
    "last_health_check": "2025-06-03T10:29:55Z",
    "created_at": "2025-06-02T00:00:00Z"
  }
]
```

#### 2.1.2 添加端点

**端点**：`POST /api/endpoints`

**请求体**：

```json
{
  "url": "http://10.0.0.3:11434",
  "enabled": true
}
```

**响应**（201 Created）：

```json
{
  "id": "ep_3",
  "url": "http://10.0.0.3:11434",
  "enabled": true,
  "healthy": false,
  "models": [],
  "last_health_check": null,
  "created_at": "2025-06-03T10:35:00Z"
}
```

**错误**：
- 400：URL 格式无效
- 409：URL 已存在（可选去重）

#### 2.1.3 更新端点

**端点**：`PUT /api/endpoints/<endpoint_id>`

**请求体**（所有字段可选）：

```json
{
  "url": "http://10.0.0.3:11434/new",
  "enabled": false
}
```

**响应**（200 OK）：返回更新后的完整对象

#### 2.1.4 删除端点

**端点**：`DELETE /api/endpoints/<endpoint_id>`

**响应**（204 No Content）

> 注意：删除端点时，相关的模型映射中的条目应自动移除（或保留但标记为无效，由前端/后端逻辑处理）。

#### 2.1.5 刷新端点模型列表

**端点**：`POST /api/endpoints/<endpoint_id>/refresh`

**功能**：调用 Ollama 的 `/api/tags` 获取该端点当前可用模型，更新到 `models` 字段。

**响应**（200 OK）：

```json
{
  "models": ["llama3:7b", "mistral:7b", "codellama:7b"]
}
```

**错误**：
- 400：无法连接端点
- 503：Ollama 服务不可用

#### 2.1.6 测试端点连通性

**端点**：`POST /api/endpoints/<endpoint_id>/test`

**功能**：测试 Ollama 端点是否可达（调用 `/api/tags` 并等待响应）。

**响应**（200 OK）：

```json
{
  "success": true,
  "models": ["llama3:7b", "mistral:7b"],
  "message": "OK"
}
```

若失败：
```json
{
  "success": false,
  "message": "Connection refused"
}
```

### 2.2 模型映射管理

#### 2.2.1 获取所有映射

**端点**：`GET /api/mappings`

**响应**（200 OK）：

```json
{
  "gpt-3.5-turbo": [
    { "endpoint_id": "ep_1", "model_name": "llama3:7b" },
    { "endpoint_id": "ep_2", "model_name": "qwen2:7b" }
  ],
  "claude-instant": [
    { "endpoint_id": "ep_1", "model_name": "mistral:7b" }
  ]
}
```

#### 2.2.2 创建/更新映射

**端点**：`POST /api/mappings`

**请求体**：

```json
{
  "virtual_name": "gpt-3.5-turbo",
  "targets": [
    { "endpoint_id": "ep_1", "model_name": "llama3:7b" },
    { "endpoint_id": "ep_2", "model_name": "llama3:7b" }   // 相同模型名不同后端
  ]
}
```

- 如果 `virtual_name` 已存在，则覆盖其 `targets`。
- 如果 `targets` 为空数组，表示删除该虚拟模型的映射（等同于 DELETE）。

**响应**（200 OK）：

```json
{
  "virtual_name": "gpt-3.5-turbo",
  "targets": [ ... ]
}
```

**错误**：
- 400：`targets` 中引用的 `endpoint_id` 不存在，或 `model_name` 不在该端点的 `models` 列表中（警告但不强制拒绝，可由系统自动修复）

#### 2.2.3 删除映射

**端点**：`DELETE /api/mappings/<virtual_name>`

**响应**：204 No Content

---

### 2.3 全局配置

#### 2.3.1 获取全局配置

**端点**：`GET /api/config`

**响应**（200 OK）：

```json
{
  "api_key_enabled": false,
  "api_key": "sk-xxxx",               // 仅当 enabled 为 true 时返回（可掩码）
  "default_passthrough": true,        // 未映射时是否尝试同名透传
  "request_timeout": 60,              // Ollama 请求超时（秒）
  "max_retries": 2                    // 随机转发失败后的最大重试次数
}
```

#### 2.3.2 更新全局配置

**端点**：`POST /api/config`

**请求体**：

```json
{
  "api_key_enabled": true,
  "api_key": "sk-new-secret",
  "default_passthrough": false,
  "request_timeout": 30,
  "max_retries": 2
}
```

**响应**（200 OK）：返回更新后的全局配置（敏感字段可掩码，如 `api_key` 返回 `"***"`）

---

### 2.4 日志查询

#### 2.4.1 获取请求日志（分页）

**端点**：`GET /api/logs`

**查询参数**：
- `page`：页码（默认 1）
- `size`：每页条数（默认 20，最大 100）
- `model`：按虚拟模型名筛选
- `status_code`：按 HTTP 状态码筛选（200, 400, 503...）
- `keyword`：搜索请求/响应中的关键词

**响应**（200 OK）：

```json
{
  "total": 152,
  "page": 1,
  "size": 20,
  "data": [
    {
      "id": "log_xxx",
      "timestamp": "2025-06-03T10:30:00Z",
      "client_ip": "127.0.0.1",
      "virtual_model": "gpt-3.5-turbo",
      "actual_backend": "http://10.0.0.1:11434",
      "actual_model": "llama3:7b",
      "status_code": 200,
      "duration_ms": 1245,
      "prompt_tokens": 45,
      "completion_tokens": 78,
      "stream": false,
      "error_message": null
    }
  ]
}
```

#### 2.4.2 获取单条日志详情

**端点**：`GET /api/logs/<log_id>`

**响应**（200 OK）：

```json
{
  "id": "log_xxx",
  "timestamp": "2025-06-03T10:30:00Z",
  "client_ip": "127.0.0.1",
  "virtual_model": "gpt-3.5-turbo",
  "actual_backend": "http://10.0.0.1:11434",
  "actual_model": "llama3:7b",
  "request": {
    "method": "POST",
    "path": "/v1/chat/completions",
    "headers": { "user-agent": "..." },
    "body": { ... }        // 可能截断
  },
  "response": {
    "status_code": 200,
    "body_preview": "..."  // 前 500 字符
  },
  "duration_ms": 1245,
  "error_message": null
}
```

> 敏感信息（如 API Key）应被过滤或掩码。

---

### 2.5 健康检查与状态

**端点**：`GET /api/health`

**功能**：检查本服务（代理）是否运行正常，以及任意 Ollama 端点是否可达（可选）。

**响应**（200 OK）：

```json
{
  "status": "ok",
  "version": "1.0.0",
  "uptime_seconds": 3600,
  "ollama_endpoints": {
    "total": 2,
    "healthy": 1,
    "unhealthy": 1
  }
}
```

若服务有严重问题（如数据库错误），返回 503。

---

### 2.6 统计摘要（仪表盘用）

**端点**：`GET /api/stats`

**功能**：提供仪表盘所需概览数据。

**响应**（200 OK）：

```json
{
  "total_requests": 1250,
  "requests_last_hour": 42,
  "avg_duration_ms": 1340,
  "total_tokens": 158200,
  "model_breakdown": [
    { "virtual_model": "gpt-3.5-turbo", "count": 800, "avg_duration_ms": 1200 },
    { "virtual_model": "claude-instant", "count": 450, "avg_duration_ms": 1500 }
  ],
  "backend_breakdown": [
    { "url": "http://10.0.0.1:11434", "count": 700, "healthy": true },
    { "url": "http://10.0.0.2:11434", "count": 550, "healthy": false }
  ]
}
```

---

## 三、数据模型与存储

建议使用 **SQLite** 存储以下表：

### 3.1 表结构

**endpoints**
- `id` TEXT PRIMARY KEY (如 "ep_xxx")
- `url` TEXT UNIQUE NOT NULL
- `enabled` INTEGER (0/1)
- `healthy` INTEGER (0/1)
- `last_health_check` TIMESTAMP
- `created_at` TIMESTAMP

**endpoint_models**（一对多）
- `endpoint_id` TEXT FOREIGN KEY
- `model_name` TEXT
- PRIMARY KEY (`endpoint_id`, `model_name`)

**model_mappings**
- `virtual_name` TEXT
- `endpoint_id` TEXT
- `actual_model_name` TEXT
- PRIMARY KEY (`virtual_name`, `endpoint_id`, `actual_model_name`)
- FOREIGN KEY (`endpoint_id`) REFERENCES `endpoints`(`id`)

**request_logs**
- `id` TEXT PRIMARY KEY
- `timestamp` TIMESTAMP
- `client_ip` TEXT
- `virtual_model` TEXT
- `actual_backend` TEXT (存储 URL)
- `actual_model` TEXT
- `status_code` INTEGER
- `duration_ms` INTEGER
- `prompt_tokens` INTEGER
- `completion_tokens` INTEGER
- `stream` INTEGER (0/1)
- `error_message` TEXT
- `request_body` TEXT (可选，长文本)
- `response_preview` TEXT (可选)

### 3.2 配置存储

全局配置可存储在 `config` 表中（key-value），或使用单独的配置文件 + 热加载机制。推荐数据库统一管理。

---

## 四、错误码规范

| HTTP 状态码 | 说明 |
|------------|------|
| 200 | OK |
| 201 | Created |
| 204 | No Content |
| 400 | 请求参数错误（如无效 JSON、缺少必填字段） |
| 401 | 未提供 API Key 或 Key 无效 |
| 404 | 请求的资源不存在（如端点 ID 不存在） |
| 409 | 资源冲突（如重复添加相同 URL 的端点） |
| 422 | 语义错误（如映射引用了不存在的端点 ID） |
| 500 | 代理服务内部错误 |
| 502 | 选中的 Ollama 后端返回无效响应 |
| 503 | 所有可用后端均不可达，或模型映射为空 |
| 504 | 后端超时 |

对于 OpenAI 兼容端点，错误响应格式遵循 OpenAI 的 `error` 对象结构。对于管理端点，可简化：

```json
{
  "error": "Description of error",
  "code": 400,
  "details": {}
}
```

---

## 五、认证与安全

- 管理端点和 OpenAI 代理端点**可共用同一套 API Key**。
- 若 `api_key_enabled = true`，所有请求（除 `/api/health` 和 `/api/config` GET 外）必须携带 `Authorization: Bearer <key>`。
- 建议在生产环境中使用 HTTPS 部署。
