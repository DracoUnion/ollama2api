# 产品需求文档（PRD）


## 1. 产品概述

### 1.1 背景与动机
Ollama 可在一台机器或不同服务器上运行多个实例，每个实例可能提供不同的模型集合（如一台跑 Llama3，另一台跑 Qwen2）。开发者希望使用统一的 OpenAI 兼容 API 访问这些分散的模型，且自动实现请求分发与负载均衡（随机）。本应用提供协议转换 + 多后端管理 + 可视化配置。

### 1.2 目标
- **多后端管理**：支持添加、删除、编辑多个 Ollama 服务地址（URL），自动或手动获取每个后端支持的模型列表。
- **灵活映射**：允许将“虚拟模型名”（OpenAI API 中使用的名称）映射到【一个或多个】实际模型（每个实际模型由“后端 URL + 模型名称”唯一确定）。
- **随机转发**：当一个虚拟模型对应多个后端实例时，每次请求随机选择一个可用后端，实现轻量负载均衡。
- **兼容性与可观测性**：保持 OpenAI API 格式转换，提供日志记录每次请求被转发到哪个后端。

## 2. 功能需求

### 2.1 后端核心功能（Flask）

#### 2.1.1 API 代理与随机转发
核心转换端点仍为 `POST /v1/chat/completions` 和 `GET /v1/models`。

**转发决策流程**：
1. 接收 OpenAI 格式请求，提取 `model` 字段（虚拟模型名）。
2. 查询模型映射表：`虚拟模型名 → 实际目标列表`。
   - 实际目标结构：`{ endpoint_id 或直接 URL, actual_model_name }`
3. 若该虚拟模型存在一个或多个实际目标：
   - 从列表中**随机选择**一个目标（使用 `random.choice`）。
   - 使用该目标的 URL 和实际模型名调用 Ollama API。
4. 若不存在映射：
   - 可配置行为：① 返回错误（模型不存在）；② 遍历所有后端，查找是否有同名模型（actual_model_name 等于虚拟模型名），若有则随机选择一个后端并转发（透传模型名）。
5. 如果选中的后端不可达（连接失败或超时），是否需要重试？简化：直接返回 502，并记录日志。高级版可实现自动重试另一个随机后端（可选，根据需求决定）。

#### 2.1.2 多端点配置管理
数据结构设计（存储在配置文件或 SQLite 中）：

```json
{
  "endpoints": [
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
    "gpt-3.5-turbo": [
      { "endpoint_id": "ep_1", "model_name": "llama3:7b" },
      { "endpoint_id": "ep_2", "model_name": "qwen2:7b" }
    ],
    "claude-instant": [
      { "endpoint_id": "ep_1", "model_name": "mistral:7b" }
    ]
  },
  "global": {
    "api_key_enabled": false,
    "api_key": "",
    "default_passthrough": true   // 未映射时是否尝试同名透传
  }
}
```

**运行时配置接口**：
- `GET /api/endpoints` 获取所有端点列表
- `POST /api/endpoints` 添加新端点（需提供 URL，可选模型列表）
- `PUT /api/endpoints/<id>` 更新端点（如 URL、启用状态）
- `DELETE /api/endpoints/<id>` 删除端点
- `GET /api/endpoints/<id>/models` 手动触发 Ollama 的 `/api/tags` 获取该端点的模型列表，并更新到 `models` 字段

- `GET /api/mappings` 获取模型映射表
- `POST /api/mappings` 添加或更新映射（指定虚拟名称，以及一个或多个实际目标）
- `DELETE /api/mappings/<virtual_name>` 删除映射

**健康检查**：后台线程定期（如每 30 秒）探测所有端点的 `/api/tags` 接口，更新 `healthy` 状态。转发时若随机选中不健康的端点，可跳过并重选（最多 N 次）。

#### 2.1.3 日志增强
每条日志需记录：
- 虚拟模型名
- 实际使用的后端 URL 和实际模型名
- 是否健康检查失败导致的故障转移

#### 2.1.4 其他保持同原 PRD（健康检查、流式转换等）

### 2.2 前端功能（React）

#### 2.2.1 仪表盘
- 显示服务状态概览，并列出所有已配置的 Ollama 端点及其健康状态（绿/红）。
- 每个端点显示 URL、在线模型数量、最近请求数（可选）。

#### 2.2.2 配置页面（分为两个子页或 Tab）
**Tab1：后端端点管理**
- 列表展示所有端点，支持添加/编辑/删除。
- 添加/编辑表单：URL（必填）、备注。
- 每个端点右侧按钮：① 测试连接（立即调用 `/api/tags` 并显示模型列表）；② 刷新模型列表（更新该端点下的模型）。
- 显示每个端点已知的模型（标签形式）。

**Tab2：模型映射**
- 以表格形式展示虚拟模型名 → 实际目标列表（多对多）。
- 添加映射：选择虚拟模型名（可新建），然后选择一个或多个“实际目标”（从已有的端点+模型组合中选择）。
- 编辑映射：可修改实际目标列表（增加/删除目标项）。
- 删除映射。
- 对于每个虚拟模型，可看到对应的多个实际目标，用户可手动调整优先级顺序？按需求是随机，但可保留顺序供将来扩展。

