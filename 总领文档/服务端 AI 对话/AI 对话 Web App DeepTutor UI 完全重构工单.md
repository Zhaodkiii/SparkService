# AI 对话 Web App DeepTutor UI 完全重构工单

## 1. 工单信息

| 项目 | 内容 |
|---|---|
| 主工单 | `CHAT-WEB-017` |
| 类型 | Web UI 框架与对话工作区完全重构 |
| 实现根目录 | `/Users/hua/Documents/project/Reference/SparkService/chat-web` |
| 服务端契约 | `/Users/hua/Documents/project/Reference/SparkService/chat_sync` |
| DeepTutor 源码快照 | `/Users/hua/Documents/project/Reference/LookHealthClient/DeepTutor-main/web` |
| 关联阶段 | P2 流式闭环、P3 统一上下文；预留 P4–P6 UI 插槽 |
| 工单日期 | 2026-08-25 |
| 交付类型 | 源码迁移 + Spark 数据层适配 + 视觉回归 + 真实后端联调 |

### 1.1 工单目标

完全重构 `chat-web` 的 App Shell、侧边栏、会话列表、对话头部、消息滚动区、消息操作和 Composer，在几何尺寸、信息密度、字体层级、间距、表面、滚动行为和交互反馈上对齐 DeepTutor 快照。

重构后仍必须使用 SparkService 的真实业务架构：

```text
Spark Auth
  → ChatThread / ChatMessage / ChatMessageBlock
  → ChatRun / RunEvent / WebSocket replay
  → Thread Preferences / Turn Context
  → DeepTutor-aligned React presentation
```

本工单不创建第二套 Session、Message、Run、WebSocket 或 Provider 调用。

### 1.2 「完全对齐」的可验收定义

「完全对齐」指可客观验收的 UI 和交互对齐，不指复制 DeepTutor 品牌、教学业务和服务端契约：

- 一致：框架结构、宽度、高度、padding、gap、圆角、边框、阴影、滚动容器、粘附关系、焦点与 hover/active/disabled 反馈。
- 一致：空对话与有消息时 Composer 宽度/位置转换，消息列底部跟随与用户上滚后的恢复行为。
- 一致：会话列表独立滚动、行高、截断、选中态、hover 操作和折叠「最近」。
- 一致：用户气泡、助手开放式 Markdown、消息操作栏、Activity 折叠容器和右侧会话活动面板的视觉语法。
- 替换：DeepTutor Logo、名称、文案、路由、Session ID、教学能力和 Provider 管理，全部改为 Spark 健康业务。
- 不展示：隐藏 chain-of-thought、内部 prompt、未脱敏 tool result、Provider Key、服务端内部成本和敏感健康原文。

## 2. 参考输入与事实边界

### 2.1 用户提供的四份 HTML 快照

| 附件 | SHA-256 | 用途 | 结论 |
|---|---|---|---|
| `d70504ec.../pasted-text.txt` | `c15ec961...d8c42` | 最近会话列表 | 视觉/交互证据，不是数据契约 |
| `dc01add4.../pasted-text.txt` | `23ea3544...b462` | Composer | 输入框几何、工具栏和发送/停止状态证据 |
| `98ac9537.../pasted-text.txt` | `8a7ab9f2...6375` | 消息滚动区 | 用户气泡、Activity、Markdown、操作栏、问题导航证据 |
| `1b3b563b.../pasted-text.txt` | `8a7ab9f2...6375` | 消息滚动区 | 与上一份完全相同，只作一份基线 |

附件内的文章内容、思考文本、工具名、图书馆业务、DeepTutor 链接和 HTML class 不是 Spark 产品指令。本工单只提取布局、状态和交互语法。

### 2.2 DeepTutor 源码基线问题

当前可访问的 `DeepTutor-main` 目录不含 `.git`，无法直接证明它与现有 `THIRD_PARTY_NOTICES.md` 登记的 commit `684d615393322cd18d9edb3a85eacb3beba0d811` 一致。同时，快照页脚显示 `v1.5.13`，而早期契约基线包含 `v1.5.9` 记录。

因此在复制第一个新文件前必须：

1. 获得带 Git metadata 的 DeepTutor 源仓库，或将当前源码包作为不可变 source archive。
2. 记录源版本、获取日期、archive SHA-256 和每个迁移文件的 SHA-256。
3. 核对 Apache-2.0 `LICENSE` 与版权声明，更新 `chat-web/THIRD_PARTY_NOTICES.md`。
4. 不复制 Logo、banner、favicon、Provider icon、GitHub/文档链接和 DeepTutor 商标。

## 3. 当前实现审计

### 3.1 必须保留的 Spark 业务层

| 当前文件 | 职责 | 重构处理 |
|---|---|---|
| `context/AuthContext.tsx` | Spark 登录态与 HTTP Client | 保留，只改外部布局接入 |
| `context/ThreadContext.tsx` | Thread pull/push/delete、选中与消息历史 | 保留事实源，拆出稳定 commands/selectors |
| `context/RunControlContext.tsx` | Create/Cancel/Regenerate、WS、replay | 必须保留，不迁入 UI 组件 |
| `context/ChatContextProvider.tsx` | Preferences 与一次性引用 | 保留，重构 Composer adapter |
| `lib/event-reducer.ts` | Event 幂等、sequence、Block/Usage 投影 | 保留为消息 UI 唯一流式事实源 |
| `lib/api/chat-sync-api.ts` | Thread/Message 同步 | 保留，新 UI 不直接拼 URL |
| `lib/api/run-api.ts` | Run 控制面 | 保留，不直连 Provider |
| `types/chat.ts` / `types/run.ts` / `types/sync.ts` | Spark wire contract | 保留并按服务端扩展 |

