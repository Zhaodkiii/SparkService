# AI 对话 Web App 实现工单

## 一、模块目标

在 `SparkService` 仓库中新增独立前端应用 `chat-web/`，面向已登录用户提供网页 AI 对话。该 App 连接 SparkService 的账号、聊天同步与服务端 AI Run API，与 iOS 共用 `ChatThread / ChatMessage / ChatMessageBlock`，不建立第二套会话数据。

界面与交互以 `/Users/hua/Documents/project/DeepTutor/DeepTutorSerevr/web` 的 Chat Workspace 为主要参考，要求整体布局、信息密度、尺寸、动效和状态反馈基本一致；品牌、文案、业务能力和数据协议改为 SparkService。不得复制 DeepTutor 的教学产品导航、Logo、名称或无关业务。

页面级 Plain Text 布局、最右全局导航与各健康工作区见：`AI 对话 Web App Plain Text UI 设计.md`。

参考工程的可复制文件、Apache-2.0 要求、“直接复用/原文件迁移/部分迁移/仅参考重写/不可迁移”五级分类和对齐后目录见：`AI 对话 Web App 源码迁移清单.md`。

### 1.1 技术选型结论

- `建议演进`：独立 App 使用 Next.js 16、React 19、TypeScript、Tailwind CSS 3、Lucide React、Framer Motion。
- 选择理由：参考前端使用相同组合，保留结构、样式和交互最直接；独立目录可以避免向现有 Vue 应用引入 React。
- `open-web` 保持公开文章/分享站职责；`backoffice-web` 保持管理端职责；不得把登录态聊天塞入二者。
- 首期采用客户端渲染的认证工作区，不依赖搜索引擎收录；Next.js 主要承担工程结构、路由与后续部署能力。

### 1.2 第一期范围

必须实现：手机号验证码登录、使用 Apple ID 登录、会话侧栏、新建/选择/重命名/删除、消息历史、流式助手回复、Markdown、工具/推理状态、附件、模型选择、发送/停止、失败重试、断线重连、移动端抽屉、主题与基础无障碍。

同时实现最右侧全局导航，包含对话、知识库、医疗、饮食、运动、记忆、设置入口。对话是第一期完整业务闭环；其他六个入口第一期至少完成路由、二级导航、页面骨架和加载/空/错误/权限状态。

暂不实现：DeepTutor 的 Partners、Notebook、Books、Quiz、Research、Co-Writer、Knowledge、Memory、Subagents、语音、生成文件预览器全集。健康资源引用和客户端工具等待卡片按 SparkService 协议实现，不照搬教学卡片。

## 二、AI 对话 Web App 模块结构

### 2.1 结构职责表

| 层级 | 职责 | 关键实现 |
| --- | --- | --- |
| App Router | 登录、聊天工作区、路由守卫、布局 | `chat-web/app/*`（建议） |
| Feature UI | 会话侧栏、消息流、Composer、工具状态、附件 | `chat-web/components/chat/*`（建议） |
| Application State | Thread/Run/Message/Event reducer、选择态与恢复 | `chat-web/context/ChatRuntimeContext.tsx`（建议） |
| API/WS Gateway | JWT、刷新、REST、WebSocket、重放与重连 | `chat-web/lib/api/*`、`lib/chat-ws.ts`（建议） |
| Domain Contract | Thread/Message/Block/Run/Event/ToolCall 类型 | `chat-web/types/chat.ts`（建议） |
| Design System | Token、字体、响应式、动效、Markdown | `chat-web/app/globals.css`、`tailwind.config.ts`（建议） |
| Test | reducer、协议、组件、视觉与 E2E | `chat-web/tests/*`、`e2e/*`（建议） |

### 2.2 当前真实目录

```text
SparkService/
├── open-web/                       # Vue 3/Vite，公开内容与分享
├── backoffice-web/                 # Vue 3/Vite，后台管理
├── chat_sync/                      # Thread/Message/Block 同步，尚无 AI Run
├── accounts/auth/                  # JWT 登录与刷新
├── ai_config/                      # 模型与场景配置
└── 总领文档/服务端 AI 对话/
```

`当前缺口`：仓库中不存在 `chat-web/`，不存在登录态 Chat 页面、Run WebSocket Client、Chat reducer 和前端测试。

### 2.3 建议目标目录

目标工程的一级目录、`components/chat/home`、`components/layout`、`components/sidebar`、`components/ui`、`hooks`、`lib`、`i18n`、`locales`和 `tests` 尽量与 `/Users/hua/Documents/project/DeepTutor/DeepTutorSerevr/web` 对齐。业务语义优先于完全同名：路由保持 `/chat`，`UnifiedChatContext` 改为 `ChatRuntimeContext`，`unified-ws` 改为 Spark `chat-ws`。完整目录树以源码迁移清单为准。

