# BACKOFFICE-CONVERSATION-000001 对话快捷问题配置与客户端生成问题登记工单

创建日期：2026-08-23

关联项目：

- 服务端：`/Users/hua/Documents/project/Reference/SparkService`
- 客户端：`/Users/hua/Documents/project/Reference/LookHealthClient/SparkClient`
- 后台前端：`/Users/hua/Documents/project/Reference/SparkService/backoffice-web`

## 1. 背景

客户端对话引导卡片已经进入“本地 AI 根据成员资料异步生成科普问题”的阶段。当前客户端生成的问题只服务于当前会话展示和点击发送 AI 消息，服务端缺少统一登记能力，后台也无法查看客户端真实生成过哪些问题、哪些问题被用户点击、哪些固定快捷问题应作为兜底或运营配置。

本工单新增一条“对话快捷问题”数据链路：

1. 客户端 AI 生成引导卡片科普问题后，后台异步登记到服务端。
2. 用户点击已登记的 AI 生成科普问题后，客户端后台异步上送点击统计，服务端点击数 +1。
3. `backoffice-web` 后台管理系统新增 `对话 / 快捷问题配置` 二级菜单，支持运营配置固定快捷问题，并查看客户端生成记录。

本工单只补充需求与落地方案，不实现代码。

## 2. 当前实现事实

### 2.1 服务端对话同步基础

已确认服务端存在 `chat_sync` 对话同步模型：

- `chat_sync/models.py`
- `ChatThread`
  - `id`：UUID 主键。
  - `user`：关联用户。
  - `member_id`：当前会话绑定成员，整数字段，可为空，已建索引。
  - `scenario`、`current_model_name`、`created_at`、`updated_at`、`server_updated_at` 等字段。
- `ChatMessage`
  - 包含 `client_message_id`、`server_message_id`、`role`、`metadata`。
- `ChatMessageBlock`
  - 包含 `id` UUID、`thread`、`message`、`kind`、`status`、`payload`、`revision`。

这说明现有对话同步链路可以定位 guide card，但本工单新增的问题登记表不保存对话、消息、block 维度字段。问题登记只记录用户、成员和 AI 生成的问题本身。

登记表保留：

- `user_id`
- `member_id`
- `title`
- `prompt`
- `category`

### 2.2 medical app 成员与权限基础

已确认服务端存在 `medical` app：

- `medical/models.py`
- `medical/views.py`
- `medical/serializers.py`
- `medical/urls.py`

其中已存在：

- `Member`
- `UserMemberBinding`
- `MemberPermissionGate`
- `MemberCompleteDataAPI`

这说明客户端生成问题登记到 `medical` app 内是合理的，因为生成问题依赖成员健康资料，且后续查看和点击统计也需要成员维度。

### 2.3 backoffice 后台对话基础

已确认后台服务端存在对话管理接口：

- `backoffice/urls.py`
- `backoffice/conversation_views.py`
- `backoffice/conversation_serializers.py`

当前已有接口包括：

- `conversations/users/`
- `conversations/users/<int:user_id>/summary/`
- `conversations/users/<int:user_id>/threads/`
- `conversations/users/<int:user_id>/threads/<uuid:thread_id>/messages/`
- `conversations/users/<int:user_id>/threads/<uuid:thread_id>/blocks/<uuid:block_id>/detail/`

### 2.4 backoffice-web 对话菜单基础

已确认后台前端存在：

- `backoffice-web/src/router/routes.ts`
- `backoffice-web/src/api/modules/conversations.ts`
- `backoffice-web/src/views/ConversationUsersView.vue`
- `backoffice-web/src/views/ConversationUserThreadsView.vue`

当前路由已有：

- `/conversations/users`：用户对话。
- `/conversations/users/:userId`：用户会话详情。

后台 RBAC 已有：

- `menu:conversations`：对话。
- `menu:conversations:users`：用户对话。

本工单应在该菜单下新增：

- `menu:conversations:quick_questions`：快捷问题配置。
- 路由：`/conversations/quick-questions`。

## 3. 目标

### 3.1 业务目标

建立一套可运营、可统计、可追踪的对话引导卡片科普问题体系：