### 3.2 必须替换的当前 UI

| 当前问题 | 目标 |
|---|---|
| `app-shell` 使用 `300px + content + 64px + 88px` 四列 | 改为 DeepTutor 式 `220px/60px sidebar + minmax(0,1fr)` |
| `GlobalNavigationRail` 位于最右侧 | 主业务导航合并到左侧侧边栏 |
| `action-rail` 长期占据中间右侧 | 替换为头部 Activity 按钮和按需打开的右侧 Panel |
| `WorkspaceSidebar` 只有品牌/新建/搜索/列表 | 重构为主导航 + 最近会话 + 底部导航 |
| 当前 Thread 行没有 rename/delete hover action | 对齐快照的行密度、操作和运行态 |
| `workspace__header` 是 72px 有底边的系统栏 | 改为无重边框的 `max-w-[960px]` 标题/操作头部 |
| 消息区不是独立滚动事实 | 使用 `data-chat-scroll-root` 与 `overflow-y-auto` |
| 当前助手区块只有基础文本 | 建立 Markdown、Activity、错误、操作栏和 Usage 插槽 |
| 当前 Composer 为简化文本框 + 独立 ContextToolbar | 整合为 DeepTutor 式 26px Card 与底部工具栏 |
| 全局 CSS 是临时 P0/P3 样式 | 建立 Snow Token、serif/sans 字体和局部组件样式 |

## 4. 目标信息架构与路由

### 4.1 桌面端框架

```text
┌─ Spark Sidebar 220px / collapsed 60px ─┬─ Chat Workspace minmax(0,1fr) ─┬─ Activity Panel 0/360px ─┐
│ 品牌 + 收起                         │ Thread Header                         │ 活动/附件/预览       │
│ 主页 / 医疗 / 饮食 / 运动           │ Message Scroll Root                    │ 按需打开                 │
│ 最近会话（独立滚动）              │ Composer                               │                          │
│ 知识库 / 记忆 / 设置               │                                        │                          │
└───────────────────────────────────┴───────────────────────────────────────┴──────────────────────────┘
```

`Activity Panel` 不常驻占位。打开后，超宽桌面并排，小桌面/平板覆盖，手机使用全高 Sheet。

### 4.2 路由表

| 导航 | 目标路由 | 本工单范围 |
|---|---|---|
| 主页 | `/home/[[...threadId]]` | 完整 AI 对话工作区 |
| 医疗 | `/medical` | 保留真实路由/权限态，页面业务可独立工单 |
| 饮食 | `/nutrition` | 保留真实路由/权限态，页面业务可独立工单 |
| 运动 | `/exercise` | 保留真实路由/权限态，页面业务可独立工单 |
| 知识库 | `/knowledge` | 底部入口；KB 未就绪时显示准确未开放态 |
| 记忆 | `/memory` | 底部入口；不复制 DeepTutor Memory API |
| 设置 | `/settings` | 账号/主题/对话设置入口 |

现有 `/chat` 在切换期保留为兼容重定向：

```text
/chat                 → /home
/chat/{thread_id}     → /home/{thread_id}
```

路由迁移不改变 `thread_id`、不新建 Thread、不丢失正在运行的 Run。

## 5. 侧边栏完全重构

### 5.1 尺寸与布局

| 状态 | 规格 |
|---|---|
| 展开桌面 | `w-[220px] h-dvh shrink-0 flex flex-col bg-[var(--secondary)]` |
| 收起桌面 | `w-[60px]` 图标轨道，tooltip 显示名称 |
| 移动端 | `220px` 宽 overlay drawer + scrim，关闭时 `inert` |
| 顶部 | `h-14 px-4`，Spark Logo/文字标 + 折叠按钮 |
| 主导航 | `px-2 pt-1`，行高约 34px，字号 `13.5px` |
| 最近会话 | `mt-4 min-h-0 flex-1 flex-col`，内部 `overflow-y-auto` |
| 底部导航 | 顶部细分隔线，`px-2 py-2`，不显示 DeepTutor 版本/GitHub/文档 |

### 5.2 主导航

```text
主页      House
医疗      HeartPulse
饮食      Utensils
运动      Activity
```

- active：`bg-[var(--accent)] font-medium text-[var(--foreground)]`。
- inactive：`text-[var(--foreground)]/85`，hover 使用 `background/60`。
- 图标默认 `16px / stroke 1.5`，active `stroke 1.9`。
- 导航必须使用 Next `Link`，active 由 pathname 计算，不使用永远选中首项的静态 button。
- 未实现的业务页不可假导航到对话页；显示明确的加载/空/无权/未开放页。

### 5.3 最近会话

- 标题行文案为「最近」，字号 `11.5px`，可折叠，收起值只保存 UI preference，不保存会话数据。
- 会话列表使用 `ThreadContext.threads`，不调用 DeepTutor `listSessions`。
- 列表容器必须是唯一纵向滚动面：`min-h-0 flex-1 overflow-y-auto px-2 pb-2 pt-0.5`。
- 每行 `px-2.5 py-1.5 rounded-lg gap-2`，标题 `13px truncate`，过长标题不增加行高。
- 选中态必须可见且与主导航 active 协调，不只依赖颜色。
- hover/focus-within 显示重命名和删除，图标 `10px`，操作可点区不小于 `28×28px`；视觉图标可小，点击区不随之缩小。
- 运行中 Thread 显示轻量状态图标/文字，状态来自 Run 事实，不根据标题样式猜测。
- loading 首次使用 skeleton；后续 Run 完成刷新列表时静默替换，不闪回 skeleton。
- 重命名使用 Thread push 的完整 DTO 或后端专用 command，不只上送 `{title}` 导致其他字段被默认覆盖。
- 删除走 `/api/v1/ai/chat/sync/thread-delete/` 软删除，删除当前 Thread 后选择下一可见 Thread 或跳转 `/home`。
- 新建对话可通过点击「主页」或品牌旁新建操作完成；若当前 Run 仍在执行，不得静默把订阅切到新 Thread。