```text
chat-web/
├── app/
│   ├── (auth)/
│   │   ├── layout.tsx
│   │   └── login/page.tsx
│   ├── (workspace)/
│   │   ├── layout.tsx
│   │   └── chat/[[...threadId]]/page.tsx
│   ├── globals.css
│   └── layout.tsx
├── components/
│   ├── auth/
│   ├── chat/home/
│   │   ├── ChatComposer.tsx
│   │   ├── ComposerInput.tsx
│   │   ├── ChatMessages.tsx
│   │   ├── ChatBlockRenderer.tsx
│   │   ├── TracePanels.tsx
│   │   └── ClientToolCard.tsx
│   ├── common/
│   ├── layout/
│   │   ├── AppShell.tsx
│   │   ├── ResponsiveAppShell.tsx
│   │   └── GlobalNavigationRail.tsx
│   ├── sidebar/
│   │   ├── SidebarShell.tsx
│   │   └── WorkspaceSidebar.tsx
│   └── ui/
├── context/ChatRuntimeContext.tsx
├── hooks/
├── i18n/
├── locales/
├── lib/
│   ├── api.ts
│   ├── auth.ts
│   ├── chat-ws.ts
│   ├── event-reducer.ts
│   ├── reconnecting-websocket.ts
│   ├── composer-keyboard.ts
│   └── single-flight.ts
├── types/chat.ts
├── tests/e2e/
├── public/spark/
├── package.json
├── LICENSE
├── THIRD_PARTY_NOTICES.md
├── next.config.ts
├── tailwind.config.ts
└── tsconfig.json
```

以上均为 `建议演进`，不得在实现完成前标为当前代码。

### 2.4 依赖方向

```text
Page/Layout
  -> ChatRuntimeContext / Feature Components
  -> REST Gateway + WebSocket Gateway
  -> SparkService Auth / Chat Sync / AI Run API

Stream Event
  -> Event Reducer
  -> Run/Message/Block State
  -> Pure Render Components
```

组件不得自行拼 API URL、刷新 Token 或直接修改跨会话状态。`ChatBlockRenderer` 只渲染 block；事件去重、sequence 和 revision 冲突全部由 reducer 处理。

## 三、独立 App 工程与认证

### 需求说明

提供独立构建、开发端口、环境变量和部署产物，并复用 SparkService 账号体系。登录页必须支持“手机号 + 短信验证码”和“使用 Apple ID 登录”，两种方式最终都换取 SparkService 的统一 access/refresh Token，不在 Web 端创建第二套用户与会话体系。

未登录访问聊天路由时进入登录页，Token 失效时只允许一次刷新并重放安全请求。iOS 和 Web 使用同一 `User/SocialIdentity`，同一账号登录后应看到相同 Thread、Message 和 Run。

### 基础要求与业务规则

- App 名称建议为 `chat-web`，开发端口不得与 `open-web:2028` 和现有管理端冲突，建议 `2029`。
- 环境变量至少有 `NEXT_PUBLIC_API_BASE_URL`、`NEXT_PUBLIC_WS_BASE_URL`。
- 登录 UI 以用户提供的参考弹窗为几何基线：桌面容器 `689×360px`，内容列 `370px`，登录按钮高 `56px`、圆角 `16px`；移动端宽 `366px`、内容列 `316px`。
- 参考中的豆包、飞书、抖音入口必须替换为“使用手机号登录”和“使用 Apple 登录”，不复制其品牌、协议文案、SVG 或 base64 素材。
- 两种登录都必须先勾选小鲸《用户协议》与《隐私政策》；未勾选时焦点转到协议区并显示可读错误。
- 手机号登录分两步：`POST /api/v1/otp/phone/request/` 获取 `otp_id`，`POST /api/v1/otp/phone/verify/` 提交 `otp_id + phone_number + code` 并换取 Token。
- 手机号统一标准化为 E.164；发送按钮要有倒计时、重复提交禁用、验证码过期/错误/锁定/限流状态。
- 验证码视觉上使用 6 个单字符格，实际使用一个可粘贴、可短信自动填充的输入；输入完成后只自动提交一次。页面显示脱敏号码与重发倒计时。
- `当前实现`：手机号 OTP 服务对非中国区号码有显式拒绝测试；首期 Web UI 应明确使用 `+86`，如需国际号码须先扩展后端短信 Provider 和风控策略。
- Apple 登录使用 `POST /api/v1/auth/apple/login/`，提交 `identity_token`、`nonce`、Web Service ID 对应的 `bundle_id`、浏览器 `device_id`，首次授权时可携带 `email/full_name`。
- Apple Web 授权前必须配置 Service ID、授权域名和 HTTPS Return URL；每次登录生成一次性 `state + nonce`，回调时校验并立即消费。
- Apple 按钮使用官方允许的“使用 Apple 登录”视觉资产；授权中禁止重复打开窗口，用户取消回到登录选择态而不建立会话。
- `当前缺口`：`AppleLoginSerializer` 接收 `authorization_code`，但 `AppleLoginView` 当前只把 `identity_token/nonce` 传入登录服务；Apple Web 回调、`state` 持久化/消费和 authorization code 服务端兑换尚未确认实现。
- `当前缺口`：Apple nonce 只在请求值和 Token claim 同时存在时比对；Web 登录需收紧为“已发放 nonce 必须存在且匹配”。生产环境还必须开启 Apple JWKS HTTPS 证书校验，不得使用当前默认的未校验 TLS 配置。
- Token 刷新复用 `POST /api/v1/auth/token/refresh/`，冷启可用 `GET /api/v1/auth/session/` 校验当前账号，退出使用 `POST /api/v1/auth/logout/`。
- 当前后端以 JSON 返回 access/refresh。工单要求 access 只保存在内存；refresh 的最终安全存储需在实现前确定。推荐增加 SameSite HttpOnly Cookie/BFF，不能未经评审长期裸存 `localStorage`。
- HTTP 和 WS 共用一个 Token 状态源；刷新失败后原子清理用户、Thread Cache、Run 订阅和敏感草稿。
- 手机号与 Apple ID 指向不同已有账号时，不得在登录流程静默合并；需进入现有 `accounts/identities/*` 的显式绑定/二次验证流程。
- 不在前端接收或保存 AI Provider API Key。
- Next.js 代理只处理同源与开发便利，不改变 Django 业务错误结构。