- 客户端本地 AI 生成的问题可以被服务端登记。
- 用户点击问题可以被统计。
- 后台可以配置固定快捷问题，用于第一阶段兜底、未绑定成员场景、AI 失败场景、运营推荐场景。
- 后台可以查看真实生成记录，帮助判断 AI 生成质量和点击效果。

### 3.2 技术目标

- 客户端上送登记和点击统计必须后台异步执行，不影响建会话、进会话、卡片展示、点击发送 AI 消息等主流程。
- 服务端登记接口保持轻量，客户端后台异步 best-effort 上送，失败或重复不影响主流程。
- 后台管理接口应复用现有 `backoffice` 权限与路由风格。
- 新数据模型放在 `medical` app 内，便于围绕成员健康资料做归档、权限、统计和后续扩展。

## 4. 非目标

本工单不做以下事项：

- 不改变客户端现有引导卡片生成、展示、点击发送消息主链路。
- 不要求客户端等待登记接口成功后再刷新 UI。
- 不要求点击统计实时强一致。
- 不在本阶段引入复杂推荐排序系统。
- 不在本阶段用后台配置问题替换客户端 AI 动态生成问题，只提供固定问题配置与兜底来源。
- 不实现代码，仅输出需求工单与落地方案。

## 5. 总体流程

### 5.1 客户端 AI 生成问题登记流程

```text
进入对话页面
  ↓
首条 system guide card 已插入并展示
  ↓
客户端根据 thread.memberID 判断是否需要生成科普问题
  ↓
有绑定成员：读取成员资料，本地 AI 异步生成问题
  ↓
AI 成功：本地回写 guide block，刷新 UI
  ↓
客户端启动后台异步登记任务
  ↓
POST /medical/chat-guide/questions/register/
  ↓
服务端按 user + member + question idempotency 去重登记
  ↓
登记成功后可返回 server_question_id 映射
  ↓
客户端可选择缓存映射；失败不影响主流程
```

### 5.2 生成失败或无绑定成员流程

```text
进入对话页面
  ↓
检查 thread.memberID
  ↓
无绑定成员或 AI 生成失败
  ↓
使用固定三条科普问题
  ↓
本地回写 guide block，刷新 UI
  ↓
流程结束，不登记到服务端
```

说明：

- 只有 AI 成功生成的问题才进入服务端登记。
- 无绑定成员、AI 生成失败、解析失败等固定兜底场景只做客户端本地展示，不创建生成记录。
- 固定兜底问题不参与本工单的点击 +1 统计，避免后台数据池混入非 AI 生成样本。

### 5.3 点击统计流程

```text
用户点击引导卡片科普问题
  ↓
客户端立即按现有逻辑向当前对话 AI 发送 prompt
  ↓
判断该问题是否为已登记的 AI 生成问题
  ↓
是：启动后台异步点击上送
  ↓
POST /medical/chat-guide/questions/click/
  ↓
服务端按 question id 原子递增 click_count
  ↓
对应问题记录 click_count +1
  ↓
上送失败进入客户端 best-effort 重试或静默丢弃，不阻断用户提问
```

如果点击的是固定兜底问题，客户端只执行发送 prompt 给 AI 的主流程，不上送点击统计。

## 6. 服务端数据模型设计

新模型建议放在：

- `medical/models.py`

迁移文件放在：

- `medical/migrations/`

### 6.1 ChatGuideQuickQuestionConfig

用途：后台配置的固定快捷问题。用于兜底、运营推荐、后续替换第一阶段写死的三条固定问题。

建议字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | BigAutoField | 是 | 主键 |
| `title` | CharField(120) | 是 | 卡片展示文案，要求短句 |
| `prompt` | TextField | 是 | 点击后发送给 AI 的完整 prompt |
| `category` | CharField(64) | 是 | 问题分类，默认 `popular_science` |
| `locale` | CharField(32) | 是 | 语言区域，默认 `zh-Hans` |
| `is_active` | BooleanField | 是 | 是否启用 |
| `created_by` | ForeignKey(User) | 否 | 创建操作员 |
| `updated_by` | ForeignKey(User) | 否 | 最近编辑操作员 |
| `metadata` | JSONField | 否 | 扩展字段，例如适用场景、标签 |
| `created_at` | DateTimeField | 是 | 创建时间 |
| `updated_at` | DateTimeField | 是 | 更新时间 |

