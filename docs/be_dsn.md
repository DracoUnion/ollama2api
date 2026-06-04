# 后端 API 设计文档

> 本设计基于 Flask，提供两类 API：
> 1. **OpenAI 兼容节点**（供客户端使用，模拟 OpenAI API 格式）
> 2. **管理节点**（供前端 React 应用调用，管理多后端、模型映射、查看日志）

## 一、OpenAI 兼容节点（代理转发）

### 1.1 聊天补全

**节点**：`POST /v1/chat/completions`

**功能**：接收 OpenAI 格式的聊天请求，根据模型映射查找实际模型名，再从所有健康节点中随机选择一个拥有该模型的节点，转换后调用 Ollama `/api/chat`，并返回 OpenAI 格式响应（支持流式/非流式）。

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

### 1.2 查询可用模型（虚拟 + 真实）

**节点**：`GET /v1/models`

**功能**：返回当前所有可用模型，包括：
1. **虚拟模型**：来自模型映射表的 `virtual_name`（`owned_by` 为 `"ollama-proxy"`，附加 `x-actual-model` 扩展字段）。
2. **真实模型**：来自所有健康节点的去重模型列表（`owned_by` 为 `"ollama"`）。

若虚拟模型映射的实际模型名与某个真实模型同名，两者均返回（虚拟模型优先用于转发映射，真实模型可直接透传调用）。主要供 OpenAI SDK 的 `client.models.list()` 使用。

**响应**（200 OK）：

```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-3.5-turbo",
      "object": "model",
      "created": 1699000000,
      "owned_by": "ollama-proxy",
      "x-actual-model": "llama3:7b"
    },
    {
      "id": "llama3:7b",
      "object": "model",
      "created": 1699000000,
      "owned_by": "ollama"
    },
    {
      "id": "mistral:7b",
      "object": "model",
      "created": 1699000000,
      "owned_by": "ollama"
    }
  ]
}
```

> `x-actual-model` 为非标准扩展字段，仅虚拟模型携带，标明映射到的真实模型名。

---

## 二、管理 API

> **前缀**：`/api`（与代理节点区分）
> **认证**：Cookie 校验。通过 `/api/login` 登录后获得 Session Cookie，后续所有管理接口请求需携带该 Cookie。未登录返回 401。
>
> **统一响应格式**：所有管理接口的响应体均使用以下统一结构，HTTP 状态码始终为 200：
>
> ```json
> {
>   "code": 0,       // 业务错误码，0 表示成功，非 0 表示失败（见下方错误码表）
>   "data": ...,     // 实际业务数据，成功时返回，失败时为 null
>   "msg": ""        // 错误信息，成功时为空字符串，失败时返回描述
> }
> ```

### 2.1 登录与登出

#### 2.1.1 登录

**节点**：`POST /api/login`

**请求体**：

```json
{
  "password": "admin-secret"
}
```

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": null,
  "msg": ""
}
```

服务端验证密码成功后，设置 Session Cookie（如 `session_id`），后续管理接口请求自动携带该 Cookie 进行身份校验。

**错误**：
- 缺少 `password` 字段：`{"code": 400, "data": null, "msg": "Missing password field"}`
- 密码错误：`{"code": 401, "data": null, "msg": "Invalid password"}`

#### 2.1.2 登出

**节点**：`POST /api/logout`

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": null,
  "msg": ""
}
```

服务端清除 Session Cookie。

### 2.2 后端节点管理

#### 2.2.1 获取所有节点

**节点**：`GET /api/nodes`

**查询参数**：
- `page`：页码（默认 1）
- `size`：每页条数（默认 20，最大 100）
- `enabled`：按启用状态筛选（`true`/`false`，可选）
- `healthy`：按健康状态筛选（`true`/`false`，可选）
- `keyword`：按 URL 模糊搜索（可选）

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
    "total": 5,
    "page": 1,
    "size": 20,
    "items": [
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
  },
  "msg": ""
}
```

#### 2.2.2 添加节点

**节点**：`POST /api/nodes`

**请求体**：

```json
{
  "url": "http://10.0.0.3:11434",
  "enabled": true
}
```

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
    "id": "ep_3",
    "url": "http://10.0.0.3:11434",
    "enabled": true,
    "healthy": false,
    "models": [],
    "last_health_check": null,
    "created_at": "2025-06-03T10:35:00Z"
  },
  "msg": ""
}
```

**错误**：
- URL 格式无效：`{"code": 400, "data": null, "msg": "Invalid URL format"}`
- URL 已存在：`{"code": 409, "data": null, "msg": "URL already exists"}`

#### 2.2.3 更新节点

**节点**：`PUT /api/nodes/<node_id>`

**请求体**（所有字段可选）：