### 验收标准

- `npm run dev/build/lint/test` 可独立执行。
- 未登录访问 `/chat/*` 跳转登录；登录成功回到原目标。
- `+86` 手机号能完成发送验证码、倒计时、校验和首次创建/已有账号登录。
- 手机号、验证码和 Apple 三个 UI 状态与 `AI 对话 Web App Plain Text UI 设计.md` 一致，在 `366px` 宽屏幕无水平溢出。
- 未勾选协议时两种登录都不发起网络请求；协议链接可用键盘单独打开。
- Apple ID 能在支持的浏览器完成授权，缺失/错误 `state/nonce`、过期 Token、不匹配 audience 和用户取消都不建立会话；生产环境 JWKS 请求必须验证 TLS 证书。
- 同一账号在 iOS 与 Web 登录后可见同一 Thread/Message，不会按登录方式创建孤立聊天账号。
- 多个并发 401 只发起一次 refresh；失败后统一退出。
- 退出账号后上一账号的消息、附件 URL 和 WS 订阅不可见。

### 技术细节与设计代码位置

- `当前实现`：`SparkService/urls.py`、`accounts/urls.py` 暴露手机 OTP、Apple、token/refresh、session 和 logout；`accounts/auth/views.py`、`accounts/otp/views.py` 统一返回 `access_token/refresh_token`。
- `当前实现`：`accounts/services/otp_service.py` 处理手机号规范化、发送状态、错误次数、锁定和账号解析；`accounts/services/apple_identity_service.py` 校验 Apple JWKS、issuer、audience 和时间声明。
- `参考实现`：参考 Web 根目录下 `app/(auth)/login/page.tsx`、`app/(workspace)/layout.tsx`；用户提供的登录 HTML 只参考布局和状态，不直接复制类名、SVG、base64 或第三方品牌文案。
- `建议实现`：`chat-web/app/(auth)/login/page.tsx`、`chat-web/components/auth/PhoneOtpForm.tsx`、`AppleSignInButton.tsx`、`chat-web/lib/api/auth.ts`、`apple-auth-state.ts`、`token-store.ts`。

## 四、App Shell、最右全局导航与会话侧栏

### 需求说明

复刻 DeepTutor Chat Workspace 的会话列表体验，并按 Spark 健康业务重组导航。桌面端最右侧固定全局业务导航，左侧显示当前模块的二级导航；移动端转换为底部 Tab 和 Drawer。

### 基础要求与业务规则

- 最右全局导航宽 `88px`，包含对话、知识库、医疗、饮食、运动、记忆、设置七个入口。
- 对话页左侧二级侧栏宽 `300px`，可收窄到 `248px`；DeepTutor `220px/60px` 只作参考。
- 主内容使用 `h-dvh`，页面本身不滚动，消息区独立滚动。
- 移动端断点 `<768px`：全局导航转底部 Tab，二级侧栏离开布局成为抽屉；关闭时设置 `inert`。
- 顶部为 Spark 品牌与折叠按钮；主体只保留“新对话”和最近会话；底部为设置/账号/退出。
- 会话行显示标题、选中态、运行状态；支持重命名、软删除、加载/空/错误状态。
- 新建会话前若当前 Run 正在生成，先请求取消或明确保留后台运行，行为必须统一，不能静默串线。
- 会话列表来自服务端 Thread Pull/List，不使用仅本地生成的第二份列表。
- 分享、导出、复制、反馈属于会话上下文动作，不与七个全局入口混在同一导航组。

### 验收标准

- 1440px 及以上保持“左二级导航 + 中央工作区 + 可选上下文动作 + 最右全局导航”。
- 七个入口可通过鼠标、键盘和屏幕阅读器访问，路由与 active 状态一致。
- 390px 移动端抽屉可用 Escape、遮罩和导航完成关闭。
- 运行中的会话有非纯颜色状态提示；删除当前会话后路由和状态正确收敛。
- 键盘 Tab 不会进入关闭的移动侧栏。

### 技术细节与设计代码位置

- `参考实现`：参考 Web 根目录下 `components/layout/AppShell.tsx`、`components/sidebar/SidebarShell.tsx`、`WorkspaceSidebar.tsx`。
- 参考尺寸来自真实代码：`220px/60px`、`768px` 断点、`h-dvh`。
- `建议实现`：`chat-web/components/layout/AppShell.tsx`、`GlobalNavigationRail.tsx`、`SecondarySidebar.tsx`、`sidebar/ChatSidebar.tsx`。

## 五、聊天工作区与视觉对齐

### 需求说明

聊天主区域在空会话和有消息两种状态间平滑转换，整体风格基本保持 DeepTutor 的轻量、编辑器式对话界面。

