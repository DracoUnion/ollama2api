# 前端页面与组件划分设计文档

> 技术栈：React 18 + React Router v6 + Axios + Ant Design (或 Tailwind + shadcn/ui) + Zustand/Context 状态管理。  
> 构建工具：Vite。  
> 目标：提供友好的多后端 Ollama 代理管理界面，支持节点配置、模型映射、实时聊天测试和日志监控。

## 一、整体布局与路由

采用经典的上导航栏 + 侧边栏布局（可折叠侧边栏）。

### 1.1 布局结构

```
┌─────────────────────────────────────────────────┐
│                    顶部栏                        │
│  Logo | 状态徽标 | 健康状态 | 用户/设置入口       │
├────────┬────────────────────────────────────────┤
│        │                                        │
│ 侧边栏 │            主要内容区域                │
│ (导航) │         (根据路由渲染页面)              │
│        │                                        │
└────────┴────────────────────────────────────────┘
```

- **侧边栏菜单项**：
  - 仪表盘 (Dashboard)
  - 节点管理 (Nodes)
  - 模型映射 (Mappings)
  - 测试聊天室 (Playground)
  - 日志查看 (Logs)
  - 全局配置 (Settings) [可选]

### 1.2 路由映射

| 路径 | 页面组件 | 说明 |
|------|---------|------|
| `/` | `DashboardPage` | 重定向到 `/dashboard` |
| `/dashboard` | `DashboardPage` | 展示整体统计、健康状态 |
| `/nodes` | `NodesPage` | 管理 Ollama 后端列表 |
| `/mappings` | `MappingsPage` | 管理虚拟模型名 ↔ 实际模型名映射 |
| `/playground` | `PlaygroundPage` | 聊天测试界面 |
| `/logs` | `LogsPage` | 日志列表及详情 |
| `/settings` | `SettingsPage` | 全局参数配置 |
| `*` | `NotFoundPage` | 404 页面 |

## 二、页面级组件划分

### 2.1 DashboardPage（仪表盘）

**功能**：展示服务概览，包括代理服务状态、后端健康摘要、请求统计。

**子组件**：
- `HealthStatusCard`: 显示代理服务健康状态、版本、运行时长
- `BackendSummaryCard`: 显示后端总数/健康数/不健康数，列出不健康节点（警告）
- `StatsChart`: 使用 ECharts 或 Recharts 展示最近请求趋势（按小时/天）
- `ModelUsageTable`: 按虚拟模型名的请求量/平均耗时表格
- `TopBackendTable`: 按后端 URL 的请求分布

**数据来源**：调用 `GET /api/stats` 和 `GET /api/nodes`。

### 2.2 NodesPage（节点管理）

**功能**：增删改查 Ollama 后端节点，查看/刷新模型列表，测试连通性。

**子组件**：
- `NodeFilterBar`: 筛选控件
  - 启用状态下拉（全部/启用/禁用）
  - 健康状态下拉（全部/健康/不健康）
  - URL 关键词搜索输入框
- `NodeList`: 表格展示节点列表（分页）
  - 每行包含：URL、启用开关、健康状态（图标）、模型数量、操作按钮
  - 操作：编辑、删除、刷新模型、测试连接
- `Pagination`: 分页组件
- `NodeFormModal`: 添加/编辑节点的弹窗表单（URL、备注、启用状态）
- `RefreshModelsButton`: 针对单个节点的刷新按钮，触发刷新并更新模型列表
- `TestConnectionButton`: 测试连接，显示成功/失败 Toast

**交互流程**：
- 点击添加 → 弹出 `NodeFormModal` → 提交 → 刷新列表
- 点击刷新模型 → 调用 POST `/api/nodes/{id}/refresh` → 更新表格中的”模型列表”列
- 测试连接 → 调用 POST `/api/nodes/{id}/test` → 显示结果
- 筛选/翻页 → 调用 `GET /api/nodes?page=x&size=y&enabled=...&healthy=...&keyword=...` → 更新表格

### 2.3 MappingsPage（模型映射）

**功能**：管理虚拟模型名到实际模型名的映射关系（一对一名称映射，不涉及具体节点）。