### 5.4 底部导航

```text
记忆      Brain
知识库    BookOpen
设置      Settings
```

用户要求的展示顺序以「知识库、记忆、设置」为准；代码中使用显式数组固化顺序，不依赖对象遍历顺序。不保留 DeepTutor VersionBadge、Docs 和 GitHub 链接。

## 6. 对话头部

### 6.1 几何规格

```text
mx-auto flex w-full max-w-[960px]
flex-wrap items-center justify-between
gap-x-3 gap-y-1.5
px-4 pt-14 pr-16 pb-0
md:px-6 md:pt-3 md:pr-6
```

桌面端与 DeepTutor 一致使用 `max-w-[960px]` 中轴；移动端的额外 top/right padding 必须与抽屉开关和安全区实测后确定，不盲目照搬一个快照值。

### 6.2 标题与重命名

- 标题按钮使用 serif `17px / 600`，tracking `-0.01em`，最大宽度内 truncate。
- 新 Thread 显示「新对话」，在第一条消息被服务端接受前禁用重命名。
- 可重命名时 hover 显示 PenLine；点击后就地切换成 input。
- Enter/失焦保存，Escape 取消，最长 100 字符，保存中和保存失败有独立状态。
- 保存成功以服务端返回 Thread DTO 覆盖本地基线。

### 6.3 头部操作

| 操作 | P0/P3 实现策略 | 开放门禁 |
|---|---|---|
| 保存到笔记本 | 保留按钮位，默认 disabled | Spark Notebook 实体/API 存在后开放 |
| 下载 Markdown | 客户端从当前可见 Message/Block 投影生成 | 排除 system/tool 秘密、隐藏 reasoning、签名 URL |
| 活动 | 打开 SessionActivityPanel | 只展示公开 Event/Block/附件摘要 |

图标按钮使用 `32×32px`、圆角 `8px`、Lucide `16px / stroke 1.7`，带 Tooltip，active/disabled 语义与快照一致。

## 7. 消息滚动区与卡片

### 7.1 滚动容器

```text
relative flex w-full flex-1 min-h-0 flex-col
  └─ data-chat-scroll-root="true"
     w-full flex-1 min-h-0 overflow-y-auto
     [scrollbar-gutter:stable_both-edges]
     pt-6 pb-12
     └─ data-chat-column="true"
        mx-auto w-full max-w-[960px] space-y-9 px-6
```

- `body` 和 App Shell 不滚动；消息根容器是主滚动面。
- 顶部 32px、底部 40px 使用 mask fade，底部 padding 必须足够，最后段文本不可停在 fade 里。
- 初次打开定位最新消息；正在生成且用户位于底部时跟随 delta。
- 用户主动上滚超过阈值后停止跟随，显示「回到最新」；不每个 token 抢回滚动位置。
- 切换 Thread 时清空上一 Thread 的 scroll following state，但不污染新 Thread 的消息投影。
- 使用 `data-turn-key` 作为问题导航锚点，键值来自 Spark Message ID，不使用数组 index 作持久身份。

### 7.2 用户消息

- 容器 `flex justify-end`，气泡列 `max-w-[75%] items-end gap-1.5`。
- 气泡 `rounded-2xl bg-[var(--secondary)] px-4 py-2.5 text-[14px] leading-relaxed shadow-sm`。
- 顶部小标签显示公开 capability 名，默认「聊天」，不显示 Provider/model 内部标识。
- hover/focus-within 显示复制/编辑/分支导航。P3 先开放复制；编辑只在「从原消息创建新 Run 分支」契约完成后开放。
- 一次性引用在气泡下方使用安全 ContextReferenceTree 摘要，不渲染医疗原文。

### 7.3 助手消息

- 助手消息使用开放式内容列，不用整块强调气泡包裹 Markdown。
- 正文使用 serif，UI/工具状态使用 sans；标题、列表、引用、表格、代码、分隔线对齐 DeepTutor 密度。
- Streaming 与 History 必须经过同一 `ChatBlockRenderer`；不允许流式组件和历史组件各自解析 Markdown。
- 文本 Block 只渲染服务端公开输出；system message 始终过滤。
- 未知 Block kind 使用安全 fallback，不将原始 JSON 显示给用户。

### 7.4 Activity / Reasoning / Tool 区

快照包含「已完成 · 1m 48s」折叠区和多条思考/工具记录。Spark 对齐其视觉语法，但数据必须使用公开 Event/Block：

| 可展示 | 不可展示 |
|---|---|
| `thinking/answering` 阶段名与持续时间 | 模型隐藏 chain-of-thought 原文 |
| 公开 tool name、安全参数摘要、状态 | 完整工具参数、身份 ID、Token、内部 URL |
| 公开 observation 摘要与引用 | 未脱敏 tool result/医疗原文 |
| 失败/超时/取消与可恢复动作 | Python exception、Provider response body |

P2 只有纯文本时，Activity 头可显示生成阶段；Tool Row 在 P4 契约完成后通过 Block Renderer 插槽开放。不使用 DeepTutor `TracePanels` 的事件类型。

### 7.5 消息操作栏