### 基础要求与业务规则

#### 布局基线

- 标题、消息流和有消息状态的 Composer 最大宽度 `960px`，左右 padding `24px`。
- 空会话 Composer 最大宽度 `768px`，垂直位置接近页面中下部；首次发送后以 `650ms cubic-bezier(0.16,1,0.3,1)` 过渡到底部。
- 消息组垂直间距参考 `36px`；用户消息最大宽度约 `75%`；助手消息保持开放式内容列，不强制气泡包裹全部 Markdown。
- 标题使用 serif 字体，正文/UI 使用 sans 字体。推荐 Geist + Lora，与参考一致。

#### 色彩与表面

- 默认采用参考 `theme-snow`：背景 `#fff`、正文 `#0d0d0d`、muted `#f2f2f2`、边框 `#e5e5e5`、主色 `#2563eb`。
- 保留 CSS Variable Token：background、foreground、card、primary、muted、border、destructive、ring。
- Composer 为白色 Card、`26px` 圆角、细边框与克制双层阴影；普通区块不使用重渐变或高饱和背景。
- Spark Logo、产品名和健康业务文案替换参考品牌，不复制 DeepTutor 素材。

#### 响应式和动效

- 弹层出现使用 `160–180ms`；抽屉/预览使用约 `220ms`；按钮反馈 `150–200ms`。
- 动效只表达打开、发送、运行、取消、定位和状态变化。
- `prefers-reduced-motion` 下停止循环动画并缩短过渡。

### 验收标准

- 在同尺寸截图对比中，App Shell、消息列、Composer、标题和侧栏的几何结构与参考基本一致。
- Light/Snow 主题文本、图标、边框满足 WCAG AA；焦点环清晰。
- 375/390、768、1024、1440、1920 五档无水平溢出或 Composer 被浏览器工具栏遮挡。
- “基本一致”不等于复制教学导航；Spark 业务差异必须有文档化映射。

### 技术细节与设计代码位置

- `参考实现`：`web/app/(workspace)/home/[[...sessionId]]/page.tsx`、`web/app/globals.css`、`web/tailwind.config.js`。
- 真实参考值：消息列 `960px`、空 Composer `768px`、Composer `26px`、侧栏 `220/60px`、消息间距 `space-y-9`。
- `建议实现`：`chat-web/app/globals.css`、`tailwind.config.ts`、`components/chat/*`。

## 六、消息流与消息块渲染

### 需求说明

按服务端 Message/Block 数据渲染用户、助手、系统、工具、附件、错误、健康资源与客户端工具卡片，流式和历史加载必须使用相同渲染器。

### 基础要求与业务规则

- `ChatMessageList` 只接收领域 ViewModel；block kind 的分支集中到 `ChatBlockRenderer`。
- 用户提供的消息卡可直接作为 UI 基线：消息列 `max-width:960px`、`px:24px`、组间距 `36px`；用户消息最大宽 `75%`、右对齐、`14px` 浅色气泡。
- 助手消息保留开放式文档布局，正文 `16px/1.75`；不使用一个大气泡包住整篇 Markdown。
- 首期 block：text、deepThought 摘要状态、tool、imageGallery、fileAttachments、error、assistantStatusCard、healthResourceReference、medicalRiskNotice、medicalDisclaimerCard、clientToolRequest。
- Markdown 支持 GFM、代码块、表格、链接与数学公式；原始 HTML 默认禁用或严格清洗。
- 流式 text delta 聚合到稳定 block_id；revision 倒退或重复 sequence 不覆盖新状态。
- ToolActivity 默认紧凑折叠，展示工具名、运行/成功/失败、耗时；不得直接展示隐私参数或完整内部结果。
- Run 轨迹头显示状态、总耗时和展开控件；折叠内容使用纵向轴呈现 reasoning 摘要、工具名、目标摘要和单步状态。
- 用户消息支持复制与编辑；编辑会创建新 Run/分支，不静默覆盖旧回复。助手消息支持复制、朗读、重新生成、停止/重试和删除；危险操作需确认。
- Token、费用和内部调用次数只在管理/调试模式显示，普通用户默认不展示。
- 自动滚动只在用户位于底部附近时跟随；用户上滑后显示“回到底部”，不得强制抢滚动。

### 验收标准

- 历史加载与流式完成后的 DOM 结构和样式一致。
- 重复/乱序事件不会产生重复文字、重复工具卡或状态回退。
- 长代码、宽表格、超长 URL、中文英文混排不撑破 960px 内容列。
- 鼠标 hover、键盘 focus-within 和触屏操作都能访问消息操作，不存在仅 hover 可用的功能。
- 工具失败和 Run 失败能在消息内给出可操作反馈。

### 技术细节与设计代码位置

- `当前实现`：服务端已有 `ChatMessageBlock` 及 `kind/status/revision/payload`。
- `参考实现`：参考 Web 根目录下 `components/chat/home/ChatMessages.tsx`、`TracePanels.tsx`、`components/common/AssistantResponse.tsx`。
- `建议实现`：`ChatMessageList.tsx`、`UserMessageCard.tsx`、`AssistantMessage.tsx`、`ChatBlockRenderer.tsx`、`RunTrace.tsx`、`ToolActivity.tsx`、事件到 ViewModel 的 projector。