**子组件**：
- `MappingTable`: 表格展示所有映射
  - 列：虚拟模型名、实际模型名、操作（编辑、删除）
- `MappingFormModal`: 添加/编辑映射的表单
  - 虚拟模型名输入（文本框）
  - 实际模型名输入（文本框）
- `DeleteMappingConfirm`: 删除前的确认弹窗

**数据加载**：
- 首次加载：获取 `GET /api/mappings`

### 2.4 PlaygroundPage（测试聊天室）

**功能**：选择虚拟模型，发送对话消息，流式显示回复，并展示实际使用的后端信息。

**子组件**：
- `ModelSelector`: 下拉框，选项从 `GET /api/mappings` 的 key 中获取（虚拟模型名）
- `ChatMessageList`: 显示历史消息（用户/助手），支持 Markdown 渲染（可选）
- `ChatInput`: 多行文本输入框，发送按钮，支持 Enter 发送
- `StreamingIndicator`: 流式响应时的加载/打字效果
- `BackendInfoBadge`: 显示当前回复所使用的实际后端 URL 和模型名（从响应头或自定义字段解析）

**交互流程**：
1. 用户选择虚拟模型。
2. 发送消息时，前端直接调用 OpenAI 兼容节点 `POST /v1/chat/completions`（stream=true）。
3. 使用 `fetch` + `ReadableStream` 处理 SSE 流，逐块渲染到 `ChatMessageList`。
4. 从第一个 chunk 或响应头中获取 `x-ollama-proxy` 信息（如果后端支持），或从非流式响应尾部字段获取，并在 UI 中展示。

### 2.5 LogsPage（日志查看）

**功能**：分页展示请求日志，支持筛选和详情查看。

**子组件**：
- `LogFilterBar`: 筛选控件
  - 模型名下拉（从映射表动态加载）
  - 状态码下拉（200/400/500等）
  - 关键词搜索输入框
  - 日期范围选择器（可选）
- `LogTable`: 表格展示日志列表
  - 列：时间、虚拟模型、实际后端、状态码、耗时、Token 用量
  - 操作：查看详情按钮
- `Pagination`: 分页组件
- `LogDetailDrawer`: 抽屉或模态框，展示单条日志的完整请求/响应内容（格式化 JSON）

**数据来源**：`GET /api/logs` 带查询参数。

### 2.6 SettingsPage（全局配置）

**功能**：管理 API Key、透传模式、超时重试等全局设置。

**子组件**：
- `GlobalConfigForm`: 表单
  - 开关：启用 API Key 认证
  - 输入框：API Key（密码类型，可显示/隐藏）
  - 开关：未映射时同名透传 (default_passthrough)
  - 数字输入：请求超时（秒）、最大重试次数
- `SaveButton`: 提交表单到 `POST /api/config`

**安全提示**：API Key 修改后，后续请求需立即使用新 Key。

## 三、通用/共享组件

| 组件名 | 用途 | 备注 |
|--------|------|------|
| `Layout` | 顶部栏 + 侧边栏 + 内容区域 | 使用 Ant Design Layout 或自定义 |
| `Sidebar` | 菜单导航 | 高亮当前路由 |
| `Header` | 显示服务状态、刷新按钮 | 包含健康检查小红点 |
| `LoadingSpinner` | 全局加载指示器 | 用于异步请求等待 |
| `ErrorBoundary` | 捕获组件错误，展示降级 UI | React 错误边界 |
| `ToastNotification` | 操作成功/失败提示 | 可用 Ant Design message |
| `ConfirmModal` | 确认删除等危险操作 | 通用模态框 |
| `PageTitle` | 页面标题 + 面包屑 | 可选 |

## 四、状态管理设计

### 4.1 全局状态 (Zustand 或 Context)

创建以下 Store（以 Zustand 为例）：