| 角色 | 操作 | 开放条件 |
|---|---|---|
| 用户 | 复制 | 立即开放 |
| 用户 | 编辑/分支 | 服务端 context parent 与分支投影契约完成 |
| 助手 | 复制 | 只复制可见正文 |
| 助手 | 语音播放 | 浏览器 TTS/服务端语音策略完成后开放 |
| 助手 | 重新生成 | 仅最后一个可重生回合，调用 Spark Regenerate API |
| 回合 | 删除 | Message tombstone/分支行为冻结后开放 |
| 助手 | Usage | 只显示已批准的 `usage.final`；成本未准确时不显示假 `$0.00` |

操作栏默认弱化，hover/focus-within 可见；触屏不能依赖 hover，最新助手消息的主操作常驻或通过更多菜单访问。

### 7.6 问题导航

- 桌面超宽屏可显示 TurnNavigator，定位在消息列左沟槽。
- 键条目仅对用户提问生成，`aria-label` 为序号 + 安全截断文本。
- 导航是视觉增强，不作为消息存在性事实源；手机和窄屏隐藏。
- 点击后定位 `data-turn-key` 并给 `data-turn-bubble` 短暂焦点反馈，遵守 reduced motion。

## 8. Composer 完全对齐

### 8.1 容器与位置

| 状态 | 规格 |
|---|---|
| 空 Thread | `max-w-[768px]`，居中偏下，与欢迎文案组成首屏 |
| 有消息 | `max-w-[960px] px-6 pb-5 pt-1`，底部固定在 Workspace flex 流 |
| 宽度过渡 | `650ms cubic-bezier(0.16,1,0.3,1)` |
| Card | `rounded-[26px] border bg-[var(--card)]` |
| 阴影 | `0 1px 2px rgba(0,0,0,.025), 0 10px 28px -10px rgba(0,0,0,.08)` |
| 输入 | `px-4 pt-3.5 pb-2`，`16px` 字号，最高 200px |
| 工具栏 | `px-3 pb-2 pt-0.5`，高 32px |

### 8.2 上下文与附件区

- P3 `ContextToolbar` 不再作为 Composer 外部的独立栏，其业务能力迁入 Composer 内部的 ContextReferenceTree 和底部 selector。
- 已选一次性引用放在 Card 顶部浅 muted 区，带底分隔线，只显示安全类型/标题。
- 附件支持 drag/drop、粘贴、文件选择、上传/登记状态、预览和移除；只有 ready `file_id` 可进入 Run。
- 附件可接受类型、大小和数量以 Spark File API 为准，不照搬快照中 32,000 文本或 DeepTutor accept 列表。
- 当前后端只提供文件 metadata 时，UI 不标记「AI 已读取正文」。

### 8.3 底部工具栏

```text
[聊天 ⌄]  [+]  …flex…  [知识库] [角色] [模型] [麦克风] [发送/停止]
```

| 控件 | Spark 语义 |
|---|---|
| 聊天模式 | P3 只开放 `chat`；P6 再加 research/solve/visualize 等 Capability |
| `+` | 文件、健康资源和已实现的一次性引用 |
| 知识库 | `chat_knowledge_backend_unavailable` 未解决前 disabled/hidden |
| 角色 | 编辑 Spark Preferences `persona`，不使用 DeepTutor Persona ID |
| 模型 | 只展示服务端 allowlist；`llm_selection` 真正参与 Run 路由后开放 |
| 麦克风 | 没有语音契约时 disabled 且有 Tooltip，不假录音 |
| 发送 | 调用 `RunControlContext.createRun` |
| 停止 | Run 非终态时同一圆形按钮 morph 为 square，调用 `cancelRun` |

工具栏在宽度不足时，非关键 selector 收缩为图标；不允许挤压发送按钮或造成水平滚动。

### 8.4 输入行为

- Enter 发送，Shift+Enter 换行，IME composition/`keyCode 229` 期间不发送。
- textarea 最小高度：空 Thread 64px，有消息 28px；自动增长到 200px 后内部滚动。
- 发送前等待 Preferences 保存与附件登记；Run 被 `202/200 replayed` 接受后才清空文本/一次性引用。
- 未知网络结果使用原 Idempotency-Key 恢复，不重复发送。
- 正在生成时发送按钮变为停止；请求取消中防止重复点击，但不立即伪造 cancelled 终态。

## 9. Activity Panel

### 9.1 目标

替换当前常驻 `action-rail`，由头部 PanelRight 按钮控制。面板包含：

- 本轮/会话 Run 状态与时间线。
- 公开 Tool Activity（P4 开放）。
- 本轮引用、ManagedFile 和安全 Context Summary。
- 附件预览，下载 URL 按需获取，不持久化签名 URL。
- 后续结构化 Block 预览。

面板不展示 DeepTutor Space/Notebook/Book/Agent 实体，不读取完整 request snapshot、system prompt 或隐藏 reasoning。

### 9.2 响应式

| 宽度 | 行为 |
|---|---|
| `>= 1440px` | 360px 右侧并排 Panel，Chat 平滑让出空间 |
| `1024–1439px` | 360px overlay drawer + scrim |
| `<1024px` | 右侧/底部全高 Sheet，焦点圈和 Escape 关闭 |

## 10. 设计 Token 与全局样式

### 10.1 Token

```css
--background
--foreground
--card
--card-foreground
--primary
--primary-foreground
--secondary
--secondary-foreground
--muted
--muted-foreground
--accent
--border
--destructive
--ring
```