字段约束：

- 新增配置默认 `is_active=false`，由运营确认后启用。
- 启用和停用只更新 `is_active`。
- 不建议物理删除，避免影响未来下发和运营统计口径。

建议索引：

- `is_active + category`
- `locale + category + is_active`
- `updated_at`

### 6.2 ChatGuideGeneratedQuestionRecord

用途：登记客户端 AI 成功生成的引导卡片科普问题。固定兜底问题、无绑定成员问题、AI 失败兜底问题不进入本表。

建议字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | BigAutoField | 是 | 主键 |
| `user` | ForeignKey(User) | 是 | 登记用户 |
| `member` | ForeignKey(Member) | 是 | 关联成员；只有有绑定成员且 AI 成功生成时才登记 |
| `title` | CharField(120) | 是 | 展示文案 |
| `prompt` | TextField | 是 | 完整 prompt |
| `category` | CharField(64) | 是 | 默认 `popular_science` |
| `locale` | CharField(32) | 是 | 语言区域，默认 `zh-Hans` |
| `click_count` | PositiveIntegerField | 是 | 点击次数，默认 0 |
| `created_at` | DateTimeField | 是 | 创建时间 |
| `updated_at` | DateTimeField | 是 | 更新时间 |

第一阶段明确不登记以下字段：

- 不登记 `generation_state`：本表只保存成功生成结果，失败和兜底不入表。
- 不登记 `model_name`、`generation_request_id`：排障优先依赖客户端日志，避免表结构膨胀。
- 不登记 `member_profile_digest`、`raw_payload`、`client_context`：减少健康敏感上下文和客户端噪声数据进入服务端。
- 不登记 `thread_id`、`message_id`、`block_id`：本表只做问题登记与统计，不绑定具体对话卡片。
- 不登记 `client_question_id`、`idempotency_key`：第一阶段不做复杂客户端问题映射和幂等键。
- 不登记 `enabled_at`、`disabled_at`：生成记录不存在启停状态。
- 不登记首次/最近点击时间：第一阶段只保留 `click_count`。

字段约束：

- 只有 AI 成功生成的问题才写入本表。
- `user`、`member` 必填。
- 第一阶段不强制唯一约束。若后续出现大量重复记录，再评估增加 `user + member + title + prompt` 的软去重策略。

建议索引：

- `user + created_at`
- `member + created_at`
- `category + created_at`
- `click_count`

点击计数规则：

- 不新增点击明细表。
- 用户点击已登记 AI 生成问题时，客户端异步上送 `server_question_id`。
- 服务端查到 `ChatGuideGeneratedQuestionRecord` 后，使用数据库原子更新将 `click_count` 加 1。
- 找不到记录时返回可忽略结果，不增加点击数。

## 7. 服务端客户端接口设计

接口建议放在：

- `medical/views.py`
- `medical/serializers.py`
- `medical/urls.py`

也可以拆分新文件：

- `medical/chat_guide_question_views.py`
- `medical/chat_guide_question_serializers.py`

若本模块继续增长，推荐拆分新文件，避免 `medical/views.py` 继续膨胀。

### 7.1 登记生成问题

接口：

```text
POST /api/v1/medical/chat-guide/questions/register/
```

请求示例：

```json
{
  "member_id": 10,
  "questions": [
    {
      "id": "q_1",
      "title": "久坐程序员怎么护颈椎腰椎？",
      "prompt": "作为需要中度久坐的27岁男性程序员，日常工作中可以通过哪些健康科普类的方法保护颈椎和腰椎，降低久坐带来的健康影响？",
      "category": "popular_science"
    }
  ]
}
```

响应示例：

```json
{
  "registered": 1,
  "items": [
    {
      "server_question_id": 123
    }
  ]
}
```

服务端处理规则：

- 必须认证用户。
- `member_id` 必填，必须校验当前用户对成员有访问权限，可复用 `MemberPermissionGate.require_access`。
- 同一批次请求可以部分成功，响应需要标明成功数量和失败明细。
- 接口返回成功仅代表登记完成，不影响客户端本地卡片状态。
- 登记接口默认只服务 AI 成功生成问题，不接收固定兜底、失败状态、模型调试上下文等扩展字段。

