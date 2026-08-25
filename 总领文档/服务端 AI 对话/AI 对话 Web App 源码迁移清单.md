# AI 对话 Web App 源码迁移清单

## 1. 文档目标

本文档回答两个问题：

1. `/Users/hua/Documents/project/DeepTutor/DeepTutorSerevr/web` 中哪些前端文件可以直接复制到 SparkService `chat-web/`。
2. `chat-web/` 如何在不引入 DeepTutor 教学业务的前提下，尽量对齐参考工程的目录结构。

本清单基于真实文件、依赖和 import 关系审计。`chat-web/` 当前尚未创建，所有目标路径均为 `建议演进`，不是已有代码。

## 2. 许可证与复制边界

参考工程根目录 `LICENSE` 是 Apache License 2.0，版权声明为 `Copyright 2025 Data Intelligence Lab, The University of Hong Kong`。

复制源码时必须：

- 在 `chat-web/` 分发物中保留 Apache-2.0 许可证副本和适用的版权/归属信息。
- 被修改的复制文件应有明显的修改说明，例如文件头注释或项目 `NOTICE`/第三方声明。
- 保留原源码中与所复用部分相关的版权、专利、商标和归属声明。
- 不复制 DeepTutor/OpenTutor 名称、Logo、banner、favicon 或其他品牌素材；Apache-2.0 不授予商标使用权。
- 不直接复制用户提供的第三方页面 base64、SVG、Provider 图标或品牌文案，除非已单独确认许可边界。

迁移第一个源码文件时，同步新增：

```text
chat-web/
├── LICENSE                       # Apache-2.0 副本
└── THIRD_PARTY_NOTICES.md       # DeepTutor 来源、版本/提交、复用文件清单和修改说明
```

## 3. SparkService 架构适配原则

### 3.1 目标架构事实

SparkService 是 Django/DRF/Channels 模块化单体服务，仓库根目录已有两个独立 Vue/Vite 应用 `open-web/` 和 `backoffice-web/`。新 `chat-web/` 是第三个根级独立前端，可使用 Next/React，但不得把 DeepTutor 的 Node 服务端、API 路由或数据库逻辑带入 SparkService。

```text
SparkService/
├── SparkService/       # Django settings / urls / ASGI 组合根
├── accounts/           # 手机 OTP、Apple ID、JWT、账号与设备
├── chat_sync/          # Thread / Message / Block / WebSocket JWT
├── ai_config/          # 模型和场景配置
├── file_manager/       # 文件、OSS、业务关联
├── medical/           # 成员、医疗档案、权限、健康资源
├── nutrition/         # 饮食、营养目标和记录
├── open-web/          # Vue/Vite 公开站
├── backoffice-web/    # Vue/Vite 管理站
└── chat-web/          # Next/React 登录态 AI 工作台（建议）
```

### 3.2 前端到 SparkService 模块的强制映射

| 前端能力 | 必须接入的 Spark 模块/路由 | 不得沿用的 DeepTutor 边界 |
| --- | --- | --- |
| 手机/Apple 登录 | `accounts/*`、`/api/v1/auth/*`、`/api/v1/otp/*` | DeepTutor `lib/auth.ts`、账号数据、Cookie 命名 |
| 会话列表与历史 | `chat_sync/*`、`/api/v1/ai/chat/sync/*` | DeepTutor session API、PocketBase/Session ID 假设 |
| AI Run 和流式 | Spark `chat_sync` 待实现 Run/Event + Channels | `unified-ws` 事件字段和 Turn 状态不可照搬 |
| 模型选择 | `ai_config/*`、`/api/v1/ai/*` | 前端 Provider Key、Base URL、DeepTutor LLM Option |
| 附件 | `file_manager/*`、`/api/v1/files/*`、`/api/v1/oss/*` | DeepTutor upload proxy、附件 ID/状态 |
| 健康成员/资源 | `medical/*`、`/api/v1/medical/*` | Persona/Notebook/Book 语义 |
| 饮食工作区 | `nutrition/*`、`/api/v1/nutrition/*` | DeepTutor 学习/掌握度数据 |
| WebSocket 认证 | `chat_sync.auth.JWTAuthMiddlewareStack` | DeepTutor WS URL、Token 传递与重连业务判定 |