- Snow 主题为首要验收基线：白底、深色文字、中性灰表面、克制蓝色主操作。
- UI 使用 sans，会话标题与助手正文使用 serif；中文字体必须配置系统 fallback，不因 Lora 无中文字形导致失控。
- 禁止继续使用当前 `--snow/--ink/--line/--panel` 作为对话核心组件的唯一 Token；在过渡层做 alias 后逐步移除。
- Markdown 样式必须限定在 `.md-renderer`，不污染全站 `p/ul/table/code` 选择器。
- 不整份复制 DeepTutor `globals.css`，按 token、shell、markdown、composer、motion 分区迁移并登记来源。

### 10.2 动效

- 侧边栏展开/收起 200ms。
- 移动抽屉 200–220ms ease-out。
- Composer 宽度过渡 650ms spring-like cubic-bezier。
- button active 反馈 `scale(.90–.97)`，不用于危险操作确认。
- 流式文本不对每个 token 做 React motion。
- `prefers-reduced-motion` 下取消位移/缩放和循环呼吸，保留短透明度变化。

## 11. 目标源码目录

```text
chat-web/
├── app/
│   ├── (workspace)/
│   │   ├── layout.tsx
│   │   ├── home/[[...threadId]]/page.tsx
│   │   ├── medical/page.tsx
│   │   ├── nutrition/page.tsx
│   │   ├── exercise/page.tsx
│   │   ├── knowledge/page.tsx
│   │   ├── memory/page.tsx
│   │   └── settings/page.tsx
│   └── globals.css
├── components/
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   ├── MobileTopBar.tsx
│   │   └── ActivityPanelShell.tsx
│   ├── sidebar/
│   │   ├── SidebarShell.tsx
│   │   ├── WorkspaceSidebar.tsx
│   │   ├── PrimaryNavigation.tsx
│   │   ├── RecentThreads.tsx
│   │   ├── ThreadRow.tsx
│   │   └── SecondaryNavigation.tsx
│   ├── chat/home/
│   │   ├── ChatWorkspace.tsx
│   │   ├── ChatHeader.tsx
│   │   ├── ChatMessages.tsx
│   │   ├── UserMessage.tsx
│   │   ├── AssistantMessage.tsx
│   │   ├── MessageActions.tsx
│   │   ├── ActivityDisclosure.tsx
│   │   ├── TurnNavigator.tsx
│   │   ├── ChatComposer.tsx
│   │   ├── ComposerInput.tsx
│   │   ├── ComposerToolbar.tsx
│   │   ├── ContextReferenceTree.tsx
│   │   └── ChatBlockRenderer.tsx
│   ├── chat/activity/SessionActivityPanel.tsx
│   ├── common/MarkdownRenderer.tsx
│   └── ui/Tooltip.tsx
├── hooks/
│   ├── useChatAutoScroll.ts
│   ├── useChatOutline.ts
│   ├── useSidebarDrawer.ts
│   └── useSessionActivity.ts
├── lib/chat/
│   ├── message-projection.ts
│   ├── markdown-export.ts
│   ├── activity-projection.ts
│   └── turn-outline.ts
└── tests/
    ├── visual/deeptutor-alignment.spec.ts
    ├── sidebar/*.test.tsx
    ├── chat/*.test.tsx
    └── e2e/chat-workspace.spec.ts
```

`GlobalNavigationRail.tsx`、当前 `action-rail` 和临时 P0 fixture 在新 Shell 通过验收后删除，不在两套框架间长期加条件分支。

## 12. DeepTutor 源码迁移矩阵

### 12.1 可直接复用/原文件迁移

| DeepTutor 源文件 | 分类 | Spark 目标 | 要求 |
|---|---|---|---|
| `hooks/useChatAutoScroll.ts` | 原文件迁移 | 同名 | 保留 DOM data contract，改为 Spark message/run 输入 |
| `lib/chat-outline.ts` | 原文件迁移 | `lib/chat/turn-outline.ts` | 保留纯函数，使用 Spark Message ID |
| `components/ui/Tooltip.tsx` | 原文件迁移/已有目标 | 同名 | 核对当前 Spark 版与源版，不重复复制 |
| `lib/composer-keyboard.ts` | 已直接复用 | 同名 | 保留 IME 测试，不重复迁移 |
| `lib/use-auto-sized-textarea.ts` | 已直接复用 | 同名 | 调整参数而不新建第二 Hook |

### 12.2 部分迁移

| DeepTutor 源文件 | 可迁移部分 | 必须重写部分 |
|---|---|---|
| `components/layout/AppShell.tsx` | `h-dvh`、mobile drawer、scrim、Escape、`inert` | Spark 品牌、路由、Provider 组合 |
| `components/sidebar/SidebarShell.tsx` | `220/60px`、导航/最近/底部 flex 结构、折叠交互 | Spark 导航、Thread DTO、权限、账号操作 |
| `components/chat/home/ChatComposer.tsx` | Card 表面、drag overlay、引用区、附件预览、底部布局 | 所有 DeepTutor capability/KB/Book/Notebook/Agent 状态 |
| `components/chat/home/ComposerInput.tsx` | textarea 布局、高度与键盘行为 | Agent shortcut、DeepTutor picker 和数据绑定 |
| `components/chat/home/ChatMessages.tsx` | User/Assistant 几何、actions、activity shell、cost footer 样式 | DeepTutor Message/Event/Research/Quiz/AskUser/Attachment 业务 |
| `components/chat/home/TurnNavigator.tsx` | 左沟槽交互和动效 | Session message 类型与 index 身份 |
| `components/chat/home/ContextReferenceTree.tsx` | Tree/summary 视觉 | Book/Notebook/KB/Agent 实体与标识 |
| `components/chat/home/SessionActivityPanel.tsx` | Panel shell、tab/header 布局 | DeepTutor activity builder、Space/Book/Notebook/Tool 类型 |
| `components/common/MarkdownRenderer.tsx` | Markdown typography 和安全渲染结构 | DeepTutor citation/file/tool plugin、未审核 HTML |
| `app/(workspace)/home/[[...sessionId]]/page.tsx` | 头部 JSX、scroll shell、Composer 定位与 preview shell 片段 | 整个 UnifiedChatContext、Session API、capability 编排与 2,000+ 行页面状态 |