客户端处理规则：

- AI 生成成功并完成本地 guide block 回写后，再启动登记。
- 登记请求必须后台异步，不阻塞 UI。
- 登记失败不触发卡片 fallback，不回滚本地问题。
- 固定兜底、无绑定成员、AI 失败、解析失败场景不调用登记接口。
- 如服务端返回 `server_question_id`，客户端保存到本地轻量映射，用于点击上送。第一阶段点击接口优先依赖 `server_question_id`，不再通过 thread/block 定位。

### 7.2 上送点击统计

接口：

```text
POST /api/v1/medical/chat-guide/questions/click/
```

请求示例：

```json
{
  "server_question_id": 123,
  "member_id": 10
}
```

响应示例：

```json
{
  "accepted": true,
  "server_question_id": 123,
  "click_count": 8
}
```

服务端处理规则：

- 优先使用 `server_question_id` 查找记录。
- 找不到记录时返回可忽略结果，不增加点击数。
- 点击 +1 使用数据库原子更新，避免并发覆盖。
- 不做点击明细表，不做点击上报幂等；客户端重复上送会重复 +1，第一阶段接受该统计误差。

客户端处理规则：

- 用户点击问题后，先执行现有“发送 prompt 给 AI”的主流程。
- 只有已登记的 AI 生成问题才后台异步上送点击。
- 固定兜底问题不调用点击接口。
- 上送失败不提示用户，不影响 AI 消息发送。
- 不要求本地 outbox，失败可静默丢弃。

## 8. 后台管理接口设计

接口建议放在：

- `backoffice/quick_question_views.py`
- `backoffice/quick_question_serializers.py`
- `backoffice/urls.py`

### 8.1 快捷问题配置列表与新增

说明：后台配置列表读写 `ChatGuideQuickQuestionConfig` 表。

```text
GET  /api/admin/v1/conversations/quick-questions/configs/
POST /api/admin/v1/conversations/quick-questions/configs/
```

列表筛选：

- `keyword`：搜索 title / prompt。
- `category`：问题分类。
- `locale`：语言。
- `is_active`：启用状态。
- `page`、`page_size`。

新增字段：

- `title`
- `prompt`
- `category`
- `locale`
- `is_active`
- `metadata`

### 8.2 快捷问题配置编辑

```text
GET   /api/admin/v1/conversations/quick-questions/configs/{id}/
PATCH /api/admin/v1/conversations/quick-questions/configs/{id}/
```

编辑规则：

- 已存在历史点击或生成引用的配置，不做物理删除。
- 修改 `title` 或 `prompt` 后，只影响后续下发，不回写历史生成记录。
- 所有编辑写入后台操作日志。

### 8.3 启用与停用

```text
POST /api/admin/v1/conversations/quick-questions/configs/{id}/enable/
POST /api/admin/v1/conversations/quick-questions/configs/{id}/disable/
```

规则：

- 启用：`is_active=true`。
- 停用：`is_active=false`。
- 停用后不影响历史生成记录和点击统计。

### 8.4 查看客户端生成记录

说明：生成记录列表读取 `ChatGuideGeneratedQuestionRecord` 表。

```text
GET /api/admin/v1/conversations/quick-questions/generated-records/
GET /api/admin/v1/conversations/quick-questions/generated-records/{id}/
```

列表筛选：

- `keyword`：搜索 title / prompt。
- `user_id`：登记用户。
- `member_id`：关联成员。
- `category`：分类。
- `created_at_start`、`created_at_end`。
- `click_count_min`、`click_count_max`。

列表字段：

- `id`
- `title`
- `prompt_preview`
- `category`
- `user`
- `member`
- `click_count`
- `created_at`

详情字段：

- 完整 `prompt`
- 登记记录不提供 thread / block 跳转；需要排查具体卡片时以客户端日志为准。

## 9. 后台前端页面设计

### 9.1 菜单与路由

新增二级菜单：

```text
对话
  ├─ 用户对话
  └─ 快捷问题配置
```