### 3.3 依赖方向

```text
chat-web Page / Component
  -> Spark Frontend Application State
  -> Spark REST Gateway / WebSocket Gateway
  -> Django urls.py / ASGI
  -> accounts | chat_sync | ai_config | file_manager | medical | nutrition
  -> Spark Database / Redis / Celery / OSS / Provider
```

- UI 组件不得直接依赖 DeepTutor API、Context 或 WebSocket 类型。
- Next Route Handler 只能用于同源/BFF 安全适配，不另建 Thread、Message、Run 数据库或第二套业务服务。
- Spark serializer/OpenAPI 是 TypeScript DTO 的来源；DeepTutor interface 只能用于理解 UI 需要哪些字段。
- `chat-web/` 使用独立 `package.json`、lockfile、构建与测试，不改变 `open-web/` 和 `backoffice-web/` 的 Vue/Vite 职责。
- 开发环境默认可使用 `chat-web:2029 -> Django:2026`。`/api` 与 WebSocket 代理、CORS、CSRF、Cookie 域和 HTTPS 必须在部署设计中统一，不照搬 DeepTutor proxy。

## 4. 五级迁移分类

| 分类 | 源码保留范围 | 目标文件身份 | 操作要求 | 合并证据 |
| --- | --- | --- | --- | --- |
| 直接复用 | 通常 95%–100% | 文件名、职责、核心实现保持不变 | 复制后只允许格式、类型兼容和品牌无关的小修 | 原测试通过、依赖审计、来源登记 |
| 原文件迁移 | 通常 60%–95% | 仍能明确追溯为同一个文件 | 以完整源文件为起点，替换 import、Token、文案或配置 | 修改说明、diff 审查、功能测试 |
| 部分迁移 | 通常低于 60% | 创建 Spark 文件，源文件仅提供指定片段 | 只复制清单点名的函数、JSX 或 CSS 区段，不提交完整源文件 | 片段来源、起止符号、目标组件测试 |
| 仅参考重写 | 0% 源代码 | Spark 新文件 | 只参考职责、交互和状态机，从空白文件按 Spark 合同实现 | Spark 契约测试、确认无 DeepTutor import |
| 不可迁移 | 0% | 不创建对应运行时文件 | 不复制、不打包、不以隐藏依赖方式引入 | 依赖扫描、资产与许可证审查 |

百分比只用于辅助评审，不是机械判定条件。只要文件涉及账号、聊天实体、Run/Event、附件标识、服务端代理或数据库语义，即使表面代码相似，也至少降为“仅参考重写”。

### 4.1 判定顺序

```text
是否属于 Spark 首期范围？
├── 否 -> 不可迁移
└── 是
    ├── 是否包含品牌资产、秘密、构建产物或许可不明内容？
    │   └── 是 -> 不可迁移
    ├── 是否依赖 DeepTutor API、认证、实体、事件或服务端状态？
    │   └── 是 -> 仅参考重写
    ├── 是否只有少数视觉/算法片段可用？
    │   └── 是 -> 部分迁移
    ├── 是否保留文件主体，仅需替换工程适配内容？
    │   └── 是 -> 原文件迁移
    └── 是否为无业务依赖的稳定通用实现？
        └── 是 -> 直接复用
```

### 4.2 迁移登记要求

每个迁移 PR 应在 `THIRD_PARTY_NOTICES.md` 或配套清单登记：源仓库、锁定提交、源路径、目标路径、五级分类、复制日期、修改摘要和验证项。不能只写“参考 DeepTutor”。“部分迁移”还必须记录所取函数、组件或 CSS 选择器；“仅参考重写”只登记设计来源，不声明复制了源码。

