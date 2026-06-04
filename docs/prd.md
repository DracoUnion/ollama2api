# 产品需求文档（PRD）


## 1. 产品概述

### 1.1 背景与动机
Ollama 可在一台机器或不同服务器上运行多个实例，每个实例可能提供不同的模型集合（如一台跑 Llama3，另一台跑 Qwen2）。开发者希望使用统一的 OpenAI 兼容 API 访问这些分散的模型，且自动实现请求分发与负载均衡（随机）。本应用提供协议转换 + 多后端管理 + 可视化配置。

### 1.2 目标
- **多后端管理**：支持添加、删除、编辑多个 Ollama 服务地址（URL），自动或手动获取每个后端支持的模型列表。
- **灵活映射**：允许将”虚拟模型名”（OpenAI API 中使用的名称）映射到一个实际模型名。映射仅涉及名称对应关系，不绑定具体节点；转发时系统自动从所有健康节点中查找拥有该实际模型的节点。
- **随机转发**：当一个虚拟模型对应多个后端实例时，每次请求随机选择一个可用后端，实现轻量负载均衡。
- **兼容性与可观测性**：保持 OpenAI API 格式转换，提供日志记录每次请求被转发到哪个后端。

## 2. 功能需求

### 2.1 后端核心功能（Flask）

#### 2.1.1 API 代理与随机转发
核心转换节点仍为 `POST /v1/chat/completions` 和 `GET /v1/models`（返回虚拟模型 + 所有健康节点的真实模型）。

**转发决策流程**：
1. 接收 OpenAI 格式请求，提取 `model` 字段。
2. 查询模型映射表：`model → 实际模型名`。
   - 若存在映射，得到实际模型名。
   - 若不存在映射，将 `model` 本身当作实际模型名（即真实模型直调）。
3. 从所有健康节点中查找拥有该实际模型的节点列表，**随机选择**一个转发。
4. 若找不到任何拥有该模型的健康节点，返回错误（模型不存在）。
5. 如果选中的节点不可达（连接失败或超时），可自动重试其他候选节点（最多 N 次），全部失败返回 503。

#### 2.1.2 多节点配置管理
数据结构设计（存储在配置文件或 SQLite 中）：

```json
{
  "nodes": [
    {
      "id": "ep_1",
      "url": "http://192.168.1.10:11434",
      "models": ["llama3:7b", "mistral:7b"],  // 可选，若为空则自动探测
      "enabled": true,
      "last_health_check": "2025-...",
      "healthy": true
    },
    {
      "id": "ep_2",
      "url": "http://localhost:11434",
      "models": [],
      "enabled": true
    }
  ],
  "model_mapping": {
    "gpt-3.5-turbo": "llama3:7b",
    "claude-instant": "mistral:7b"
  },
  "global": {
    "api_key_enabled": false,
    "api_key": "",
    "admin_password": "",          // 管理接口登录密码
    "default_passthrough": true   // 未映射时是否尝试同名透传
  }
}
```

**运行时配置接口**（管理接口采用 Cookie Session 认证，需先通过 `/api/login` 登录）：
- `POST /api/login` 管理员登录（提交密码，返回 Session Cookie）
- `POST /api/logout` 管理员登出（清除 Session）
- `GET /api/nodes` 获取节点列表（支持分页、筛选）
- `POST /api/nodes` 添加新节点（需提供 URL，可选模型列表）
- `PUT /api/nodes/<id>` 更新节点（如 URL、启用状态）
- `DELETE /api/nodes/<id>` 删除节点
- `POST /api/nodes/<id>/refresh` 刷新节点模型列表（调用 Ollama `/api/tags`）
- `POST /api/nodes/<id>/pull` 拉取模型到指定节点（调用 Ollama `/api/pull`，支持流式进度）

- `GET /api/mappings` 获取模型映射表
- `POST /api/mappings` 添加或更新映射（指定虚拟名称和实际模型名）
- `DELETE /api/mappings/<virtual_name>` 删除映射

**健康检查**：后台线程定期（如每 30 秒）探测所有节点的 `/api/tags` 接口，更新 `healthy` 状态。转发时若随机选中不健康的节点，可跳过并重选（最多 N 次）。

#### 2.1.3 日志增强
每条日志需记录：
- 虚拟模型名
- 实际使用的后端 URL 和实际模型名
- 是否健康检查失败导致的故障转移

#### 2.1.4 其他保持同原 PRD（健康检查、流式转换等）

### 2.2 前端功能（React）

#### 2.2.1 仪表盘
- 显示服务状态概览，并列出所有已配置的 Ollama 节点及其健康状态（绿/红）。
- 每个节点显示 URL、在线模型数量、最近请求数（可选）。

#### 2.2.2 配置页面（分为两个子页或 Tab）
**Tab1：后端节点管理**
- 列表展示所有节点，支持添加/编辑/删除。
- 添加/编辑表单：URL（必填）、备注。
- 每个节点右侧按钮：① 测试连接（立即调用 `/api/tags` 并显示模型列表）；② 刷新模型列表（更新该节点下的模型）。
- 显示每个节点已知的模型（标签形式）。

**Tab2：模型映射**
- 以表格形式展示虚拟模型名 → 实际模型名（一对一对映）。
- 添加映射：输入虚拟模型名和实际模型名。
- 编辑映射：修改实际模型名。
- 删除映射。