## 七、Composer、附件与发送控制

### 需求说明

复刻参考 Composer 的核心结构：大圆角输入容器、上下文/附件区域、底部轻量工具栏，以及同一个按钮在发送与停止之间切换。

### 基础要求与业务规则

- Composer 外壳 `26px` 圆角；输入、附件、引用和工具栏属于同一表面。
- 用户提供的 textarea 结构可直接复用：外层 `px-4 pt-3.5 pb-2`，`rows=1`，`maxLength=32000`，初始高 `28px`，`16px/relaxed`，placeholder 为“今天我能帮您什么？”。
- textarea 以 `150ms ease-out` 随内容自动增高，最高 `200px`，超过后内部滚动；接近字数上限时显示计数器。
- 工具栏可直接复用参考层级：外层 `px-3 pb-2 pt-0.5`，控件高 `32px`；左侧为对话模式和添加文件/上下文，右侧为知识库、成员、模型、上下文用量、语音与发送/停止。
- 参考中 Persona 映射为 Spark 健康成员/对话角色；模型别名和图标由服务端配置驱动，不写死参考模型名。
- 发送按钮四态：idle、blocked、ready、streaming；streaming 时同一个按钮变为停止，不替换点击目标。
- Enter 发送、Shift+Enter 换行；IME 中文组合输入时 Enter 不误发送。
- 支持点击、拖放、粘贴添加附件；发送前显示缩略或文件卡；校验类型、数量、单文件和总大小。
- 第一阶段保留模型选择、附件和成员/健康资料入口；不复制 DeepTutor 的 Capability/Notebook/Books/Agents 选择器。
- 上下文用量显示圆形进度和百分比，数据来自服务端；不向普通用户显示内部 system prompt 原文。
- 发送立即创建 optimistic 用户消息，但以服务端 ACK 的 client_message_id/run_id 对账。
- active Run 时禁止重复发送；停止后保留已生成内容并显示 cancelled 状态。

### 验收标准

- 中文输入法、键盘、拖放、粘贴和移动端软键盘行为正确。
- textarea 在 1 行、多行和超过 `200px` 三种高度状态下无跳动；`32000` 字符上限与服务端校验一致。
- 960px 内容宽度时工具栏展示关键文字，窄屏收缩为图标但仍保留可读 `aria-label`。
- 发送到 streaming 的按钮位置不跳动；点击停止只提交一次取消。
- 附件失败不会清空文本草稿；成功发送后才清理本轮附件和引用。
- 重复点击/网络重试复用同一 Idempotency-Key。

### 技术细节与设计代码位置

- `参考实现`：参考 Web 根目录下 `components/chat/home/ChatComposer.tsx`、`ComposerInput.tsx`、`tests/composer-keyboard.test.ts`；用户提供的 textarea、工具栏和消息卡 HTML 只复用 UI 层级与尺寸，数据和事件必须接入 SparkService。
- 参考真实值：有消息宽 `960px`、空态 `768px`、发送控件 `32px` 圆形、菜单 `160–180ms`。
- `建议实现`：`chat-web/components/chat/ChatComposer.tsx`、`ComposerInput.tsx`、`ComposerToolbar.tsx`、`ContextUsageButton.tsx`、`hooks/useImeComposing.ts`、附件上传 Gateway。

## 八、Run 流式连接、重连与恢复

### 需求说明

REST 负责资源与可靠查询，WebSocket 负责 Run 实时事件。前端连接断开后不把 Run 判为失败，而是重连并从最后 sequence 继续。

### 基础要求与业务规则

- 维护每个活动 Run 的 `lastSequence`，事件按 `run_id + sequence/event_id` 去重。
- 支持 start、subscribe、resume、cancel、client tool result；具体名称以后端最终合同为准。
- 心跳参考 DeepTutor：30 秒发送 ping、45 秒无消息判定连接异常；参数需可配置。
- 重连使用指数退避并带随机抖动，最多次数后进入可手动重试状态。
- WS 恢复后先订阅 `after_sequence`；同时用 REST 获取 Run/Message 最终状态作为兜底。
- reducer 按 block revision 处理消息；不允许 React 组件直接 append 文本。
- 页面刷新后从 URL threadId、Thread Message API 和 Active Run API 恢复。

### 验收标准

- 流式中断 5 秒后恢复，文本不重不漏，发送按钮最终正确结束。
- Done 丢失时，REST 兜底可清除 streaming 状态。
- 页面刷新和切换会话不会把 A 会话事件写到 B 会话。
- 同一 Run 重复订阅不会重复 Tool 卡或 Usage。

### 技术细节与设计代码位置

- `参考实现`：参考 Web 根目录下 `lib/unified-ws.ts`、`context/UnifiedChatContext.tsx`，包括 heartbeat、指数重连、turn reconcile。
- `当前依赖`：SparkService 当前 `/ws/chat/sync/` 只发 sync hint；Run 事件协议需后端先补齐。
- `建议实现`：`chat-web/lib/chat-ws.ts`、`event-reducer.ts`、`ChatRuntimeContext.tsx`。

## 九、整体业务流程

### 9.1 手机号验证码登录