建议登记格式：

```text
Source commit: <git sha>
Source path: web/components/chat/home/ComposerInput.tsx
Target path: chat-web/components/chat/home/ComposerInput.tsx
Classification: 部分迁移
Copied symbols/selectors: textarea shell, attachment preview layout
Excluded: Agent shortcut, DeepTutor context/API, teaching prompts
Modified by SparkService: 2026-xx-xx
Verification: typecheck / component test / visual regression
```

## 5. 直接复用

### 5.1 纯函数与 Hook

| DeepTutor 源文件 | Spark 目标文件 | 复制后必做检查 |
| --- | --- | --- |
| `lib/composer-keyboard.ts` | `lib/composer-keyboard.ts` | 保留 IME `229` 防误发逻辑 |
| `lib/use-auto-sized-textarea.ts` | `lib/use-auto-sized-textarea.ts` | Composer 传入 `min:28, max:200` |
| `lib/use-ime-composing.ts` | `lib/use-ime-composing.ts` | 保留 `compositionend` 延迟清理 |
| `lib/debounce.ts` | `lib/debounce.ts` | 可将 `NodeJS.Timeout` 改为 `ReturnType<typeof setTimeout>` |
| `lib/single-flight.ts` | `lib/single-flight.ts` | 用于 Token refresh 和其他单飞请求 |
| `lib/reconnecting-websocket.ts` | `lib/reconnecting-websocket.ts` | 仅处理连接；Spark 事件协议放在 `chat-ws.ts` |
| `lib/relative-time.ts` | `lib/relative-time.ts` | 确认 Spark 时间戳是秒还是毫秒 |
| `hooks/useLockBodyScroll.ts` | `hooks/useLockBodyScroll.ts` | 保留 scrollbar padding 补偿 |
| `hooks/useMeasuredHeight.ts` | `hooks/useMeasuredHeight.ts` | 对不支持 `ResizeObserver` 的环境保持安全 |
| `hooks/useSmoothStreamText.ts` | `hooks/useSmoothStreamText.ts` | 输入只接收 Spark block 的已合并文本 |
| `hooks/useChatAutoScroll.ts` | `hooks/useChatAutoScroll.ts` | 保留对应 `data-*` 锚点或同步改选择器 |

`useChatAutoScroll.ts` 只 import React，但内部依赖页面 `data-chat-*` DOM 契约。只有在目标消息列保持该 DOM 契约时才可直接复用；否则改为“原文件迁移”并同步修改选择器和测试。

### 5.2 基础 UI

| DeepTutor 源文件 | Spark 目标文件 | 说明 |
| --- | --- | --- |
| `components/ui/Button.tsx` | `components/ui/Button.tsx` | 依赖 React、Lucide 和通用 CSS Variable，可复制 |
| `components/ui/Tooltip.tsx` | `components/ui/Tooltip.tsx` | 可复制，但需同步迁移/改名 `dt-tooltip-*` CSS |

`components/ui/ConfirmDialog.tsx` 带 `react-i18next` 文案依赖，列为“原文件迁移”，不应在未接入 i18n 时原样复制。

### 5.3 可连同源码复制的测试

| 源测试 | 前置条件 |
| --- | --- |
| `tests/composer-keyboard.test.ts` | 复制 `lib/composer-keyboard.ts` |
| `tests/reconnecting-websocket.test.ts` | 复制 `lib/reconnecting-websocket.ts` |
| `tests/single-flight.test.ts` | 复制 `lib/single-flight.ts` |

测试运行器应由 Spark 的 `package.json` 统一定义，不需为了运行三个测试就复制全部 DeepTutor `scripts/`。

## 6. 原文件迁移