#### 2.2.3 测试聊天室
- 选择虚拟模型名（从映射表中选择）进行对话。
- 显示每次请求实际被转发到的后端 URL 和模型名（可用于调试）。

#### 2.2.4 日志查看
- 额外增加一列“实际后端”展示 URL。

## 3. 技术架构调整

### 3.1 数据存储
原 PRD 使用简单的 config.py 全局变量，现在需要持久化保存多节点及映射。建议使用 **SQLite**（轻量，无需额外依赖）或 JSON 文件（简单但并发写需注意）。推荐 SQLite + SQLAlchemy（ORM）或直接使用 sqlite3 模块。核心表：
- `nodes`: id, url, enabled, healthy, last_check, metadata
- `node_models`: node_id, model_name (一对多)
- `model_mappings`: virtual_name (主键), actual_model_name

或者为了简化，仍然使用 JSON 文件加文件锁，适合小规模部署。

### 3.2 随机算法实现
```python
import random
def resolve_target(virtual_model):
    # 查映射表：虚拟模型名 → 实际模型名
    actual_model = mapping.get(virtual_model)
    if actual_model is None:
        if global_default_passthrough:
            actual_model = virtual_model  # 透传：用原名当作实际模型名
        else:
            return None
    # 从所有健康节点中查找拥有该实际模型的节点
    candidates = [ep for ep in nodes if ep.healthy and actual_model in ep.models]
    if not candidates:
        return None
    chosen = random.choice(candidates)
    return (chosen.url, actual_model)
```

### 3.3 后端自省获取模型列表
Ollama 提供 `GET /api/tags`，返回 `{"models":[{"name":"llama3:7b",...}]}`。添加节点时，自动调用此接口填充模型列表；用户也可手动刷新。

### 3.4 容错与重试
当选定一个目标后，调用 Ollama 失败（超时/连接错误），可记录错误并尝试从剩余候选目标中再随机选择一个（最多尝试 3 次）。如果全部失败，返回 503。

## 4. 接口规范补充

### 4.1 管理接口统一响应格式

所有管理接口（`/api/*`）的响应体统一为以下结构，HTTP 状态码始终为 200：

```json
{
  "code": 0,       // 业务错误码，0 表示成功，非 0 表示失败
  "data": ...,     // 实际业务数据，成功时返回，失败时为 null
  "msg": ""        // 错误信息，成功时为空字符串
}
```

### 4.2 后端管理接口示例

**GET /api/nodes** 响应（支持查询参数 `page`、`size`、`enabled`、`healthy`、`keyword`）：
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
        "url": "http://10.0.0.1:11434",
        "enabled": true,
        "healthy": true,
        "models": ["llama3:7b", "mistral:7b"],
        "last_health_check": "2025-..."
      }
    ]
  },
  "msg": ""
}
```

**POST /api/nodes** 请求：
```json
{
  "url": "http://10.0.0.2:11434",
  "enabled": true
}
```
响应：`{"code": 0, "data": {创建后的完整对象}, "msg": ""}`

**POST /api/nodes/<id>/refresh** 触发模型列表刷新，返回：`{"code": 0, "data": {"models": [...]}, "msg": ""}`

**GET /api/mappings** 响应：
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

**POST /api/mappings** 请求：
```json
{
  "virtual_name": "gpt-3.5-turbo",
  "actual_model_name": "llama3:7b"
}
```
若已存在映射则覆盖。删除映射使用 DELETE。

## 5. 非功能需求补充

- **高可用考虑**：随机转发虽简单，但可避免单点过载。若需要更复杂的负载均衡（轮询、最少连接），可在后续迭代。
- **并发安全**：当使用 JSON 文件存储配置时，写操作需加文件锁。建议使用 SQLite 避免。
- **节点模型自动同步**：当 Ollama 后端增加了新模型，用户需手动点击“刷新模型列表”，或应用可定时（如每小时）刷新一次。

## 6. 实现计划更新

| 阶段 | 任务 | 工时 |
|------|------|------|
| 1 | 后端核心改造：支持多节点数据结构、随机转发逻辑 | 4h |
| 2 | 后端管理 API（CRUD nodes + mappings） | 4h |
| 3 | 健康检查后台任务、容错重试 | 2h |
| 4 | 前端：节点管理页面（列表、添加、刷新模型） | 3h |
| 5 | 前端：模型映射页面（简单名称映射配置） | 2h |
| 6 | 前端：仪表盘显示多节点健康状态 | 2h |
| 7 | 测试聊天室显示实际后端信息 | 1h |
| 8 | 日志记录增强、联调 | 3h |
| 合计 | | 22h（与原计划持平，因部分复用） |

## 7. 验收标准补充

1. 可通过前端添加两个 Ollama 后端（如本机不同端口或远程），配置模型映射：`my-model` → `modelX`。若两个后端均有 `modelX`，则请求自动随机分散到两个后端。
2. 连续多次调用 `my-model`，观察日志确认请求随机分散到拥有该模型的多个后端。
3. 手动禁用其中一个后端（停止服务），应用健康检查标记其为不健康，之后的请求不再转发到该后端（若无其他可用后端则失败）。
4. 刷新模型列表功能：当 Ollama 端新增模型，前端点击刷新后，该节点的模型列表更新，可用于后续映射配置。