新增路由：

```text
/conversations/quick-questions
```

建议文件：

- `backoffice-web/src/views/ConversationQuickQuestionsView.vue`
- `backoffice-web/src/api/modules/conversationQuickQuestions.ts`

也可以复用：

- `backoffice-web/src/api/modules/conversations.ts`

若 `conversations.ts` 已经较大，推荐新建 `conversationQuickQuestions.ts`。

### 9.2 页面结构

页面标题：`快捷问题配置`

页面采用 tabs：

```text
┌────────────────────────────────────────────────────────────┐
│ 快捷问题配置                                      [新增问题] │
├────────────────────────────────────────────────────────────┤
│ [配置管理] [生成记录] [点击统计]                            │
├────────────────────────────────────────────────────────────┤
│ 筛选区                                                     │
│ 关键词 / 分类 / 状态 / 来源 / 时间范围                      │
├────────────────────────────────────────────────────────────┤
│ 表格                                                       │
└────────────────────────────────────────────────────────────┘
```

### 9.3 配置管理 tab

用途：管理后台固定快捷问题。

筛选项：

- 关键词。
- 分类。
- 语言。
- 状态：全部 / 启用 / 停用。

表格列：

- 问题标题。
- Prompt 预览。
- 分类。
- 语言。
- 状态。
- 创建人。
- 最近更新。
- 操作：编辑 / 启用 / 停用 / 查看生成记录。

新增 / 编辑弹窗字段：

- 展示文案 `title`。
- 完整 prompt `prompt`。
- 分类 `category`。
- 语言 `locale`。
- 是否启用 `is_active`。
- 备注或标签 `metadata`。

交互规则：

- `title` 必须短，建议不超过 30 个中文字符。
- `prompt` 可以更完整，用于点击后发送给 AI。
- 停用操作需要二次确认。
- 编辑保存后刷新当前列表。

### 9.4 生成记录 tab

用途：查看客户端 AI 成功生成并登记过的问题。固定兜底问题不在本列表展示。

筛选项：

- 关键词。
- 用户 ID。
- 成员 ID。
- 分类。
- 时间范围。
- 点击次数范围。

表格列：

- 问题标题。
- Prompt 预览。
- 用户。
- 成员。
- 点击次数。
- 创建时间。
- 操作：查看详情 / 查看对话。

详情抽屉：

- 完整 title。
- 完整 prompt。
- category。
- user_id。
- member_id。

### 9.5 点击统计 tab

第一阶段可以只做轻量统计：

- 总登记问题数。
- AI 生成问题数。
- AI 生成问题点击次数。
- 总点击次数。
- 点击率 Top 20。
- 最近 7 天点击趋势。

若排期紧张，可以把点击统计延后，只在生成记录列表展示 `click_count`。

## 10. RBAC 与权限

新增权限建议：

| 权限 code | 类型 | 名称 | 父级 |
| --- | --- | --- | --- |
| `menu:conversations:quick_questions` | menu | 快捷问题配置 | `menu:conversations` |
| `conversation.quick_question.config.read` | api | 查看快捷问题配置 | `menu:conversations:quick_questions` |
| `conversation.quick_question.config.create` | button | 新增快捷问题 | `menu:conversations:quick_questions` |
| `conversation.quick_question.config.update` | button | 编辑快捷问题 | `menu:conversations:quick_questions` |
| `conversation.quick_question.config.enable` | button | 启用快捷问题 | `menu:conversations:quick_questions` |
| `conversation.quick_question.config.disable` | button | 停用快捷问题 | `menu:conversations:quick_questions` |
| `conversation.quick_question.generated.read` | api | 查看生成记录 | `menu:conversations:quick_questions` |
| `conversation.quick_question.click.read` | api | 查看点击记录 | `menu:conversations:quick_questions` |

权限落地位置：

- `backoffice/rbac.py` 的 `bootstrap_admin_permissions` 增加默认权限。
- 超级管理员默认拥有。
- 后续普通后台角色按需授权。

## 11. 客户端接入要求

客户端相关改动属于配套任务，本工单只定义服务端契约。

### 11.1 登记触发点

触发时机：