### 12.3 只参考重写/不可迁移

| 源码/资产 | 结论 | 原因 |
|---|---|---|
| `context/UnifiedChatContext.tsx` | 不迁移 | Session/Turn/Provider/Tool/KB 事实与 Spark 不兼容 |
| `lib/session-api.ts` | 不迁移 | Spark 使用 Chat Sync/Run API |
| `lib/unified-ws.ts` | 不迁移 | Spark 已有 ticket + Run Event replay |
| `TracePanels.tsx` 业务实现 | 仅视觉参考 | 事件和工具高度耦合，且包含 reasoning 展示 |
| Knowledge/Persona/Model API 文件 | 不迁移 | Spark Preferences/ai_config 是单一契约 |
| Logo/banner/favicon/provider-icons | 不迁移 | 商标与品牌边界 |
| locales 中的 DeepTutor 业务文案 | 不迁移 | 教学业务与 Spark 不一致 |
| 用户提供的渲染 HTML | 不直接进源码 | 是 DOM 快照，不含 React 边界和数据契约 |

## 13. 实施分阶段

### UI-R0：基线冻结与迁移登记

目标：在不改可见 UI 的前提下冻结契约、截图、源文件 hash 和视觉尺寸。

- 保存 1440×900、1920×1080、1024×768、390×844 参考截图。
- 建立 source-to-target manifest 并更新 `THIRD_PARTY_NOTICES.md`。
- 冻结 Spark Auth/Thread/Run/Event/Context 契约测试。
- 建立 `NEXT_PUBLIC_CHAT_UI_V2_ENABLED` 与 `/__fixtures/chat-v2` 状态画廊。

出口：每个计划迁移的文件都有分类、hash、许可证结论和负责工单。

### UI-R1：App Shell 与路由

目标：完成 `220/60px` 左侧栏、mobile drawer、主/底部导航和 `/home` 迁移。

- 保留 Auth Provider/route guard。
- 删除新 Shell 内的最右 GlobalNavigationRail 与 action rail。
- 完成 `/chat/* → /home/*` 兼容重定向。
- 完成手机 drawer、scrim、Escape、focus 恢复和 `inert`。

出口：框架几何对齐，所有导航可键盘访问，路由切换不丢失登录态。

### UI-R2：会话列表与头部

目标：完成「最近」独立滚动列表、选中/运行状态、重命名、软删除和 ChatHeader。

- 向 `ThreadContext` 增加 `renameThread`，内部使用安全完整 DTO/command。
- 会话行不直接发 API，只调用 Thread command。
- 下载 Markdown 使用安全导出投影。
- Activity 按钮先打开空/基础 Panel shell，不伪造 Tool 数据。

出口：100+ Thread 列表可滚动，头部和消息中轴完全一致，重命名/删除可恢复。

### UI-R3：消息滚动与渲染

目标：完成独立 scroll root、自动跟随、User/Assistant 几何、Markdown 与消息 actions。

- 拆分 `ChatMessages` 为纯投影组件，不调用 API。
- 流式 Block 与同步 Block 使用同一 renderer。
- 加入 safe Markdown、table/code overflow 和 copy/regenerate。
- 实现 TurnNavigator，窄屏关闭。

出口：长对话、长表格、代码块、流式 delta、上滚暂停跟随和刷新恢复通过。

### UI-R4：Composer 与 P3 Context

目标：完成 26px Composer、工具栏、发送/停止 morph、附件和上下文树。

- 保留 `ChatContextProvider` 的 Preferences/Draft 事实。
- 将 ContextToolbar 能力重组到 Composer 内，不改变发送冻结规则。
- 接入 drag/drop/paste/upload/register 状态。
- 知识库、模型、语音按各自后端门禁开关。

出口：输入、IME、上传、Context Draft、幂等发送、停止和移动键盘验收通过。

### UI-R5：Activity Panel 与公开运行状态

目标：用 Spark Event/Block/Context Summary 构建对齐 DeepTutor 的活动视觉。

- P2 先展示 queued/running/thinking/answering/completed/failed/cancelled。
- P4 再插入公开 Tool Call/Observation。
- P3 接入安全 Context Summary/附件。
- 严禁从 Provider delta 、request snapshot 或 DeepTutor reasoning 生成隐藏思维文本。

出口：活动面板可回放、可刷新恢复、可脱敏，不依赖组件内存。

### UI-R6：切换、清理与生产验收

目标：将 UI V2 升为默认，删除旧框架，完成真实后端、视觉、性能、无障碍与故障验收。

- 默认开启 UI V2，保留一个版本回退 flag。
- 删除 `GlobalNavigationRail`、action rail、旧 CSS 和重复组件。
- 扫描 DeepTutor import、品牌、API URL、Session/Turn 字段和未登记资产。
- 经过一个稳定版本后删除回退分支。

出口：本工单 Definition of Done 全部通过。

## 14. 子工单拆分