| DeepTutor 源文件 | Spark 目标 | 必须修改 |
| --- | --- | --- |
| `tailwind.config.js` | `tailwind.config.ts` 或 `.js` | 保留 CSS Variable 颜色/字体；移除无用 pages 扫描 |
| `tsconfig.json` | `tsconfig.json` | 保留 strict/alias；删除 `.next-deeptutor` include |
| `postcss.config.js` | `postcss.config.js` | 核对 Tailwind 版本 |
| `eslint.config.mjs` | `eslint.config.mjs` | 移除 DeepTutor 自定义 i18n 规则或同步迁移 |
| `next.config.js` | `next.config.ts`/`.js` | 重写 API 代理、图片域名、构建目录 |
| `app/layout.tsx` | `app/layout.tsx` | 保留 Geist/Lora 与 Provider 顺序，替换 metadata、Toast、Theme、i18n |
| `components/ui/ConfirmDialog.tsx` | 同路径 | 改为 Spark i18n 键与危险操作文案 |
| `hooks/useDevice.ts` | 同路径 | 对齐 Spark 的 768/1200 断点 |
| `i18n/I18nClientBridge.tsx`、`I18nProvider.tsx`、`index.ts`、`init.ts` | `i18n/` 同名文件 | 保留初始化与语言切换结构；默认语言改为产品约定，核对 SSR/hydration |

`package.json` 不应原样复制。可以以它为版本参考，但 Spark 首期只引入 Next、React、Tailwind、Lucide、Framer Motion、Markdown/Katex 和测试必需依赖；不引入 chart.js、cytoscape、docx-preview、exceljs、mermaid、jspdf 等未使用能力。

## 7. 部分迁移

### 7.1 App Shell 和侧栏

| 源文件 | 可保留 | 必须重写 |
| --- | --- | --- |
| `components/layout/AppShell.tsx` | drawer、遮罩、`inert`、Escape、`h-dvh` | 最右全局导航、Spark 路由、i18n |
| `components/layout/ResponsiveAppShell.tsx` | 桌面/移动分流结构 | Spark 底部 Tab 与页面骨架 |
| `components/sidebar/SidebarShell.tsx` | 展开/收起、会话区域布局 | Capability、Book、CoWriter、VersionBadge、品牌 |
| `components/sidebar/WorkspaceSidebar.tsx` | Thread 列表的组装方式 | `UnifiedChatContext`、Admin/Profile 和 DeepTutor 导航 |

最右侧 `GlobalNavigationRail.tsx` 是 Spark 新增组件，DeepTutor 无可原样复制文件。

### 7.2 聊天页、消息和 Composer

| 源文件 | 行数/特点 | 迁移方式 |
| --- | --- | --- |
| `components/chat/home/ChatMessages.tsx` | 1519 行，带 Notebook/Question/Book/Agent | 复制 JSX/CSS 起点，重写为 Spark Block Renderer |
| `components/chat/home/TracePanels.tsx` | 2700 行，工具类型高度耦合 | 只提取 Activity header、纵向轴和通用 tool row |
| `components/chat/home/ChatComposer.tsx` | 1163 行，带 Agent/Knowledge/Book/Persona | 只保留表面、附件区和工具栏布局 |
| `components/chat/home/ComposerInput.tsx` | 532 行，带 Agent 快捷输入 | 提取 textarea，并接入“直接复用”的 IME/自动高度 Hook |
| `components/chat/home/ContextBudgetChip.tsx` | 335 行 | 保留圆形用量 UI，替换 Spark context usage 数据 |
| `components/chat/home/ModelSelector.tsx` | Provider 选择 | 只显示服务端返回的模型别名，不复制 Provider Key UI |
| `components/chat/home/KnowledgeSelector.tsx` | DeepTutor Knowledge API | 改接 Spark 知识库契约 |
| `components/chat/home/PersonaSelector.tsx` | Persona API | 映射为健康成员/对话角色 |
| `components/chat/home/StarterSuggestions.tsx` | 空对话推荐 | 保留组件结构，重写为健康问题 |