- AI 生成成功，并且本地 guide block 已回写成功后。

不应触发的情况：

- 只是重新进入已有对话。
- 只是从本地缓存加载已有 guide card。
- 服务端 block sync 拉取导致卡片刷新。
- 无绑定成员使用固定问题。
- AI 生成失败、解析失败后使用固定问题。

### 11.2 点击触发点

触发时机：

- 用户点击某个 `ChatGuideQuestion`。
- 现有逻辑继续把 `question.prompt` 发送给当前对话 AI。
- 如果该问题来自已登记的 AI 生成结果，再后台异步上送点击统计。
- 如果该问题来自固定兜底，不上送点击统计。

### 11.3 失败处理

登记失败：

- 不影响 UI。
- 不影响本地 guide card。
- 不影响 block sync。
- 可写客户端 debug 日志。

点击上送失败：

- 不影响 prompt 发送。
- 不提示用户。
- 可 best-effort 重试。

## 12. 隐私与合规

科普问题 prompt 可能包含用户年龄、性别、职业、体检异常、慢病风险等敏感健康上下文，因此必须注意：

- 客户端登记时不要上传完整成员资料，只上传生成后的问题本身。
- 不上传 `member_profile_digest`、complete-data、原始 AI 请求上下文、客户端设备上下文等扩展信息。
- 服务端普通日志不要打印完整 prompt。
- 后台页面默认展示 prompt 预览，完整 prompt 只在详情中展示。
- 后台访问必须受 RBAC 控制。
- 导出能力不在第一阶段提供。

## 13. 日志与可观测性

服务端建议增加结构化日志：

登记成功：

```text
chat.guide.question.registered user=<id> member=<id> count=<n>
```

登记失败：

```text
chat.guide.question.register_failed user=<id> member=<id|null> error=<category>
```

点击成功：

```text
chat.guide.question.clicked user=<id> member=<id|null> question=<id|null>
```

注意：

- 日志不要输出完整 prompt。
- 可以输出 title hash 或 prompt hash。

## 14. 兼容与迁移

### 14.1 与现有客户端固定三条问题兼容

客户端当前固定问题示例：

```json
[
  {
    "id": "tcm_medicine_precautions",
    "title": "使用中成药有哪些注意事项?",
    "prompt": "使用中成药有哪些注意事项?",
    "category": "popular_science"
  },
  {
    "id": "astragalus_suitable_groups",
    "title": "黄芪适合哪些人群服用?",
    "prompt": "黄芪适合哪些人群服用?",
    "category": "popular_science"
  },
  {
    "id": "lactose_intolerance_handling",
    "title": "乳糖不耐受如何处理?",
    "prompt": "乳糖不耐受如何处理?",
    "category": "popular_science"
  }
]
```

落地建议：

- 第一阶段仍保留客户端固定三条兜底，避免后台配置接口未上线时影响客户端。
- 后台配置上线后，可新增一个“拉取启用固定快捷问题”的客户端接口，后续再替换客户端写死配置。
- 本工单优先完成登记和点击统计，不强制客户端依赖后台配置下发。

### 14.2 与现有对话同步兼容

本工单新增的数据不进入 `ChatMessageBlock.payload` 的主同步协议，不改变 `block_updates` 语义。

原因：

- guide card 的展示数据仍由客户端本地与 chat_sync block 负责。
- 本工单登记数据用于后台运营和统计。
- 将统计数据混入 block payload 会增加对话主链路复杂度。

## 15. 开发任务拆分

### 15.1 服务端 medical

1. 新增模型：
   - `ChatGuideQuickQuestionConfig`
   - `ChatGuideGeneratedQuestionRecord`
2. 新增 migration。
3. 新增 serializer：
   - 客户端登记 serializer。
   - 客户端点击 serializer。
4. 新增客户端接口：
   - `POST /api/v1/medical/chat-guide/questions/register/`
   - `POST /api/v1/medical/chat-guide/questions/click/`
5. 增加成员权限校验：
   - `member_id` 非空时校验当前用户可访问。
6. 点击接口使用数据库原子更新递增 `click_count`。
7. 增加单元测试。

### 15.2 服务端 backoffice