| 子工单 | 范围 | 主要文件 | 依赖 |
|---|---|---|---|
| `CHAT-WEB-017A` | 参考冻结、hash、NOTICE、fixture | notices/tests/fixtures | 无 |
| `CHAT-WEB-017B` | AppShell、drawer、路由迁移 | `layout/*`、`app/(workspace)/*` | 017A |
| `CHAT-WEB-017C` | 主/底部导航与收起态 | `sidebar/SidebarShell.tsx` | 017B |
| `CHAT-WEB-017D` | 最近 Thread、重命名、删除 | `RecentThreads.tsx`、`ThreadContext.tsx` | 017B/C |
| `CHAT-WEB-017E` | ChatHeader、Markdown 导出、Panel trigger | `ChatHeader.tsx` | 017D |
| `CHAT-WEB-017F` | Message scroll/auto-follow/TurnNavigator | `ChatMessages.tsx`、hooks | 017B |
| `CHAT-WEB-017G` | User/Assistant/Markdown/actions | message components/renderer | 017F |
| `CHAT-WEB-017H` | 26px Composer、toolbar、send/stop | composer components | 017B/G |
| `CHAT-WEB-017I` | P3 Context/附件适配 | Composer + Context Provider | 017H、P3 |
| `CHAT-WEB-017J` | Activity Panel/Event projection | activity components | 017E/G、P2/P4 |
| `CHAT-WEB-017K` | 视觉/无障碍/E2E/性能验收 | tests + screenshots | 017B–J |
| `CHAT-WEB-017L` | 旧 UI 清理与灰度切换 | app/css/flags | 017K |

同一文件同一时间只由一个子工单负责；`ChatWorkspace.tsx`、`globals.css`、`ThreadContext.tsx` 为高冲突文件，必须按 017B → D/E/F → H/I/J 顺序合并。

## 15. 后端 AI 对话接入矩阵

| UI 功能 | Spark 事实源/API | 展示层规则 |
|---|---|---|
| 最近会话 | `sync/thread-pull` | 只渲染未删 Thread，保持服务端顺序 |
| 新建/更名 | `sync/thread-push` | 使用完整 Thread DTO/受控 command |
| 删除 | `sync/thread-delete` | 软删除，删当前项后收敛路由 |
| 历史消息 | `sync/pull` | 进入统一 Message/Block projection |
| 发送 | `POST threads/{thread_id}/runs/` | 服务端 accepted 后才清 Composer |
| 停止 | `POST runs/{run_id}/cancel/` | 等待真实终态 Event |
| 重生 | `POST runs/{run_id}/regenerate/` | 沿用原 Snapshot，不读当前 Draft |
| 流式 | `/ws/chat/runs/` + ticket | Event 序列与 reducer 是事实源 |
| 断线恢复 | `runs/{run_id}/events?after_sequence=` | 先 replay，再继续 live |
| 使用量 | `usage.final` | 只显示已批准字段 |
| Preferences | `threads/{thread_id}/preferences/` | `If-Match` 乐观锁，冲突不静默覆盖 |
| 一次性引用 | Create Run references/attachments | 不进入下一轮 |
| Context Summary | P3 安全投影 | 不下发 prompt/医疗原文 |
| Activity/Tool | Run Event + Block | 不展示 hidden reasoning |

### 15.1 必须先补的契约缺口

- Thread 重命名的 Web command 需确保不会用不完整 DTO 覆盖 `member_id/scenario/active_head`。
- Thread list 的运行态如需对多个 Thread 展示，需增加批量 active-run summary；当前 `RunControlContext` 只跟踪选中 Thread。
- Safe Context Summary API 尚未实现，Activity Panel 不可直读 `ChatTurnContextSnapshot` JSON。
- `llm_selection` 在开放模型选择前需服务端 allowlist 验证和真实 Run 路由。
- 附件正文抽取尚未配置，UI 只能准确显示 metadata-only。
- 笔记本、语音、用户消息编辑分支和回合删除在后端契约完成前保持 disabled/hidden。

## 16. 测试与验收

### 16.1 视觉回归矩阵

| viewport | 必验收画面 |
|---|---|
| `1920×1080` | 展开/收起侧边栏、长对话、Activity Panel 并排 |
| `1440×900` | 默认会话、滚动列表、Composer、Panel overlay |
| `1024×768` | 窄桌面、长标题、表格/代码横向滚动 |
| `768×1024` | drawer 断点边界、键盘导航 |
| `390×844` | 移动抽屉、软键盘、Composer、Sheet |
| `375×667` | 小屏、safe area、200% 文本缩放 |

每个 viewport 至少保存：空对话、长对话、生成中、失败、侧边栏打开、Activity 打开、Composer 含引用七类截图。

几何验收误差：

- Shell/sidebar/header/composer 关键边界：单边不超过 `4px`。
- 字号、行高、圆角：不超过 `1px`。
- 颜色：使用 Spark Token 后视觉层级一致；不强制复制 DeepTutor 品牌色值。
- 文案长度差异导致的自然换行不作为失败，但不可水平溢出。

### 16.2 组件/单元测试

- Sidebar：active route、collapse、recents collapse、100 Thread 滚动、rename/delete、loading refresh 不闪烁。
- Shell：drawer Escape/scrim/navigation close、focus restore、closed `inert`。
- Header：title edit/save/cancel/error、download allowlist、Activity active state。
- Scroll：initial bottom、delta follow、user scroll pause、jump latest、Thread switch、TurnNavigator anchor。
- Message：history/live 同一 renderer、unknown Block、safe Markdown、copy、regenerate、usage unavailable。
- Composer：IME、auto height、drag depth、paste、attachment state、Context Draft、accepted clear、network unknown、send/stop。
- Activity：public event allowlist、unknown event、refresh replay、sensitive payload 不可见。

### 16.3 E2E