```text
输入 +86 手机号
  -> 前端格式校验与发送防重
  -> POST /api/v1/otp/phone/request/
  -> 保存 otp_id 并开始倒计时
  -> 输入验证码
  -> POST /api/v1/otp/phone/verify/
  -> 服务端校验过期/错误次数/锁定/bundle/device
  -> 解析已有身份或创建账号
  -> 签发 access/refresh
  -> 加载当前账号 Thread
```

### 9.2 使用 Apple ID 登录

```text
点击“使用 Apple ID 登录”
  -> 生成并暂存一次性 state + nonce
  -> Apple Web 授权
  -> 回调校验 state，获取 identity_token/code
  -> POST /api/v1/auth/apple/login/
  -> 服务端校验 JWKS/issuer/audience/expiry/nonce
  -> 解析 Apple SocialIdentity，首登创建账号
  -> 签发 access/refresh
  -> 清理一次性 Apple 授权状态并加载 Thread
```

### 9.3 登录后聊天流程

```text
访问 /chat/{threadId?}
  -> 恢复/校验登录
  -> 拉取会话列表
  -> 新建或加载 Thread 与消息
  -> 检查活动 Run 并订阅 after_sequence
  -> 用户编辑文本/附件/成员引用
  -> 幂等创建 Run
  -> optimistic user message + assistant placeholder
  -> WS Event Reducer 更新 block/tool/usage/status
  -> Done 后用服务端 Message 对账
  -> chat_sync 使 iOS 获得同一消息
```

### 成功路径

发送后立即显示用户消息；首个 Run 事件激活助手区；delta、Tool 和 Block 渐进呈现；Done 固化消息并允许下一轮输入。

### 失败、重试和恢复

- 登录过期：单飞刷新；失败退出并清理账号态。
- Thread 加载失败：保留侧栏，主区显示重试。
- 创建 Run 失败：撤销或标记 optimistic 消息失败，保留草稿可重试。
- WS 断开：显示“正在重连”，不立即宣告 Run 失败。
- Provider/Tool 失败：渲染服务端错误码对应提示，不自行猜测最终状态。

### 取消、并发和幂等

- 一 Thread 一活动 Run；按钮和服务端同时防重复。
- create/cancel/tool result 都携带幂等标识。
- 切换 Thread 只更换订阅与视图，不错误取消后台 Run；若产品要求取消，必须由明确操作触发。

## 十、状态模型

| 状态 | 进入条件 | 用户可见结果 | 退出条件 |
| --- | --- | --- | --- |
| `bootstrapping` | App 启动 | 全屏轻量加载 | 认证完成 |
| `unauthenticated` | 无有效会话 | 登录页 | 登录成功 |
| `threadLoading` | 打开会话 | 会话骨架 | 成功/失败 |
| `idleEmpty` | 无消息 | 居中欢迎与 Composer | 发送/切换 |
| `idleReady` | 有历史无 Run | 消息流与底部 Composer | 发送 |
| `submitting` | 创建 Run | 用户消息 optimistic | ACK/失败 |
| `streaming` | Run running | delta/Tool/停止按钮 | Done/失败/取消/断线 |
| `waitingForClientTool` | Run 等待设备 | 等待卡片与说明 | 结果/过期/取消 |
| `reconnecting` | WS 异常 | 非阻塞重连提示 | 恢复/耗尽 |
| `failed` | 请求或 Run 失败 | 错误与重试 | 重试/新消息 |

## 十一、数据与持久化

| 数据 | 所有者 | 前端位置 | 生命周期 | 清理 |
| --- | --- | --- | --- | --- |
| Thread/Message/Block | SparkService | 内存 Cache | 当前账号会话 | 退出/淘汰 |
| Run/Event sequence | SparkService | Runtime Context | 活动/最近 Run | 终态后压缩 |
| 输入草稿 | 用户设备 | session/local storage（不含附件原文） | 每 Thread | 发送/删除/退出策略 |
| access token | 账号服务 | 内存 | 短期 | 刷新失败/退出 |
| refresh token | 账号服务 | 待安全方案确认 | 登录会话 | 退出/撤销 |
| phone `otp_id`/倒计时 | 账号服务/前端 | 内存或 sessionStorage | 单次验证 | 成功/过期/更换号码 |
| Apple `state/nonce` | 认证层 | HttpOnly 会话或等价短期安全存储 | 单次 Apple 授权 | 回调成功/失败/超时立即消费 |
| Sidebar/Theme 偏好 | 前端 | localStorage | 设备级 | 用户重置 |
| 附件预览 URL | 前端 | Object URL | 本轮/预览期 | remove/revoke/unmount |

不得把医疗正文、附件 Base64、Provider Key、完整 Tool 参数放入 localStorage。

## 十二、错误模型

统一错误归一化、Toast/字段/横幅/Run 卡片分流、视觉、去重、无障碍和业务码接入详见 [AI 对话 Web App 统一错误提示工单](./AI%20对话%20Web%20App%20统一错误提示工单.md)。本节只保留业务错误总览。