1. 新增后台 serializer。
2. 新增后台 view：
   - 配置列表。
   - 新增配置。
   - 编辑配置。
   - 启用配置。
   - 停用配置。
   - 生成记录列表。
   - 生成记录详情。
3. 在 `backoffice/urls.py` 注册路由。
4. 在 `backoffice/rbac.py` 增加菜单与按钮权限。
5. 写后台接口测试：
   - 无权限访问失败。
   - 超级管理员访问成功。
   - 新增、编辑、启用、停用成功。
   - 生成记录筛选成功。

### 15.3 backoffice-web

1. 新增路由：
   - `/conversations/quick-questions`
2. 新增菜单：
   - `对话 / 快捷问题配置`
3. 新增 API 模块或扩展 `conversations.ts`。
4. 新增页面：
   - `ConversationQuickQuestionsView.vue`
5. 页面支持：
   - 新增问题。
   - 编辑问题。
   - 启用问题。
   - 停用问题。
   - 查看生成记录。
   - 查看点击数。
6. 补充 TypeScript 类型。
7. 执行构建校验。

### 15.4 客户端

1. 新增登记 API client。
2. 新增点击 API client。
3. AI 问题生成成功后后台异步登记。
4. 固定兜底问题不登记。
5. 点击已登记 AI 生成问题后后台异步上送点击。
6. 点击固定兜底问题不上送点击。
7. 所有网络失败不阻断主流程。
8. 不要求本地 outbox；点击和登记均按后台异步 best-effort 处理。

## 16. 验收标准

### 16.1 客户端登记

- 新建对话并生成 AI 科普问题后，服务端可查到 3 条登记记录。
- 登记接口失败时，客户端 guide card 仍正常展示。
- 重复上送同一批问题可能产生重复记录，第一阶段接受该误差，后续按数据情况再补去重。
- 无绑定成员、AI 失败、解析失败等固定问题场景不会产生登记记录。

### 16.2 点击统计

- 用户点击问题后，当前对话 AI 请求照常发送。
- 已登记 AI 生成问题的点击后台异步上送。
- 固定兜底问题的点击不上送。
- 服务端对应问题 `click_count` +1。
- 重复上送会重复 +1，第一阶段接受该统计误差。
- 找不到登记记录时不增加点击数。

### 16.3 后台配置

- 后台出现 `对话 / 快捷问题配置` 二级菜单。
- 可以新增快捷问题。
- 可以编辑快捷问题。
- 可以启用、停用快捷问题。
- 停用的问题不影响历史生成记录展示。

### 16.4 后台生成记录

- 可以查看客户端 AI 生成记录。
- 可以按用户、成员、分类、时间、点击次数筛选。
- 可以查看完整 prompt 与点击次数。
- 可以复制登记记录 id、成员 id、问题 id 辅助排查。

## 17. 风险与注意事项

1. 敏感信息风险：
   - prompt 中可能带健康信息，后台展示必须受权限控制。
2. 重复统计风险：
   - 第一阶段不做登记幂等和点击幂等，客户端重复上送可能导致重复记录或点击数偏高。
3. 主流程阻塞风险：
   - 客户端登记和点击上送不能 await 到影响 UI。
4. 数据量增长风险：
   - AI 生成记录可能增长较快，需通过后台筛选与索引控制查询成本。
5. 后台配置与客户端固定问题双轨风险：
   - 第一阶段明确后台配置不强依赖客户端下发，避免引入额外发布阻塞。

## 18. 推荐落地顺序

1. 先做服务端模型和客户端登记、点击接口。
2. 再让客户端接入异步登记和点击上送。
3. 再做 backoffice 生成记录查询。
4. 最后做后台快捷问题配置新增、编辑、启停。
5. 后续再评估是否让客户端从服务端拉取固定快捷问题配置。

## 19. 待确认问题

1. 固定兜底问题是否也需要登记为生成记录？
   - 已明确：不登记。只有 AI 成功生成的问题才登记。
2. 后台配置问题是否第一阶段就要下发给客户端？
   - 推荐第一阶段不下发，只做配置管理和未来能力预留。
3. prompt 是否允许后台完整展示？
   - 推荐超级管理员可查看完整 prompt，其他角色只看预览。