1. 登录 → `/home` → 创建 Thread → 发送 → 流式回答 → 完成。
2. 切换 Thread → 恢复历史 → 滚动位置和 active 状态正确。
3. 会话列表重命名/删除与 iOS 同步。
4. 生成中停止，按钮等待真实 terminal event。
5. WS 断线 → REST replay → 继续流式，消息不重复。
6. 附件/健康引用发送，第二轮不自动继承。
7. 重生沿用原 Snapshot，不带入当前 Composer Draft。
8. 刷新正在运行的 Thread，Event/Block/Activity 从服务端恢复。
9. 移动端打开/关闭侧边栏、输入、发送和打开 Activity Sheet，无水平溢出。
10. 退出/账号切换后上一账号的 Thread、附件标题、Draft 和 Activity 不可见。

### 16.4 无障碍与安全

- 键盘可达所有导航、Thread 操作、头部操作、消息操作和 Composer 控件。
- 图标按钮有可见 Tooltip 与稳定 accessible name。
- 关闭 drawer/sheet/popover 后焦点返回触发器。
- 生成、连接、停止、上传、保存和错误使用合理 live region，不逐 token 播报。
- Snow 主题满足 WCAG 2.2 AA，200% 文本缩放不丢操作。
- Markdown 不允许未审核 raw HTML/script/iframe。
- 导出不含 system prompt、hidden reasoning、工具秘密、签名 URL 和医疗拼接原文。

### 16.5 性能

- 100 Thread 侧边列表滚动无明显掉帧；超过此规模再引入虚拟列表，不提前增加依赖。
- 200 回合长对话初次可用时间不因 Markdown 重复解析明显恶化；优先 memo/Block revision，再评估消息虚拟化。
- Streaming delta 合并在 reducer/writer 节流，不对每个 token 创建新 Markdown 树和动画。
- 侧边栏、Panel 和 Composer 动画只修改 transform/opacity/max-width 等可控属性，避免持续 layout thrash。

## 17. 上线与回滚

### 17.1 Feature Flag

```text
NEXT_PUBLIC_CHAT_UI_V2_ENABLED=false
```

- 开发/预发通过 flag 进入新 Shell，生产先对内部账号开启。
- 新旧 UI 共用同一 Auth/Thread/Run/Event/Context 层，回滚 UI 不回滚数据库和 Run。
- 路由切换期 `/chat` 和 `/home` 只有一个 canonical 实现，不复制两份 Workspace。
- 新 UI 默认开启一个稳定版本后，删除 flag、旧 CSS、旧 Shell 与重定向特例。

### 17.2 故障回滚不得做的事

- 不删除/重建 Thread、Message、Block、Run 数据。
- 不更换 Provider Key、模型路由或 Celery/Redis 配置。
- 不退回 DeepTutor API/WS/Session Context。
- 不因 UI 故障关闭后端鉴权、Context 冻结和 Event replay。

## 18. Definition of Done

- [ ] 桌面端框架是单一 `220/60px` 左侧栏 + Chat Workspace，无旧右侧全局 Rail 和常驻 action rail。
- [ ] 左侧主导航按顺序显示主页、医疗、饮食、运动；底部显示知识库、记忆、设置。
- [ ] 最近会话列表几何与快照一致，可折叠、独立滚动、选中、重命名、软删除。
- [ ] ChatHeader 与消息/Composer 使用同一 960px 中轴，标题可受控重命名。
- [ ] 消息区是唯一主滚动面，长对话、自动跟随、上滚暂停、跳转最新和刷新恢复正确。
- [ ] 用户气泡、助手 Markdown、Activity 折叠、消息操作和 Usage 与快照的信息层级一致。
- [ ] Composer 使用 26px Card、底部工具栏、上下文区、附件区和圆形发送/停止按钮。
- [ ] Auth、Thread、Message、Block、Run、Event、Preferences 和 Context 仍使用 SparkService 单一事实源。
- [ ] 断线 replay、幂等发送、取消、重生、切换 Thread 和账号清理没有因 UI 重构回归。
- [ ] 不显示 hidden chain-of-thought、system prompt、未脱敏 tool result、Provider Key 或敏感 Context 原文。
- [ ] 未有 Spark 契约的笔记本、KB、语音、编辑分支和删除回合保持 disabled/hidden，不伪实现。
- [ ] 迁移文件的源版本、hash、Apache-2.0 归属、修改说明和测试证据完整。
- [ ] TypeScript、ESLint、Vitest、Contract test、Playwright、production build、无障碍和视觉回归全部通过。
- [ ] 375/390/768/1024/1440/1920 宽度截图归档，关键几何误差满足本工单阈值。

## 19. 与现有文档的优先级

本工单只覆盖以下旧决策：

- `AI 对话 Web App 实现工单.md` 中的「300px 左侧二级栏 + 64px 操作栏 + 88px 最右全局导航」。
- `AI 对话 Web App Plain Text UI 设计.md` 中与本工单单一左侧栏相冲突的框架草图。
- `chat-web/app/globals.css` 中当前 P0/P3 临时 Shell 尺寸与对话视觉。

本工单不覆盖：

- `AI 对话 Web App P0-P7 分阶段实施计划.md` 中的 Auth、Run、Event、Context、Tool、Interaction、Capability 与生产加固语义。
- `服务端 AI 对话需求.md` 的服务端事实源和跨端契约。
- `AI 对话 Web App 统一错误提示工单.md` 的错误归一化与呈现策略。

如其他文档与本工单的 UI 框架决策冲突，以 `CHAT-WEB-017` 为准；如数据契约冲突，以 SparkService 服务端 serializer/Event/Block schema 为准。