| 错误 | 是否重试 | 用户反馈 | 清理/恢复 |
| --- | --- | --- | --- |
| 401/refresh 失败 | 否 | 登录已过期 | 清理账号态与订阅 |
| 手机号不支持/短信发送失败 | 有条件 | 号码或发送失败原因 | 保留号码，按 retryable 允许重发 |
| OTP 错误/过期/锁定/已使用 | 修正或重发 | 展示精确可恢复状态 | 禁用重复校验，必要时重新获取 `otp_id` |
| Apple 取消/`state` 不匹配 | 否 | 登录未完成 | 消费授权状态，不创建本地会话 |
| Apple audience/token/JWKS 错误 | 部分可重试 | 无法验证 Apple 身份 | 不签发 Spark Token；JWKS 临时失败按服务错误处理 |
| Thread 404 | 否 | 会话不存在 | 返回新对话 |
| Run 409 active | 订阅现有 Run | 正在生成 | 获取 active run |
| 网络离线/WS 断开 | 是 | 正在重连 | after_sequence 恢复 |
| 附件校验失败 | 修正后 | 文件原因 | 保留文本 |
| Provider/Tool failed | 按服务端 | 消息内错误/重试 | 等待终态对账 |
| client tool unsupported | 否 | 当前网页不支持 | 提供移动端/替代方案 |
| 事件协议未知类型 | 否 | 不阻断对话 | 记录并忽略/通用卡 |

## 十三、与其他模块的接口边界

### 本模块负责

登录态聊天 UI、Thread 导航、消息/Block 渲染、Composer、Run 事件消费、重连、前端状态和视觉还原。

### 本模块不负责

模型调用、Prompt、工具授权判定、医疗权限、消息最终事实、计费计算、HealthKit 读取、后台运营。

### 上游调用方

浏览器用户、产品入口链接、未来账户中心导航。

### 下游依赖

`accounts`、`chat_sync`、服务端 AI Run、`ai_config` 模型展示、`file_manager` 上传/附件、医疗成员/资源选择 API。

### 输入和输出契约

输入为 REST DTO 与 Run Event；输出为创建/取消 Run、附件上传、Thread 操作和客户端 ToolResult。所有 DTO 必须生成 TypeScript 类型或由 OpenAPI 校验，禁止散落手写不一致字段。

## 十四、关键代码对应关系

| 能力 | SparkService 当前 | DeepTutor 参考 | 目标 |
| --- | --- | --- | --- |
| 独立 App | 当前无 | `web/package.json`、`app/layout.tsx` | `chat-web/*` |
| App Shell | 当前无 | `components/layout/AppShell.tsx` | `chat-web/components/layout/AppShell.tsx` |
| 会话侧栏 | 仅后台查看组件 | `SidebarShell.tsx`、`WorkspaceSidebar.tsx` | `ChatSidebar.tsx` |
| Chat 页面 | 当前无 | `app/(workspace)/home/[[...sessionId]]/page.tsx` | `app/(workspace)/chat/[[...threadId]]/page.tsx` |
| 消息流 | `backoffice-web` 仅管理查看 | `ChatMessages.tsx`、`TracePanels.tsx` | Chat Block 渲染器 |
| Composer | 当前无 | `ChatComposer.tsx`、`ComposerInput.tsx` | Spark Composer |
| 运行状态 | 服务端 Run 尚缺 | `UnifiedChatContext.tsx` | `ChatRuntimeContext.tsx` |
| WS | 只有 sync hint | `lib/unified-ws.ts` | `lib/chat-ws.ts` |
| 样式 | 公开站/后台各自 CSS | `globals.css`、Tailwind Token | Spark Snow 主题 |
| 测试 | open-web 无测试目录 | `web/tests/*`、Playwright audit | node/component/E2E/视觉测试 |

## 十五、测试策略

### 已有测试

- SparkService 当前没有 Chat Web 测试。
- DeepTutor 可参考 `composer-keyboard.test.ts`、`turn-reconcile.test.ts`、`ask-user-state.test.ts`、`chat-outline.test.ts`、Playwright UI audit。

### 建议补充测试

- reducer：事件去重、乱序、revision、Done 丢失、跨 Thread 隔离。
- auth：手机 OTP 发送/校验/倒计时/限流，Apple `state/nonce/audience` 与用户取消，单飞 refresh、退出清理、路由回跳。
- component：Sidebar、Composer 四态、IME、附件、Tool 卡、未知 Block。
- E2E：登录、新建会话、流式、停止、刷新恢复、断网重连、删除会话。
- 视觉：375/390/768/1024/1440 截图基线；与参考结构做人工验收。
- 无障碍：键盘、焦点陷阱、drawer inert、aria-live、reduced motion、对比度。

## 十六、当前实现、缺口与演进

### 当前实现

- SparkService 有 Vue `open-web/backoffice-web`、JWT、Thread/Message/Block 同步和 WebSocket JWT。
- SparkService 已有手机 OTP、Apple ID、Token 刷新、当前会话、退出、SocialIdentity 与登录审计的服务端能力。
- DeepTutor 参考前端有完整 Next Chat Workspace、事件 reducer、断线重连和测试资产。

### 当前缺口

- `chat-web/` 未创建。
- 无 Web 手机验证码登录页、Apple 登录按钮与回调页。
- Apple Web Service ID、授权域名/Return URL、`state` 校验、强制 nonce、authorization code 兑换和生产 JWKS TLS 校验链路尚未收口。
- 服务端 Run/Event API 未实现，前端不能完成真实流式闭环。
- Web Token 安全存储、部署域名、CORS/CSRF、附件限制尚需确定。
- 健康资源选择 API 与 Web 客户端工具支持矩阵尚未固化。