### 7.3 全局样式片段

`app/globals.css` 不能作为完整文件迁移。源文件约 845 行，混合了主题变量、通用排版、聊天交互、DeepTutor 品牌和页面特例。目标文件应从空白开始，只按下表摘取：

| 可取片段 | 迁移要求 | 不得带入 |
| --- | --- | --- |
| 色彩、圆角、前景/背景 CSS Variable | 改名并映射到 Spark Snow Token | DeepTutor 品牌变量和 Logo 相关样式 |
| Markdown 正文、代码块、表格基础排版 | 限定到消息正文作用域 | Book、Quiz、Notebook 专用选择器 |
| Tooltip 基础样式 | 与迁移后的 `Tooltip.tsx` 一起验证 | `dt-*` 命名原样长期保留 |
| Composer textarea、滚动条和 focus 样式 | 对齐用户给出的输入区尺寸 | 页面级固定宽高和参考站特例 |
| reduced-motion、focus-visible 规则 | 保留无障碍语义 | 覆盖浏览器默认焦点但无替代样式的规则 |

### 7.4 文案资源片段

| 源文件 | 迁移方式 |
| --- | --- |
| `locales/zh/common.json`、`locales/en/common.json` | 逐键筛选按钮、确认、取消、加载等通用文案；键名符合 Spark 语义后才能保留 |
| `locales/zh/app.json`、`locales/en/app.json` | 文件包含数千行教学业务文案，禁止整文件复制；只摘取已被迁移通用组件实际引用的键，其余 Spark 文案重新编写 |

## 8. 仅参考重写

以下文件只允许参考职责分解、状态机和恢复思路，不复制实现到 Spark 主干：

| 源文件 | 结论 |
| --- | --- |
| `app/(workspace)/home/[[...sessionId]]/page.tsx` | 2372 行且承担教学工作台编排；只参考加载、空态、发送、恢复和选中会话流程，Spark 主页面从空白重写 |
| `app/(workspace)/layout.tsx` | Provider、Capability 和导航边界与 Spark 不同；按 Spark 登录守卫和工作台布局重写 |
| `context/UnifiedChatContext.tsx` | 不直接复制；只参考 reducer/provider 边界，目标为 `ChatRuntimeContext.tsx` |
| `lib/unified-ws.ts` | 不直接复制；事件类型必须以 Spark Run/Event 合同为准 |
| `lib/api.ts` | 不直接复制；改接 Spark JWT、错误码、Request ID 和 refresh |
| `lib/auth.ts` | 不直接复制；重写为手机 OTP + Apple ID + Spark Token |
| `lib/session-api.ts` | 不直接复制；改为 Spark Thread/Message Pull/Push |
| `lib/turn-reconcile.ts` | 算法可参考，但当前假定 number/负数 ID 和 DeepTutor event 字段；需按 Spark UUID/client_message_id 重写 |
| `lib/optimistic-id.ts` | 不原样复制；当前使用负整数，Spark 应使用 UUID/ULID 或明确 client id |
| `package.json` | 只参考版本兼容范围和 scripts 目标；依赖集合必须由 Spark 功能反推并重新生成 |

## 9. 不可迁移

- `app/(workspace)/book/*`、`co-writer/*`、`partners/*`、`playground/*`。
- `components/agents/*`、`book/*`、`quiz/*`、`research/*`、`notebook/*`、`partners/*`、`mcp/*`、`visualize/*`。
- `lib/book-*`、`quiz-*`、`partners-*`、`co-writer-*`、`subagents-*`、`codex-*`、`mcp-*`、`learning-*`、`research-types.ts`。
- `public/logo*.png`、`banner.png`、`favicon-*.png`、`apple-touch-icon.png`。
- `public/provider-icons/*`，除非每个图标的来源和许可证已单独确认。
- `.next*`、`dist/`、`playwright-report/`、`test-results/`、任何构建产物和临时结果。
- DeepTutor 的 `app/api/v1/*` 代理路由；Spark 应根据自己的 BFF/同源部署方案重建。
- `package-lock.json`；目标依赖集合不同，应由 `chat-web/package.json` 重新生成。
- `.env*`、本地 Provider 配置、Token、Cookie、证书和任何密钥；目标环境变量必须从 SparkService 的部署配置重新建立。
- `tsconfig.tsbuildinfo`、缓存目录和编辑器生成文件。