```json
{
  "url": "http://10.0.0.3:11434/new",
  "enabled": false
}
```

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": { "id": "ep_1", "url": "...", "enabled": false, "healthy": true, "models": [...], ... },
  "msg": ""
}
```

#### 2.2.4 删除节点

**节点**：`DELETE /api/nodes/<node_id>`

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": null,
  "msg": ""
}
```

> 注意：由于模型映射仅涉及模型名称，不绑定具体节点，删除节点不影响已有映射。

#### 2.2.5 刷新节点模型列表

**节点**：`POST /api/nodes/<node_id>/refresh`

**功能**：调用 Ollama 的 `/api/tags` 获取该节点当前可用模型，更新到 `models` 字段。

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
    "models": ["llama3:7b", "mistral:7b", "codellama:7b"]
  },
  "msg": ""
}
```

**错误**：
- 无法连接节点：`{"code": 400, "data": null, "msg": "Cannot connect to node"}`
- Ollama 服务不可用：`{"code": 503, "data": null, "msg": "Ollama service unavailable"}`

#### 2.2.6 测试节点连通性

**节点**：`GET /api/nodes/<node_id>/test`

**功能**：测试 Ollama 节点是否可达（调用 `/api/tags` 并等待响应）。

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
    "models": ["llama3:7b", "mistral:7b"]
  },
  "msg": ""
}
```

若失败：
```json
{
  "code": 500,
  "data": null,
  "msg": "Connection refused"
}
```

#### 2.2.7 拉取模型

**节点**：`POST /api/nodes/<node_id>/pull`

**功能**：调用指定 Ollama 节点的 `POST /api/pull` 接口，拉取指定模型到该节点。支持同步等待完成或流式返回进度。

**请求体**：

```json
{
  "model_name": "llama3:7b",
  "stream": false
}
```

- `model_name`（必填）：要拉取的模型名称（含标签，如 `llama3:7b`、`qwen2:latest`）。
- `stream`（可选，默认 `false`）：是否以 SSE 流形式实时返回拉取进度。

**响应 — 同步模式**（`stream: false`，等待拉取完成后返回）：

```json
{
  "code": 0,
  "data": {
    "model_name": "llama3:7b",
    "status": "success"
  },
  "msg": ""
}
```

**响应 — 流式模式**（`stream: true`，Content-Type: text/event-stream）：

逐条推送 Ollama 返回的进度事件，格式与 Ollama `/api/pull` 一致：

```
data: {"status":"pulling manifest"}

data: {"status":"pulling abc123...","digest":"sha256:abc123...","total":4567890,"completed":1234567}

data: {"status":"verifying sha256 digest"}

data: {"status":"writing manifest"}

data: {"status":"success"}
```

拉取完成后连接关闭。前端可据此展示进度条。

**错误**：
- 缺少 `model_name`：`{"code": 400, "data": null, "msg": "Missing model_name"}`
- 无法连接节点：`{"code": 400, "data": null, "msg": "Cannot connect to node"}`
- Ollama 返回错误（如模型不存在）：`{"code": 502, "data": null, "msg": "Ollama error: model not found"}`

### 2.3 模型映射管理

> 模型映射仅涉及两个模型名称之间的对应关系（虚拟模型名 → 实际模型名），不绑定具体节点。转发时系统自动从所有健康节点中查找拥有该实际模型的节点。

#### 2.3.1 获取所有映射

**节点**：`GET /api/mappings`

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
    "gpt-3.5-turbo": "llama3:7b",
    "claude-instant": "mistral:7b"
  },
  "msg": ""
}
```

#### 2.3.2 创建/更新映射

**节点**：`POST /api/mappings`

**请求体**：

```json
{
  "virtual_name": "gpt-3.5-turbo",
  "actual_model_name": "llama3:7b"
}
```

- 如果 `virtual_name` 已存在，则覆盖其 `actual_model_name`。

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
    "virtual_name": "gpt-3.5-turbo",
    "actual_model_name": "llama3:7b"
  },
  "msg": ""
}
```

#### 2.3.3 删除映射

**节点**：`DELETE /api/mappings/<virtual_name>`

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": null,
  "msg": ""
}
```

---

### 2.4 全局配置

#### 2.4.1 获取全局配置

**节点**：`GET /api/config`

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
    "api_key_enabled": false,
    "api_key": "sk-xxxx",               // OpenAI 兼容接口的 API Key（仅当 enabled 为 true 时返回，可掩码）
    "admin_password": "***",            // 管理接口登录密码（始终掩码返回）
    "default_passthrough": true,        // 未映射时是否尝试同名透传
    "request_timeout": 60,              // Ollama 请求超时（秒）
    "max_retries": 2                    // 随机转发失败后的最大重试次数
  },
  "msg": ""
}
```

#### 2.4.2 更新全局配置

**节点**：`POST /api/config`

**请求体**：