#### 2.2.3 测试聊天室
- 选择虚拟模型名（从映射表中选择）进行对话。
- 显示每次请求实际被转发到的后端 URL 和模型名（可用于调试）。

#### 2.2.4 日志查看
- 额外增加一列“实际后端”展示 URL。

## 3. 技术架构调整

### 3.1 数据存储
原 PRD 使用简单的 config.py 全局变量，现在需要持久化保存多端点及映射。建议使用 **SQLite**（轻量，无需额外依赖）或 JSON 文件（简单但并发写需注意）。推荐 SQLite + SQLAlchemy（ORM）或直接使用 sqlite3 模块。核心表：
- `endpoints`: id, url, enabled, healthy, last_check, metadata
- `endpoint_models`: endpoint_id, model_name (一对多)
- `model_mappings`: virtual_name, endpoint_id, actual_model_name (联合主键)

或者为了简化，仍然使用 JSON 文件加文件锁，适合小规模部署。

### 3.2 随机算法实现
```python
import random
def resolve_target(virtual_model):
    targets = mapping.get(virtual_model, [])
    if not targets:
        if global_default_passthrough:
            # 获取所有健康端点的所有模型，查找与 virtual_model 同名的
            candidates = [(ep.url, virtual_model) for ep in endpoints if ep.healthy and virtual_model in ep.models]
            return random.choice(candidates) if candidates else None
        else:
            return None
    # 过滤掉不健康的端点
    healthy_targets = [t for t in targets if get_endpoint(t.endpoint_id).healthy]
    if not healthy_targets:
        # 可选：返回任意一个不健康的（记录警告）
        healthy_targets = targets
    return random.choice(healthy_targets)
```

### 3.3 后端自省获取模型列表
Ollama 提供 `GET /api/tags`，返回 `{"models":[{"name":"llama3:7b",...}]}`。添加端点时，自动调用此接口填充模型列表；用户也可手动刷新。

### 3.4 容错与重试
当选定一个目标后，调用 Ollama 失败（超时/连接错误），可记录错误并尝试从剩余候选目标中再随机选择一个（最多尝试 3 次）。如果全部失败，返回 503。

## 4. 接口规范补充

### 4.1 后端管理接口示例

**GET /api/endpoints** 响应：
```json
[
  {
    "id": "ep_1",
    "url": "http://10.0.0.1:11434",
    "enabled": true,
    "healthy": true,
    "models": ["llama3:7b", "mistral:7b"],
    "last_health_check": "2025-..."
  }
]
```

**POST /api/endpoints** 请求：
```json
{
  "url": "http://10.0.0.2:11434",
  "enabled": true
}
```
响应：创建后的完整对象。

**POST /api/endpoints/<id>/refresh** 触发模型列表刷新，返回新的 models 列表。

**GET /api/mappings** 响应：
```json
{
  "gpt-3.5-turbo": [
    { "endpoint_id": "ep_1", "model_name": "llama3:7b" },
    { "endpoint_id": "ep_2", "model_name": "qwen2:7b" }
  ]
}
```

**POST /api/mappings** 请求：
```json
{
  "virtual_name": "gpt-3.5-turbo",
  "targets": [
    { "endpoint_id": "ep_1", "model_name": "llama3:7b" },
    { "endpoint_id": "ep_2", "model_name": "llama3:7b" }
  ]
}
```
若已存在映射则覆盖。删除映射使用 DELETE。

## 5. 非功能需求补充

- **高可用考虑**：随机转发虽简单，但可避免单点过载。若需要更复杂的负载均衡（轮询、最少连接），可在后续迭代。
- **并发安全**：当使用 JSON 文件存储配置时，写操作需加文件锁。建议使用 SQLite 避免。
- **端点模型自动同步**：当 Ollama 后端增加了新模型，用户需手动点击“刷新模型列表”，或应用可定时（如每小时）刷新一次。

## 6. 实现计划更新

| 阶段 | 任务 | 工时 |
|------|------|------|
| 1 | 后端核心改造：支持多端点数据结构、随机转发逻辑 | 4h |
| 2 | 后端管理 API（CRUD endpoints + mappings） | 4h |
| 3 | 健康检查后台任务、容错重试 | 2h |
| 4 | 前端：端点管理页面（列表、添加、刷新模型） | 3h |
| 5 | 前端：模型映射页面（多对多配置界面） | 3h |
| 6 | 前端：仪表盘显示多端点健康状态 | 2h |
| 7 | 测试聊天室显示实际后端信息 | 1h |
| 8 | 日志记录增强、联调 | 3h |
| 合计 | | 22h（与原计划持平，因部分复用） |

## 7. 验收标准补充

1. 可通过前端添加两个 Ollama 后端（如本机不同端口或远程），配置模型映射：`my-model` 对应后端A的`modelX`和后端B的`modelY`。
2. 连续多次调用 `my-model`，观察日志确认请求随机分散到两个后端。
3. 手动禁用其中一个后端（停止服务），应用健康检查标记其为不健康，之后的请求不再转发到该后端（若无其他可用后端则失败）。
4. 刷新模型列表功能：当 Ollama 端新增模型，前端点击刷新后，该端点的模型列表更新，且可用于后续映射配置。