## 10. 建议目标目录：符合 SparkService 且尽量与 DeepTutor 对齐

```text
chat-web/
├── app/
│   ├── (auth)/
│   │   ├── layout.tsx
│   │   └── login/page.tsx
│   ├── (workspace)/
│   │   ├── layout.tsx
│   │   └── chat/[[...threadId]]/page.tsx     # Spark 保留 /chat 业务路由
│   ├── layout.tsx
│   └── globals.css
├── components/
│   ├── auth/
│   │   ├── PhoneOtpForm.tsx
│   │   ├── AppleSignInButton.tsx
│   │   └── LogoutButton.tsx
│   ├── chat/
│   │   └── home/                              # 对齐参考工程
│   │       ├── ChatComposer.tsx
│   │       ├── ComposerInput.tsx
│   │       ├── ComposerToolbar.tsx
│   │       ├── ChatMessages.tsx
│   │       ├── ChatBlockRenderer.tsx
│   │       ├── TracePanels.tsx
│   │       ├── ContextBudgetChip.tsx
│   │       ├── KnowledgeSelector.tsx
│   │       ├── MemberSelector.tsx
│   │       ├── ModelSelector.tsx
│   │       ├── StarterSuggestions.tsx
│   │       └── ClientToolCard.tsx
│   ├── common/
│   │   ├── AssistantResponse.tsx
│   │   ├── MarkdownRenderer.tsx
│   │   └── ToastViewport.tsx
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   ├── ResponsiveAppShell.tsx
│   │   └── GlobalNavigationRail.tsx          # Spark 新增
│   ├── sidebar/
│   │   ├── SidebarShell.tsx
│   │   └── WorkspaceSidebar.tsx
│   └── ui/
│       ├── Button.tsx
│       ├── ConfirmDialog.tsx
│       └── Tooltip.tsx
├── context/
│   ├── AppShellContext.tsx
│   └── ChatRuntimeContext.tsx                    # 替代 UnifiedChatContext
├── hooks/
│   ├── useChatAutoScroll.ts
│   ├── useDevice.ts
│   ├── useLockBodyScroll.ts
│   ├── useMeasuredHeight.ts
│   └── useSmoothStreamText.ts
├── i18n/
├── locales/
│   ├── zh/
│   └── en/
├── lib/
│   ├── api.ts
│   ├── auth.ts
│   ├── chat-ws.ts                               # Spark Run/Event 协议
│   ├── event-reducer.ts
│   ├── reconnecting-websocket.ts
│   ├── composer-keyboard.ts
│   ├── use-auto-sized-textarea.ts
│   ├── use-ime-composing.ts
│   ├── debounce.ts
│   ├── single-flight.ts
│   ├── relative-time.ts
│   └── turn-reconcile.ts
├── tests/
│   ├── composer-keyboard.test.ts
│   ├── reconnecting-websocket.test.ts
│   ├── single-flight.test.ts
│   ├── event-reducer.test.ts
│   └── turn-reconcile.test.ts
├── public/
│   └── spark/                                   # 只放 Spark 品牌资产
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── package.json
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── playwright.config.ts
```

### 10.1 有意不对齐的地方