```json
{
  "api_key_enabled": true,
  "api_key": "sk-new-secret",
  "admin_password": "new-admin-password",
  "default_passthrough": false,
  "request_timeout": 30,
  "max_retries": 2
}
```

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": { "api_key_enabled": true, "api_key": "***", "admin_password": "***", ... },
  "msg": ""
}
```

敏感字段掩码返回。

---

### 2.5 日志查询

#### 2.5.1 获取请求日志（分页）

**节点**：`GET /api/logs`

**查询参数**：
- `page`：页码（默认 1）
- `size`：每页条数（默认 20，最大 100）
- `model`：按虚拟模型名筛选
- `status_code`：按 HTTP 状态码筛选（200, 400, 503...）
- `keyword`：搜索请求/响应中的关键词

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
    "total": 152,
    "page": 1,
    "size": 20,
    "items": [
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
  },
  "msg": ""
}
```

#### 2.5.2 获取单条日志详情

**节点**：`GET /api/logs/<log_id>`

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
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
  },
  "msg": ""
}
```

> 敏感信息（如 API Key）应被过滤或掩码。

---

### 2.6 健康检查与状态

**节点**：`GET /api/health`

**功能**：检查本服务（代理）是否运行正常，以及任意 Ollama 节点是否可达（可选）。

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
    "status": "ok",
    "version": "1.0.0",
    "uptime_seconds": 3600,
    "ollama_nodes": {
      "total": 2,
      "healthy": 1,
      "unhealthy": 1
    }
  },
  "msg": ""
}
```

若服务有严重问题（如数据库错误）：`{"code": 500, "data": null, "msg": "Database error"}`

---

### 2.7 统计摘要（仪表盘用）

**节点**：`GET /api/stats`

**功能**：提供仪表盘所需概览数据。

**响应**（200 OK）：

```json
{
  "code": 0,
  "data": {
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
  },
  "msg": ""
}
```

---

## 三、数据模型与存储

建议使用 **SQLite** 存储以下表：

### 3.1 表结构

**nodes**
- `id` TEXT PRIMARY KEY (如 "ep_xxx")
- `url` TEXT UNIQUE NOT NULL
- `enabled` INTEGER (0/1)
- `healthy` INTEGER (0/1)
- `last_health_check` TIMESTAMP
- `created_at` TIMESTAMP

**node_models**（一对多）
- `node_id` TEXT FOREIGN KEY
- `model_name` TEXT
- PRIMARY KEY (`node_id`, `model_name`)

**model_mappings**
- `virtual_name` TEXT PRIMARY KEY
- `actual_model_name` TEXT NOT NULL

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

### 4.1 OpenAI 兼容接口

HTTP 状态码携带语义，错误响应遵循 OpenAI 标准格式：

| HTTP 状态码 | 说明 |
|------------|------|
| 200 | OK |
| 400 | 请求参数错误（如无效 JSON、缺少必填字段） |
| 401 | API Key 无效或缺失 |
| 404 | 模型不存在 |
| 500 | 代理服务内部错误 |
| 502 | 选中的 Ollama 后端返回无效响应 |
| 503 | 所有可用后端均不可达 |
| 504 | 后端超时 |

### 4.2 管理接口

管理接口 HTTP 状态码始终为 200，通过响应体 `code` 字段区分业务状态：

| code | 说明 |
|------|------|
| 0 | 成功 |
| 400 | 请求参数错误（如无效 JSON、缺少必填字段） |
| 401 | 未登录或 Session 过期 |
| 404 | 资源不存在（如节点 ID 不存在） |
| 409 | 资源冲突（如重复添加相同 URL 的节点） |
| 422 | 语义错误 |
| 500 | 服务内部错误 |
| 503 | 外部服务不可用（如 Ollama 节点不可达） |

---

## 五、认证与安全

本系统采用**两套独立认证机制**，分别保护 OpenAI 兼容接口和管理接口：

### 5.1 OpenAI 兼容接口（`/v1/*`）

- 使用 **API Key** 认证，通过 `Authorization: Bearer <api_key>` 请求头传递。
- 若 `api_key_enabled = true`，所有 `/v1/*` 请求必须携带有效的 API Key；否则返回 401。
- 若 `api_key_enabled = false`，则不校验，所有请求放行。

### 5.2 管理接口（`/api/*`，除 `/api/health` 外）

- 使用 **Cookie Session** 认证。
- 通过 `POST /api/login` 提交 `admin_password` 登录，成功后服务端设置 Session Cookie。
- 后续所有管理接口请求自动携带 Cookie，服务端校验 Session 有效性。
- 未登录或 Session 过期返回 401。
- `GET /api/health` 无需认证，供外部监控探针使用。

### 5.3 安全建议

- 建议在生产环境中使用 HTTPS 部署。
- 管理接口密码和 API Key 应使用强随机字符串。
- 日志中敏感信息（API Key、密码）应被过滤或掩码。