### 建议演进与任务拆分

| 工单 | 内容 | 前置依赖 | 交付结果 |
| --- | --- | --- | --- |
| `CHAT-WEB-000` | 锁定 DeepTutor 源版本，建立 Apache-2.0/THIRD_PARTY_NOTICES，按五级迁移清单登记和迁移 | 参考工程可读 | 每个文件均有分类、来源、修改摘要和验证证据 |
| `CHAT-WEB-001` | Next 工程、Token、字体、主题、lint/test | 无 | 可独立启动构建 |
| `CHAT-WEB-002A` | 手机号输入、OTP 发送/校验、倒计时与错误状态 | Phone OTP API/SMS 配置 | 手机号登录闭环 |
| `CHAT-WEB-002B` | Apple ID 按钮、Service ID 配置、回调、`state/nonce`、身份 Token 交换 | Apple Developer 配置/Auth API | Apple Web 登录闭环 |
| `CHAT-WEB-002C` | Token 安全存储、单飞刷新、当前会话、路由守卫、退出清理 | 002A/002B/Auth API | 统一认证会话 |
| `CHAT-WEB-003` | App Shell、Sidebar、会话 CRUD | Thread API | 会话工作区 |
| `CHAT-WEB-004` | 复用消息卡 UI，接入消息历史、Block Renderer、Markdown、Run 轨迹 | Message API | 历史对话 |
| `CHAT-WEB-005` | 复用 textarea/工具栏 UI，接入 Composer、附件、模型、成员/资源入口 | File/AI/Medical API | 可提交消息 |
| `CHAT-WEB-006` | Run WS、Reducer、恢复、取消 | Run/Event API | 实时对话闭环 |
| `CHAT-WEB-007` | ToolActivity、客户端 Tool 卡、错误/Usage | Tool/Event 合同 | 完整运行状态 |
| `CHAT-WEB-008` | 响应式、无障碍、视觉对齐、E2E | 前述全部 | 上线候选 |
| `CHAT-WEB-009` | 最右全局导航、通用二级侧栏、七模块路由 | `CHAT-WEB-001` | 健康 AI 工作台骨架 |
| `CHAT-WEB-010` | 知识库页骨架与上传/处理/失败/引用状态 | File/Knowledge API | 知识库工作区 |
| `CHAT-WEB-011` | 医疗概览、报告、检验、用药、复诊 UI | Medical API | 医疗工作区 |
| `CHAT-WEB-012` | 饮食概览、餐次记录、营养趋势、AI 评估 UI | Nutrition API | 饮食工作区 |
| `CHAT-WEB-013` | 运动概览、记录、计划与客户端同步状态 | Activity/Client Bridge API | 运动工作区 |
| `CHAT-WEB-014` | AI 记忆确认、来源、编辑、删除与停用 UI | Memory API | 可控记忆工作区 |
| `CHAT-WEB-015` | 账号、对话、隐私、数据、记忆与外观设置 UI | Auth/Settings API | 设置工作区 |
| `CHAT-WEB-016` | 全局 Toast、错误归一化、错误码目录、呈现分流、去重与无障碍 | `CHAT-WEB-001`、API 错误合同 | 统一错误提示；详见 `AI 对话 Web App 统一错误提示工单.md` |

### 16.4 Web P0–P7 分阶段计划入口

Web 的阶段目标、服务端联调门禁、源码迁移边界、可见 UI、工单归属和出口验收统一维护在 [AI 对话 Web App P0–P7 分阶段实施计划](./AI%20对话%20Web%20App%20P0-P7%20分阶段实施计划.md)。本工单不再维护重复阶段表；工单内容或依赖变更时，必须同步更新该阶段计划中的工单映射。

## 十七、整体验收标准

- [ ] `chat-web/` 可独立开发、测试、构建和部署，不影响另外两个 Web App。
- [ ] 登录复用 SparkService 账号，不新增前端私有用户体系。
- [ ] 支持 `+86` 手机号验证码登录，发送、倒计时、校验、锁定、过期和限流状态完整。
- [ ] 支持使用 Apple ID 登录，Service ID、HTTPS Return URL、`state/nonce`、audience 与用户取消经安全测试。
- [ ] 手机号与 Apple ID 登录使用同一账号解析规则，不静默合并冲突身份。
- [ ] Thread/Message/Block 与 iOS 共用服务端数据。
- [ ] 桌面侧栏 220/60px、内容列 960px、空态 Composer 768px、Composer 26px 等视觉基线落实。
- [ ] 页面结构、密度、动效和交互与 DeepTutor Chat Workspace 基本一致，品牌与业务已替换。
- [ ] 发送/停止为同一控件，IME、附件、重复提交正确。
- [ ] Run Event 可去重、重放、断线恢复，页面刷新不丢活动状态。
- [ ] 服务端工具、错误、Usage 和客户端工具等待均可渲染。
- [ ] Web 不支持 HealthKit 时提供明确替代，不伪造设备能力。
- [ ] Token、医疗数据、附件和 Tool 参数不发生不必要持久化或日志泄露。
- [ ] 手机、平板、桌面布局和键盘操作通过验收。
- [ ] reducer、组件、E2E、视觉回归和无障碍检查通过。