- DeepTutor 路由 `home/[[...sessionId]]` 保持为 Spark `chat/[[...threadId]]`，避免牺牲 Spark 业务语义；如需兼容 `/home`，只做重定向。
- `context/UnifiedChatContext.tsx` 改为 `ChatRuntimeContext.tsx`，防止误以为两端使用相同事件协议。
- `lib/unified-ws.ts` 拆为协议无关的 `reconnecting-websocket.ts` 与 Spark 特有 `chat-ws.ts`。
- `PersonaSelector.tsx` 改为 `MemberSelector.tsx`，对应 Spark 健康成员；若未来同时支持 AI Persona，再拆成两个组件。
- 不创建 DeepTutor 的 Book、Quiz、Notebook、Partner、Agent、MCP 目录空壳。

## 11. 迁移顺序

```text
1. 创建最小 Next/React/Tailwind 工程
   -> 完成 LICENSE + THIRD_PARTY_NOTICES

2. 复制“直接复用”纯函数/Hook/基础 UI
   -> 同步复制对应单元测试
   -> 先保证 lint/typecheck/test 通过

3. 迁移 Tailwind Token 与必需 globals.css 片段
   -> 替换 Spark 品牌与字体

4. 迁移 AppShell/Sidebar 的结构
   -> 新建最右 GlobalNavigationRail

5. 提取 ComposerInput/Toolbar 和消息卡 UI
   -> 先用静态 ViewModel 验收视觉

6. 实现 Spark API/Auth/ChatRuntime/Event reducer
   -> 禁止让迁移 UI 直接依赖 DeepTutor API

7. 接入历史、流式、工具、附件和客户端桥接
   -> 完成协议、恢复和 E2E 验收
```

### 11.1 P0–P7 分阶段迁移入口

各阶段允许迁移、必须重写、禁止迁移的内容及交付证据统一维护在 [AI 对话 Web App P0–P7 分阶段实施计划](./AI%20对话%20Web%20App%20P0-P7%20分阶段实施计划.md)。本清单继续作为五级分类和文件级迁移判定依据，但不再维护第二套阶段矩阵。

## 12. 迁移后必查项

- [ ] 每个复制文件都在 `THIRD_PARTY_NOTICES.md` 有来源记录。
- [ ] 修改文件已有显著修改说明，Apache-2.0 和原归属已保留。
- [ ] `rg -i 'deeptutor|opentutor|book|quiz|notebook|partner|subagent|mcp' chat-web` 的命中均经人工解释或清理。
- [ ] `public/` 不包含 DeepTutor Logo、favicon、banner 和未核对许可的 Provider 图标。
- [ ] UI 不直接 import DeepTutor `api.ts/auth.ts/unified-ws.ts/UnifiedChatContext.tsx`。
- [ ] `chat-web/` 不直接调用模型供应商，也不保存豆包/OpenAI Key 或 Base URL。
- [ ] Next Route Handler 未创建第二套 Thread/Message/Run 数据模型；所有业务写入仍进入 Django。
- [ ] Spark Thread/Message/Block/Run/Event 类型是唯一聊天数据事实源。
- [ ] 手机 OTP、Apple ID、refresh、logout 均使用 SparkService 账号体系。
- [ ] 复制的 Hook/纯函数测试通过，修改后的 DOM 选择器有对应组件测试。
- [ ] 复制前后使用同视口屏截图进行视觉回归，同时验证 390/768/1024/1440px。

### 12.1 分类验收口径

| 分类 | Code Review 必问问题 |
| --- | --- |
| 直接复用 | 是否仍是纯通用实现？原测试是否不改断言即可通过？ |
| 原文件迁移 | 文件主体是否仍可辨识？所有 DeepTutor import、文案、Token 是否已替换？ |
| 部分迁移 | PR 是否只包含获准片段？是否记录片段来源并清除了周边业务分支？ |
| 仅参考重写 | 是否从 Spark DTO/事件合同出发？是否做到零 DeepTutor 源码 import？ |
| 不可迁移 | 是否被依赖、静态资源和构建产物扫描拦截？ |