```js
// stores/appStore.js
const useAppStore = create((set) => ({
  // 全局配置
  globalConfig: { apiKeyEnabled: false, defaultPassthrough: true, ... },
  setGlobalConfig: (config) => set({ globalConfig: config }),

  // 节点列表（分页）
  nodes: [],
  nodesTotal: 0,
  nodesPage: 1,
  nodesSize: 20,
  setNodes: (data, total, page, size) => set({ nodes: data, nodesTotal: total, nodesPage: page, nodesSize: size }),
  addNode: (ep) => set((state) => ({ nodes: [...state.nodes, ep], nodesTotal: state.nodesTotal + 1 })),
  updateNode: (id, updates) => ...,
  deleteNode: (id) => ...,

  // 模型映射表
  mappings: {},
  setMappings: (mappings) => set({ mappings }),

  // 健康状态轮询
  healthPolling: false,
  startHealthPolling: () => ...,
}));
```

### 4.2 数据获取与缓存

- 使用 React Query (TanStack Query) 管理服务端状态，自动处理缓存、重新验证。
- 对于节点列表和映射表，在组件挂载时获取，并设置定期刷新（例如每 30 秒轮询健康状态）。

## 五、样式与 UI 库

**推荐**：Ant Design v5
- 优点：组件丰富，表格/表单/弹窗开箱即用，节省开发时间。
- 主题可定制，适合管理后台。

**备选**：Tailwind CSS + shadcn/ui
- 更灵活，轻量，但需要自己组合组件。

选择 Ant Design 加速开发。

## 六、组件层级树

```
App
├─ Layout
│  ├─ Header
│  │  ├─ ServiceStatusBadge
│  │  └─ RefreshButton
│  ├─ Sidebar
│  │  └─ MenuItems
│  └─ Content (Outlet)
│     ├─ DashboardPage
│     │  ├─ HealthStatusCard
│     │  ├─ BackendSummaryCard
│     │  ├─ StatsChart (Recharts)
│     │  └─ ModelUsageTable
│     ├─ NodesPage
│     │  ├─ NodeFilterBar
│     │  ├─ NodeList (Table)
│     │  │  └─ NodeActions (Buttons)
│     │  ├─ Pagination
│     │  └─ NodeFormModal
│     ├─ MappingsPage
│     │  ├─ MappingTable
│     │  │  └─ MappingActions
│     │  └─ MappingFormModal
│     ├─ PlaygroundPage
│     │  ├─ ModelSelector
│     │  ├─ ChatMessageList
│     │  │  └─ ChatMessage (单个消息，支持角色样式)
│     │  ├─ ChatInput
│     │  └─ BackendInfoBadge
│     ├─ LogsPage
│     │  ├─ LogFilterBar
│     │  ├─ LogTable
│     │  ├─ Pagination
│     │  └─ LogDetailDrawer
│     └─ SettingsPage
│        └─ GlobalConfigForm
└─ ToastNotification (Portal)
```

## 七、API 接口调用封装

创建 `api.js` 模块，基于 Axios 实例：

```js
const apiClient = axios.create({
  baseURL: '/api',  // 代理到后端
  timeout: 10000,
});

// 请求拦截器添加 API Key
apiClient.interceptors.request.use((config) => {
  const apiKey = localStorage.getItem('api_key');
  if (apiKey) {
    config.headers.Authorization = `Bearer ${apiKey}`;
  }
  return config;
});

export const nodesApi = {
  list: () => apiClient.get('/nodes'),
  create: (data) => apiClient.post('/nodes', data),
  update: (id, data) => apiClient.put(`/nodes/${id}`, data),
  delete: (id) => apiClient.delete(`/nodes/${id}`),
  refreshModels: (id) => apiClient.post(`/nodes/${id}/refresh`),
  test: (id) => apiClient.post(`/nodes/${id}/test`),
};
// ... 其他 API 模块
```

## 八、开发顺序建议

1. 搭建项目框架：Vite + React + Ant Design + Router
2. 实现 Layout 和路由基础结构
3. 实现 NodesPage（增删改查 + 刷新模型）→ 确保后端管理基本可用
4. 实现 MappingsPage（模型映射配置）→ 用于后续测试
5. 实现 PlaygroundPage（聊天测试）→ 验证整体转发功能
6. 实现 LogsPage 和 DashboardPage（统计图表）
7. 实现 SettingsPage 和全局状态集成
8. 添加错误处理、加载状态、Toast 通知等细节优化
