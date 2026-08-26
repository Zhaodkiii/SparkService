# CHAT-WEB-019 Web Apple 独立登录与会话隔离需求工单

创建日期：2026-08-25  
状态：基础链路已实现，待并发补强与完整验收  
优先级：P0  
阶段归属：Web 对话认证与会话维护  
关联模块：`accounts`、`chat-web`、Web 对话登录态  
实施约束：本文件只创建需求工单，不修改业务代码、配置、数据库或客户端工程。

## 一、需求背景

Chat Web 需要复用 SparkService 的账号和对话数据，但 Web Apple 登录不能继续借用移动端 Apple 登录和移动设备会话。

立项时 Web BFF 的 Apple callback 曾调用移动端：

```http
POST /api/v1/auth/apple/login/
```

同时曾给浏览器生成随机 `device_id`。服务端随后进入 `AccountDeviceSession`，浏览器因此可能替换真实移动端会话。当前基础改造已将 Web callback 切换至独立 Web Apple API，本工单继续补强跨域不互斥和移动端全平台单活验收。

本工单以 Web 对话的 Apple 登录和 Web Session 隔离为主；移动端部分只固化并补强服务端既有单活不变量，不授权修改对应客户端或移动登录流程。用户提供的移动端 Apple 登录失败日志仅是现状证据。

## 二、最终范围

### 2.1 本工单包含

1. 新增 Web 专属 Apple 登录服务端入口。
2. Chat Web Apple callback 改为调用 Web 专属入口。
3. 新增独立 Web Session 和 Web Token 生命周期。
4. Web 登录、刷新和退出不影响移动端 Session。
5. 移动端登录不影响 Web Session。
6. Web 登录同一 User 后，共享已有 Thread、Message、Block 和 Run。
7. Web 与一个移动端会话允许同时在线，双方登录、刷新和退出互不排挤。
8. 同一 User 的移动端继续保持全平台单活：iOS、Android、HarmonyOS 中最多一个有效移动会话。

### 2.2 明确不包含

- 不检查 Pro 用户。
- 不修改对话模型获取和模型选择。
- 不修改 Run、Provider factory 或模型网关。
- 不修改任何 iOS 客户端文件、代码、接口调用、参数、状态机或页面流程。
- 不修改任何 Android 或 HarmonyOS 客户端内容。
- 不修复移动端 Apple 登录日志中的 JWKS/证书问题。
- 不修改移动端 Apple 登录服务端入口的现有契约和流程。

### 2.3 Bootstrap 保持原样

本工单禁止修改：

```http
GET /api/v1/ai/config/bootstrap
```

具体约束：

1. 不修改 Pro 判断。
2. 不修改 `scenarios`、`default_model`、`models` 或 `smallTasks`。
3. 不删除、不脱敏、不改名 `endpoint` 和明文 `api_key`。
4. 不新增 Web 专属 bootstrap DTO。
5. 不修改客户端 bootstrap 解析和缓存。
6. 不将 bootstrap 纳入本工单测试、灰度和验收。

## 三、目标与非目标

### 3.1 目标

- Web Apple 使用独立服务端 API、验证服务和 Web Session。
- Web Apple 不再调用移动端 `/api/v1/auth/apple/login/`。
- Web 登录不创建 `TrustedDevice` 或 `AccountDeviceSession`。
- Web 和移动端可以同时保持登录。
- Web 已登录后，iOS、Android 或 HarmonyOS 正常登录不得撤销 WebSession。
- 移动端已登录后，Web 正常登录不得撤销 AccountDeviceSession。
- 同一 User 的 iOS、Android、HarmonyOS 不允许同时保持两个 ACTIVE 移动会话。
- Web 与移动端登录同一 User 后共享同一套对话。
- Web Session 可独立刷新、撤销、退出和过期。
- Web Apple 安全校验覆盖 state、nonce、Service ID、Return URL、JWKS 和 authorization code。

### 3.2 非目标

- 不改变任何移动客户端内容或流程。
- 不改变移动 Apple 接口、Serializer、Service、错误码和 Token claim。
- 不修改 `AppleIdentityService` 的移动端验证实现。
- 不修复 `apple_jwks_unavailable`。
- 不处理 Pro、模型、Provider 或 bootstrap。
- 不实现 Apple 账号手工绑定 UI。
- 不允许 Web Apple 失败后回退移动 Apple API。
- 不决定多个 Web 浏览器的在线数量上限。

## 四、当前实现核验

### 4.1 移动 Apple 服务端链路

当前链路为：

```text
POST /api/v1/auth/apple/login/
  → AppleLoginView
  → AppleLoginSerializer
  → LoginService.authenticate_apple_and_issue_tokens
  → AccountLoginResolutionService.resolve_verified_identity
  → DeviceSessionService.activate_and_issue_tokens
  → SparkRefreshToken.for_device_session
```

该链路属于不可变兼容基线。本工单不得修改其输入、输出和执行步骤。

### 4.2 Web 链路现状

真实文件：

```text
chat-web/app/api/auth/apple/start/route.ts
chat-web/app/api/auth/apple/callback/route.ts
chat-web/app/api/auth/bootstrap/route.ts
chat-web/app/api/auth/logout/route.ts
chat-web/lib/server/auth-cookies.ts
```

立项时问题（已完成基础改造）：

- callback 调用移动 Apple API。
- callback 为浏览器生成随机 `device_id`。
- 上游返回带移动 Session claim 的 refresh token。
- Web bootstrap 刷新时继续携带浏览器 `device_id`。
- Web logout 可能按移动会话语义执行。

当前代码事实：

- callback 已只调用 `POST /api/v1/auth/apple/web/login/`。
- callback 已不再生成或提交移动 `device_id`、`bundle_id`。
- Web Apple 已签发带 `web_session_id/session_class=web` 的 Token。
- Web bootstrap 已按 Web refresh Token 恢复登录态。
- Web logout 已按 claim 只撤销当前 AccountWebSession。

本轮新增缺口不在 Web Apple 基础链路，而在跨域会话不变量的完整验收和移动端并发登录的服务端一致性。

### 4.3 现有会话事实

`AccountDeviceSession` 当前用于移动设备会话。`DeviceSessionService.activate_session_on_login` 会替换同一用户其他 ACTIVE 移动会话。

Web 未进入此模型。当前已存在并行的 `AccountWebSession`、`WebSessionService` 和 Web Token；后续只允许增量补强，不得给 `AccountDeviceSession` 增加 Web 特例。

## 五、目标架构

```text
                              Spark User
                                  │
              ┌───────────────────┴───────────────────┐
              │                                       │
       现有移动会话域                           独立 Web 会话域
       保持原服务端流程                         Chat Web BFF
              │                                       │
      AccountDeviceSession                    AccountWebSession
              │                                       │
      device_session_id                 web_session_id + class=web
              └───────────────────┬───────────────────┘
                                  │
                     Thread / Message / Block / Run
```

原则：共享账号与对话数据，隔离 Web 和移动 Session 生命周期。

## 六、Web Apple 独立登录

### 6.1 已实现接口

当前已注册：

```http
POST /api/v1/auth/apple/web/login/
```

Chat Web 保留浏览器入口：

```text
GET  /api/auth/apple/start
POST /api/auth/apple/callback
```

callback 必须只调用新 Web 上游，不再调用移动 Apple API。

### 6.2 Web 请求契约

当前上游请求：

```json
{
  "identity_token": "redacted",
  "authorization_code": "redacted",
  "nonce": "one-time-nonce",
  "service_id": "configured-web-service-id",
  "redirect_uri": "configured-https-return-url"
}
```

Web 上游不得接收或使用：

- 移动 `bundle_id`。
- 移动 `device_id`。
- `device_secret`。

`service_id` 和 `redirect_uri` 必须匹配服务端配置，不能信任浏览器任意值。

### 6.3 安全流程

```text
BFF 生成 state + nonce
  → 写入短期 HttpOnly Cookie
  → 跳转 Apple Web authorize
  → Apple form_post 回 BFF
  → BFF 校验并消费 state/nonce/return_to
  → 调用 Web Apple 上游
  → 校验 TLS/JWKS/iss/aud/exp/iat/sub/nonce
  → 服务端兑换 authorization code
  → 解析或创建 User/SocialIdentity
  → 创建 AccountWebSession
  → 签发 Web Token
  → Refresh Token 写入 HttpOnly Cookie
```

强制规则：

1. audience 只能是配置的 Web Service ID。
2. nonce 必填并严格匹配。
3. state 和 nonce 只能消费一次。
4. Return URL 必须命中 HTTPS allowlist。
5. `return_to` 只能是站内相对路径。
6. Web JWKS 使用标准 TLS 校验、超时和缓存。
7. 未知 `kid` 强制刷新，失败时拒绝 Token。
8. authorization code 由服务端兑换并校验 redirect URI。
9. Apple client secret 只留服务端。
10. Web 登录失败不得调用移动端接口兜底。

### 6.4 身份与对话共用

1. Web Service ID 应在 Apple Developer 中与主 App ID 正确分组。
2. Web Service ID 通过 `IdentityScopeService` 映射至既有账号身份作用域。
3. LoginAudit 记录真实 Service ID 和 `channel=web`。
4. Web Apple subject 命中已有身份时登录同一 User。
5. 无法安全关联时返回 `apple_web_identity_link_required`。
6. 不允许仅凭 email 或 Private Relay email 静默合并。
7. 首次 Web 用户可以创建 User/SocialIdentity，但不能创建移动设备或移动 Session。

### 6.5 当前服务端文件

以下文件已经存在：

```text
accounts/
├── auth/web_tokens.py
├── migrations/0016_account_web_session.py
├── services/web_apple_identity_service.py
├── services/web_apple_login_service.py
├── services/web_session_service.py
└── tests_web_session_and_apple_login.py
```

现有公共文件已完成 Web 增量注册：

- `accounts/auth/serializers.py` 新增 `WebAppleLoginSerializer`。
- `accounts/auth/views.py` 新增 `WebAppleLoginView`。
- `accounts/urls.py` 新增 `/auth/apple/web/login/`。
- `accounts/models.py` 新增 `AccountWebSession`。

Web 服务复用 User、SocialIdentity、IdentityScope、AccessControl、LoginAudit；不得进入 `DeviceSessionService`。禁止再次创建同职责模型、Service 或第二条 Web Apple API。

### 6.6 错误契约

| HTTP/code | msg | 场景 | Web 行为 |
|---|---|---|---|
| 400/40071 | `apple_web_callback_invalid` | state/字段缺失 | 重新发起 |
| 401/40171 | `apple_web_nonce_mismatch` | nonce 错误 | 重新发起 |
| 401/40172 | `apple_web_token_invalid` | 签名/aud/时间错误 | 登录失败 |
| 409/40971 | `apple_web_transaction_replayed` | 事务重放 | 回登录页 |
| 409/40972 | `apple_web_identity_link_required` | 身份不可安全关联 | 显示绑定提示 |
| 503/50371 | `apple_web_jwks_unavailable` | 无验证密钥 | 稍后重试 |
| 503/50372 | `apple_web_code_exchange_unavailable` | code 兑换失败 | 稍后重试 |
| 503/50373 | `web_session_store_unavailable` | Session 存储失败 | 稍后重试 |

错误响应只返回安全文案和 `request_id`，不返回证书路径、Token claim 或 Apple 原始响应。

## 七、Web Session 设计

### 7.1 AccountWebSession

当前模型：

```text
AccountWebSession
├── id: UUID
├── user_id
├── status: active/revoked/logged_out/expired
├── session_version
├── refresh_jti_hash
├── user_agent_hash
├── ip_prefix_hash（可选）
├── created_at / last_refreshed_at / expires_at
└── revoked_at / revoked_reason / request_id
```

规则：

- 不保存原始 refresh token。
- 不把浏览器随机 UUID 写入 TrustedDevice。
- Web refresh 只校验和轮换 AccountWebSession。
- Web logout 只撤销当前 Web Session。
- 新 Web 登录不撤销移动 Session。
- 移动登录不撤销 Web Session。
- WebSession 不计入移动端“单设备登录”名额。
- 移动端单活按 User 全局计算，不按操作系统、bundle ID 或登录方式分别计算。
- 账号封禁、注销和“退出所有设备”可以显式撤销两类会话。

### 7.2 Web Token

Web Token 当前包含 `web_session_id`、`web_session_version` 和 `session_class=web`，禁止携带 `device_session_id`、`device_id` 和移动 bundle ID。

### 7.3 认证分派

1. 有 `device_session_id`：继续执行现有移动 Session 校验。
2. 有 `web_session_id` 且 `session_class=web`：执行 WebSession 校验。
3. 同时存在两类 claim：拒绝非法 Token。
4. 普通用户 Token 没有 session claim：不得自动回退到当前移动 Session。
5. Admin/内部 Token 继续使用既有明确白名单。

### 7.4 Web refresh

Web refresh 当前在现有 refresh 入口按 claim 分派，并必须持续满足：

- 不查询或修改 AccountDeviceSession。
- 不接收 `device_id` 作为 Session 定位依据。
- 使用 refresh Token 内的 `web_session_id`。
- rotation 更新当前 WebSession 的 JTI hash 和版本。
- 旧 refresh 重放被拒绝，但不影响移动 Session。
- revoked/expired 返回 Web 专属错误，不返回移动 `replaced` 错误。

### 7.5 Chat Web BFF 调整

目标文件：

```text
chat-web/app/api/auth/apple/callback/route.ts
chat-web/app/api/auth/bootstrap/route.ts
chat-web/app/api/auth/logout/route.ts
chat-web/lib/server/auth-cookies.ts
```

当前实现及持续验收要求：

1. callback 改调 Web Apple 上游。
2. callback 不再生成或提交移动 `device_id`。
3. bootstrap 以 Web refresh Token 恢复 Session。
4. bootstrap 不再提交随机移动 `device_id`。
5. logout 只撤销当前 WebSession，并清理 HttpOnly cookie。
6. BFF 不持久化 Apple client secret。
7. 所有响应设置 `Cache-Control: no-store` 并透传 `X-Request-ID`。

这里的 bootstrap 指 Chat Web BFF 登录恢复入口 `/api/auth/bootstrap`，不是 `/api/v1/ai/config/bootstrap`。AI 配置 bootstrap 保持完全不变。

## 八、与移动 Session 的隔离规则

本工单不改动任何移动客户端，也不改变移动客户端现有登录流程。服务端只保证 WebSession 不参加移动会话替换。

### 8.1 会话分类

| 类别 | 客户端 | 实体 | claim | 策略 |
|---|---|---|---|---|
| Mobile | iOS、Android、HarmonyOS | AccountDeviceSession | device_session_id | 同一 User 全平台最多一个 ACTIVE |
| Web | Chat Web | AccountWebSession | web_session_id/class=web | 与 Mobile 独立 |
| Admin | 后台 | 现有 Admin JWT | 现有 claim | 不变 |

会话分类必须由登录入口和签发器决定，不能根据 User-Agent 或请求 body 猜测。

### 8.2 隔离矩阵

| 已在线 | 新登录 | 目标结果 |
|---|---|---|
| Mobile | Web | 两者同时在线 |
| Web | Mobile | 两者同时在线 |
| Web A | Web B | 均保留；本工单不限制 Web 数量 |
| iOS A | Android B | Android B 保留，iOS A 移动会话失效；Web 不变 |
| Android A | HarmonyOS B | HarmonyOS B 保留，Android A 移动会话失效；Web 不变 |
| HarmonyOS A | iOS B | iOS B 保留，HarmonyOS A 移动会话失效；Web 不变 |
| 任一 Mobile A | 同一安装再次登录 | 复用/轮换当前移动会话，不产生第二个 ACTIVE；Web 不变 |
| 任一 Mobile A | 另一 Mobile B 并发登录 | 事务完成后只能有一个 ACTIVE，最后成功提交者生效；Web 不变 |

### 8.3 服务端事务要求

- 移动端 `activate_session_on_login` 查询范围只包含 AccountDeviceSession。
- WebSession 创建、刷新和退出查询范围只包含 AccountWebSession。
- 两类 Service 不得互相调用 revoke 方法。
- Web 会话事务失败不得撤销或回滚移动 Session。
- 移动会话事务失败不得撤销或回滚 WebSession。
- 全局封禁、注销和“退出所有设备”必须显式调用两类 Service。

### 8.4 退出矩阵

| 操作 | Mobile | 当前 Web | 其他 Web |
|---|---:|---:|---:|
| 移动退出 | 沿用现状 | 不变 | 不变 |
| Web 退出 | 不变 | 撤销 | 不变 |
| 新移动登录 | 旧 Mobile 撤销、新 Mobile ACTIVE | 不变 | 不变 |
| 新 Web 登录 | 不变 | 不变 | 不变 |
| 退出所有设备 | 全部撤销 | 全部撤销 | 全部撤销 |
| 账号封禁/注销 | 全部撤销 | 全部撤销 | 全部撤销 |

`POST /api/v1/auth/logout/` 必须按 Token claim 分派。Web Token 不得触发“回退查找用户当前移动 Session”的逻辑。

### 8.5 两个会话域的强制不变量

对同一个 Spark User，服务端必须始终满足：

```text
active_mobile_session_count(user_id) <= 1
移动替换写集合 ∩ AccountWebSession = ∅
Web 登录写集合 ∩ (AccountDeviceSession + TrustedDevice) = ∅
```

Web 与移动并存不是“双设备放宽”，而是两个会话域各自执行规则：

- Web 域：允许当前用户存在多个 WebSession，本工单暂不限制浏览器数量。
- Mobile 域：iOS、Android、HarmonyOS 共同竞争同一个移动单活名额。
- 跨域：一个或多个 WebSession 可以与唯一一个 ACTIVE AccountDeviceSession 同时存在。
- 全局安全操作：只有账号封禁、账号注销或明确的“退出所有设备”可以同时撤销两个域。

平台归类必须由登录入口和 Token 签发器决定。服务端不得依赖可伪造的 User-Agent 判断 Web/Mobile，也不得因 Android、HarmonyOS 使用不同 bundle ID 就创建各自独立的 ACTIVE 配额。

### 8.6 登录时序

#### 场景 A：Web 已在线，移动端登录

```text
AccountWebSession(web-1)=ACTIVE
  -> iOS/Android/HarmonyOS 调用现有移动登录入口
  -> DeviceSessionService 锁定该 User 的移动会话域
  -> 撤销旧 AccountDeviceSession（如存在）
  -> 创建或轮换新 AccountDeviceSession
  -> AccountWebSession(web-1) 仍为 ACTIVE
  -> Web access/refresh token、Run、WS ticket 和 Thread 权限继续有效
```

禁止行为：移动登录成功后调用 `WebSessionService.revoke_all_sessions_for_user()`、修改 `AccountWebSession.session_version`，或让 Web BFF 清理登录 Cookie。

#### 场景 B：移动端已在线，Web 登录

```text
AccountDeviceSession(mobile-1)=ACTIVE
  -> Chat Web Apple 登录
  -> 创建 AccountWebSession(web-1)
  -> AccountDeviceSession(mobile-1) 仍为 ACTIVE
  -> TrustedDevice.is_revoked 仍为 false
  -> 移动 access/refresh token、推送设备和聊天同步继续有效
```

禁止行为：Web 登录进入 `DeviceSessionService.activate_session_on_login()`、创建浏览器 TrustedDevice，或把随机浏览器 ID 当作移动 `device_id`。

#### 场景 C：移动端跨平台替换

```text
iOS AccountDeviceSession=A/ACTIVE
  -> Android 或 HarmonyOS 以同一 User 登录
  -> 锁定 User 移动会话域
  -> A.status=REVOKED
  -> A.revoked_reason=replaced_by_new_device
  -> 旧 refresh JTI 加入黑名单
  -> 旧 TrustedDevice.is_revoked=true
  -> 新 AccountDeviceSession=B/ACTIVE
  -> 已有 AccountWebSession 不变
```

同一规则适用于 iOS→Android、iOS→HarmonyOS、Android→iOS、Android→HarmonyOS、HarmonyOS→iOS 和 HarmonyOS→Android，不为任何平台设置例外。

### 8.7 并发与原子性

`当前实现`：`DeviceSessionService.activate_session_on_login()` 已使用事务，并查询同一 User 的全部 ACTIVE `AccountDeviceSession`；它不按 bundle ID 切分，因此顺序登录已经符合移动全平台单活要求。

`当前缺口`：`AccountDeviceSession.Meta.constraints` 为空。仅锁定已存在的 ACTIVE 行不能完整覆盖“当前没有会话时两个平台同时首次登录”的竞态，理论上可能产生两个 ACTIVE 行。

服务端补强要求：

1. 每次移动登录事务先锁定稳定存在的 User 行，再查询和替换移动会话；同一 User 的移动登录必须串行提交。
2. 锁内再次读取 ACTIVE 会话，禁止使用锁外旧快照决定撤销对象。
3. 创建新会话与撤销旧会话必须在同一数据库事务内完成。
4. 事务提交前校验该 User 的 ACTIVE 移动会话数量不大于 1。
5. 若数据库无法使用条件唯一约束，用户行锁是强制机制；Redis 锁不得作为唯一正确性保障。
6. 同一安装重复登录可以轮换原 Session 的 `session_version`，但必须使旧 Token 版本失效。
7. 不论哪个移动登录获胜，都不得锁定、更新或撤销 `AccountWebSession`。
8. 并发失败应回滚本次移动事务，不得出现“移动登录失败但 Web 被退出”。

移动登录的外部 API、请求字段、响应字段和客户端调用时序保持不变；这里只补强服务端内部事务一致性。

### 8.8 被替换移动会话的失效语义

旧移动会话被新平台替换后：

| 入口 | 服务端结果 |
|---|---|
| 旧 access token 调用受保护 API | `401 / device_session_replaced`（业务码沿用 `40105`） |
| 旧 refresh token 刷新 | 拒绝，返回 replaced/revoked/token blacklist 对应错误 |
| 旧设备重新建立 Chat Sync WS | 鉴权失败并关闭 `4401` |
| 旧设备已存在的长连接 | 服务端按旧 `device_session_id` 定向通知并关闭，不再接收账号数据 |
| 新移动会话 | 正常访问，成为唯一 ACTIVE Mobile |
| 所有 WebSession | 状态、版本和 Token 全部不变 |

移动替换事务提交后，服务端应向旧 `device_session_id` 对应的 Channel group 发布 `auth.session.invalidated`，由 Consumer 主动关闭旧连接。不得向整个 `user_id` group 广播会话替换，否则可能误伤新移动会话或 Web 会话；不得依赖客户端自行比较 Session ID 才完成安全失效。

服务端落地要求：

1. JWT WS 鉴权成功后，将受验证 Token 的 `session_class`、`device_session_id` 写入 ASGI scope；不得从客户端额外查询参数采信 Session ID。
2. 移动 Chat Sync Consumer 除现有 user sync group 外，再加入仅属于当前 `device_session_id` 的失效 group。
3. 移动替换事务使用 `transaction.on_commit` 发布旧 Session 失效事件，避免数据库回滚后错误踢下线。
4. Consumer 收到定向事件后发送既有 `auth.session.invalidated` 控制消息并主动关闭；关闭后必须从两个 group 清理。
5. 新移动 Session、`AccountWebSession` 和 `/ws/chat/runs/` ticket 连接不得加入旧移动 Session group。
6. group 名只使用内部整数/哈希 Session ID，不包含 token、device secret 或原始 device ID。

本工单不要求修改移动客户端对错误码的展示、页面跳转或重连实现，只要求服务端继续返回既有契约。若需要优化移动端被替换后的 UI，必须另建移动端工单。

### 8.9 当前代码对应关系

| 能力 | 当前代码 | 当前结论 |
|---|---|---|
| 移动单活创建/替换 | `accounts/services/device_session_service.py::activate_session_on_login` | 已按 User 查询全部 ACTIVE 移动会话 |
| 移动旧 Token 拒绝 | `accounts/services/device_session_service.py::_validate_session_state` | 已区分 `device_session_replaced` |
| Web 独立创建 | `accounts/services/web_session_service.py::create_session` | 不读取/写入移动会话 |
| Web 独立刷新/退出 | `accounts/services/web_session_service.py` | 仅作用于当前 AccountWebSession |
| Token 域分派 | `accounts/auth/authentication.py` | Web claim 与 Device claim 分流 |
| Web/Mobile 共存测试 | `accounts/tests_web_session_and_apple_login.py` | 已覆盖移动替换后 Web Token 仍有效 |
| 移动第二设备替换测试 | `accounts/tests_device_session.py` | 已覆盖顺序登录和旧 refresh 拒绝 |
| 三平台并发竞态测试 | 当前未发现 | 本工单补充 |

文档中的 WebSession 不再只是未来建议：当前仓库已经存在 `AccountWebSession`、migration、Service 和基础测试。后续开发应以现有实现增量补强，不得重复创建第二套 Web Session 模型或服务。

### 8.10 范围再确认

本节所称 iOS、Android、HarmonyOS 仅用于定义服务端会话互斥结果：

- 不修改三个移动客户端的登录接口调用。
- 不修改移动 Apple 登录、验证码登录或设备登录流程。
- 不修改移动端 Token 存储、页面、提示、WebSocket 重连或推送注册代码。
- 不新增平台专属 Session 表。
- 不把移动单活规则扩展到 WebSession。
- 不修改 AI config bootstrap、明文 `api_key`、Pro 或模型配置。

## 九、Web 对话接入

Web Apple 登录成功后继续使用现有服务端事实层：

```text
User
  → ChatThread
  → ChatMessage / ChatMessageBlock
  → ChatRun / ChatRunEvent
  → WebSocket subscription / replay
```

要求：

1. Web Apple 命中的 `user_id` 与已有账号一致。
2. Web 从 SparkService 同步 Thread，不创建 Web 私有对话表。
3. Thread、Run、Context、Tool API 继续使用现有 User 权限。
4. WebSession 失效只中断 Web 鉴权，不删除或 tombstone 对话。
5. 移动 Session 状态变化不应中断 Web Run 或 WebSocket。
6. Web logout 不删除服务端 Thread、Message、Block、Run 和 Event。
7. 本工单不调整模型列表、模型选择或 AI 配置 bootstrap。

## 十、API 与文件变更规划

### 10.1 API

| API | 当前 | 目标 |
|---|---|---|
| `POST /auth/apple/login/` | 移动 Apple | 保持原样 |
| `POST /auth/apple/web/login/` | 不存在 | 新增 Web Apple |
| Web Apple callback | 调移动入口 | 调 Web 专属入口 |
| Web token refresh | 移动 Session 语义 | WebSession 语义 |
| `POST /auth/logout/` | 主要撤销移动 Session | 按 claim 撤销当前域 |
| `GET /auth/session/` | 账号摘要 | Web Token 同样可调用 |
| AI config bootstrap | 现有响应含明文 api_key | 完全不变 |

### 10.2 当前真实目录

```text
accounts/
├── auth/views.py
├── auth/serializers.py
├── auth/tokens.py
├── urls.py
├── models.py
└── services/
    ├── login_service.py
    ├── apple_identity_service.py
    ├── account_login_resolution_service.py
    ├── identity_scope_service.py
    └── device_session_service.py

chat-web/
├── app/api/auth/apple/start/route.ts
├── app/api/auth/apple/callback/route.ts
├── app/api/auth/bootstrap/route.ts
├── app/api/auth/logout/route.ts
└── lib/server/auth-cookies.ts
```

### 10.3 禁止修改目录

本工单禁止产生以下范围的代码 diff：

```text
ai_config/
chat_sync/ai_runtime/providers/
任何 iOS 客户端工程目录
任何 Android 客户端工程目录
任何 HarmonyOS 客户端工程目录
```

允许读取这些范围用于契约核验，但不能编辑。

### 10.4 高冲突文件所有权

- `accounts/auth/views.py`、`serializers.py`：Web Apple API 子工单独占。
- `accounts/models.py`：WebSession 模型子工单独占新增区域。
- `device_session_service.py`：除 `CHAT-WEB-019I` 为移动全平台单活增加用户级事务锁、竞态保护和审计字段外不修改；不得改变移动 API、Token claim、错误码和顺序登录结果。
- `chat-web/app/api/auth/apple/callback/route.ts`：Web callback 子工单独占。
- `chat-web/app/api/auth/bootstrap/route.ts`：WebSession 恢复子工单独占。

## 十一、测试矩阵

### 11.1 Web Apple

- 正常 form_post 和用户取消。
- state 缺失、不匹配、过期和重放。
- nonce 缺失和不匹配。
- audience 为非 Web Service ID。
- Token 过期、未来 iat、错误 iss、未知 kid、无 sub、坏签名。
- JWKS cache、刷新、超时和无可用 key。
- authorization code 成功、重复、过期、redirect URI 不匹配。
- 相同 subject 命中已有 User。
- 不同 subject 不按 email 自动合并。
- 断言 Web 登录未创建 TrustedDevice/AccountDeviceSession。
- 断言 Web 登录未调用 DeviceSessionService。

### 11.2 WebSession

- 创建、refresh rotation、旧 refresh 重放、logout、expired、revoked。
- WebSession 与 AccountDeviceSession 同时存在。
- Web refresh 不读取或修改移动 Session。
- Web logout 不撤销移动 Session。
- 移动登录不撤销 WebSession。
- Web 登录不撤销当前 ACTIVE 移动 Session，也不修改 TrustedDevice。
- Token 同时携带 Web/Mobile claim 时拒绝。
- 普通无 session claim Token 不回退移动 Session。

### 11.3 Web/Mobile 并存与移动全平台单活

按同一个 `user_id` 建立以下服务端测试矩阵：

| 前置状态 | 操作 | 必须断言 |
|---|---|---|
| Web ACTIVE | iOS 登录 | Web ACTIVE；iOS Mobile ACTIVE |
| Web ACTIVE | Android 登录 | Web ACTIVE；Android Mobile ACTIVE |
| Web ACTIVE | HarmonyOS 登录 | Web ACTIVE；HarmonyOS Mobile ACTIVE |
| iOS ACTIVE + Web ACTIVE | Android 登录 | iOS REVOKED；Android ACTIVE；Web ACTIVE |
| Android ACTIVE + Web ACTIVE | HarmonyOS 登录 | Android REVOKED；HarmonyOS ACTIVE；Web ACTIVE |
| HarmonyOS ACTIVE + Web ACTIVE | iOS 登录 | HarmonyOS REVOKED；iOS ACTIVE；Web ACTIVE |
| Mobile ACTIVE | 新 Web 登录 | Mobile/TrustedDevice 不变；新增 Web ACTIVE |
| Web A + Web B ACTIVE | Mobile 跨平台替换 | Web A/Web B 均保持 ACTIVE |
| iOS/Android/HarmonyOS 并发首次登录 | 等待全部事务完成 | AccountDeviceSession ACTIVE 总数严格等于 1 |

附加断言：

- 旧移动 access token 返回 `device_session_replaced`。
- 旧移动 refresh token 不能轮换出新 Token。
- 旧移动 Chat Sync WS 收到定向失效并由服务端关闭；新移动和 Web WS 不受影响。
- 新移动 Token 可正常访问 `/auth/session/` 和聊天同步 API。
- Web access/refresh token 在移动替换前后均有效。
- 移动替换前后的 `web_session_version`、`refresh_jti_hash` 和 `status` 完全不变。
- Web 登录前后的移动 `session_version`、`refresh_jti`、`status` 和 TrustedDevice 完全不变。
- 并发测试不能只用单线程 TestCase；必须使用能建立独立数据库连接的 TransactionTestCase/集成测试。

### 11.4 Web 对话 E2E

1. 准备已有账号及历史 Thread。
2. 同一账号完成 Web Apple 登录。
3. Web 拉取相同 Thread 和 Message。
4. Web 创建 Run 并订阅 Event。
5. 移动 Session 发生既有状态变化。
6. Web Run、WebSocket 和 Thread 同步继续正常。
7. Web logout 后移动端保持原有状态。
8. 服务端未创建 Web 私有账号或对话数据。

### 11.5 零改动门禁

- AI bootstrap fixture 不修改。
- bootstrap 的 `api_key` 字段不删除、不脱敏。
- 不新增 Pro 权益测试。
- 不修改模型选择测试。
- 不修改任何移动客户端测试或 fixture。
- 移动 Apple JWKS 503 不作为本工单修复或通过条件。

## 十二、日志与可观测性

Web 新链路允许记录：`request_id`、user_id、session_class、web_session_id 尾号、error_code 和 duration_ms。

Web 新链路禁止记录：identity token、authorization code、raw nonce、access/refresh token、Apple client secret 和完整 Apple subject。

建议指标：

- `apple_web_login_total{outcome,error_code}`。
- `apple_web_jwks_fetch_total{outcome,cache}`。
- `web_session_active_total`。
- `session_cross_domain_revoke_total`，目标值为 0。
- `web_chat_after_mobile_session_change_total{outcome}`。
- `mobile_session_replaced_total{from_platform,to_platform}`，平台值必须来自服务端受信入口映射。
- `mobile_active_session_invariant_violation_total`，目标值必须为 0。
- `cross_domain_session_revocation_total{source_domain,target_domain}`，普通登录场景目标值必须为 0。

## 十三、子工单

| 子工单 | 内容 | 依赖 | 出口证据 |
|---|---|---|---|
| `CHAT-WEB-019A` | AccountWebSession 模型与迁移 | 无 | Model/migration test |
| `CHAT-WEB-019B` | Web Token、认证、refresh、logout | 019A | Session 隔离测试 |
| `CHAT-WEB-019C` | Web Apple Token/JWKS/code 验证服务 | 019A | 安全单元测试 |
| `CHAT-WEB-019D` | Web Apple 登录服务和新上游 API | 019B/C | API contract test |
| `CHAT-WEB-019E` | Chat Web BFF callback 与恢复链路 | 019D | 浏览器 E2E |
| `CHAT-WEB-019F` | Web 对话共享、故障与零改动验收 | 019E | E2E/监控报告 |
| `CHAT-WEB-019G` | WebSocket 鉴权失败重连治理与来源标记 | 019B/E | WS 状态机测试、连接日志与浏览器 E2E |
| `CHAT-WEB-019H` | Web Run readiness、发送门禁与运维启用说明 | 019E | readiness contract、Run 冒烟与故障矩阵 |
| `CHAT-WEB-019I` | Web/Mobile 会话并存与移动全平台单活服务端补强 | 019A/B | 事务竞态测试、跨域不变式报告 |

## 十四、Feature Flag 与发布

当前 Web 开关：

```text
WEB_APPLE_LOGIN_V2_ENABLED
WEB_SESSION_DOMAIN_ENABLED
```

不新增或修改 AI bootstrap、模型、Pro 和移动客户端 Feature Flag。

发布顺序：

1. AccountWebSession、Web Token 和 Web Apple 基础链路保持现有实现。
2. 为移动登录补充 User 级事务串行化和三平台并发测试，Web flag 保持当前灰度范围。
3. 只读验证移动 Apple 服务端公开契约、请求和响应无变化。
4. 验证 Web 登录后 iOS、Android、HarmonyOS 分别登录均不撤销 WebSession。
5. 验证三个移动平台顺序及并发登录后最多一个 ACTIVE AccountDeviceSession。
6. 验证移动替换不影响 Web 对话同步、Run、WS ticket 和 logout。
7. 完成 refresh 重放、并发回滚、JWKS 故障和跨域误撤销演练。

回滚规则：

- Web Apple V2 失败时关闭 Web Apple 按钮或 V2 flag。
- 不允许回退调用移动 Apple API。
- WebSession 回滚不得撤销移动 Session。
- 回滚不得修改任何客户端内容。
- 回滚不得修改 AI config bootstrap 或明文 `api_key`。

## 十五、出口验收

### 15.1 范围门禁

- [ ] 没有 Pro、模型路由、Run Provider 或模型场景改动。
- [ ] `/api/v1/ai/config/bootstrap` 完全不变。
- [ ] bootstrap 继续保持现有明文 `api_key` 字段。
- [ ] 没有任何 iOS、Android 或 HarmonyOS 客户端代码/流程改动。
- [ ] `ai_config/**` 和 `chat_sync/ai_runtime/providers/**` 无本工单 diff。

### 15.2 Web Apple

- [ ] Web Apple 只调用独立上游入口。
- [ ] 移动 Apple 服务端契约和执行流程无变化。
- [ ] Web 校验 Service ID、Return URL、state、nonce、TLS/JWKS 和 code。
- [ ] Web Apple 不创建 TrustedDevice/AccountDeviceSession。
- [ ] Web Apple 失败不回退移动 Apple API。
- [ ] 无法安全关联时不按 email 静默合并。

### 15.3 Web Session

- [ ] Web 与移动 Session 可以同时有效。
- [ ] Web 登录、刷新和退出均不撤销任何移动 Session。
- [ ] iOS、Android 或 HarmonyOS 登录、刷新和相互替换均不撤销 WebSession。
- [ ] 同一 User 的 iOS、Android、HarmonyOS 合计最多一个 ACTIVE AccountDeviceSession。
- [ ] 移动单活不按 platform、bundle ID 或登录方式拆分配额。
- [ ] 三个平台并发登录完成后数据库严格只有一个 ACTIVE 移动会话。
- [ ] 被替换移动 Token 返回既有 `device_session_replaced/revoked` 契约。
- [ ] Web login/refresh/logout 不影响移动 Session。
- [ ] 移动 Session 状态变化不影响 WebSession。
- [ ] WebSession 竞争、重放、撤销和过期状态唯一可解释。

### 15.4 Web 对话

- [ ] Web 和已有账号命中同一 User。
- [ ] Web 读取同一 Thread/Message/Block。
- [ ] 移动 Session 变化后 Web Run、WS 和同步继续有效。
- [ ] Web logout 不删除服务端对话数据。
- [ ] 未创建 Web 私有账号体系或私有对话表。

## 十六、开发前待确认

1. Apple Web Service ID 是否与主 App ID 正确分组，Web subject 是否可命中既有身份。
2. Web authorization code 是否由 SparkService 强制兑换；本工单默认强制。
3. Web-to-Web 是否需要在线上限；本工单默认不限制。
4. WebSession 有效期和“退出所有设备”入口归属。
5. 移动 Apple JWKS 故障由哪张独立工单处理；本工单不处理。

## 十七、WebSocket 重复 `4401/1006` 连接分析与 Web 优化

### 17.1 日志结论

以下日志不是同一个 WebSocket 在服务端内部重复执行，而是客户端在连接被拒绝后不断创建新的连接：

```text
HANDSHAKING /ws/chat/sync/
chat ws token validation failed
chat ws connect rejected unauthenticated
CONNECT /ws/chat/sync/
DISCONNECT /ws/chat/sync/
chat ws disconnected close_code=4401/1006
```

服务端当前执行顺序为：

```text
客户端创建连接
  -> JWTAuthMiddleware 校验 token 失败
  -> scope.user = AnonymousUser
  -> ChatSyncConsumer 临时 accept
  -> 下发 auth.session.invalidated
  -> 主动 close(4401)
  -> 客户端把关闭当作可恢复网络故障
  -> 约 1 秒后重新创建连接
```

因此重复的直接条件有两个：

1. `/ws/chat/sync/` 携带的 token 缺失、过期、格式错误，或所属 Session 已失效。
2. 发起连接的一方没有把鉴权失败识别为终止条件，仍按网络断线策略重连。

`4401` 表示服务端明确拒绝未认证连接；`1006` 是连接一方观察到未完整收到关闭帧时产生的异常关闭状态。两者交替不代表存在两个服务端错误。日志中的 `request_id=-` 仅表示当前 WS 握手没有进入普通 HTTP request-id 日志上下文，不是鉴权失败原因。

### 17.2 当前 Web 路径边界

当前 `chat-web` Run 实时链路使用：

```text
POST /api/v1/ai/chat/ws-tickets/
WS   /ws/chat/runs/?ticket=<一次性短票据>
```

当前 Web 源码没有直接创建 `/ws/chat/sync/`。`/ws/chat/sync/` 是历史消息同步通道，在同仓库相邻移动端工程中存在实现。因此在修改任何逻辑前，必须先确认连接来源；不得因为日志出现于 SparkService 就推断为 Chat Web。

本工单只允许：

- 为 Web 连接增加可辨识但不含密钥的来源字段和诊断日志。
- 检查 Web 是否残留旧 bundle、旧页面、代理层或重复 Provider 创建 `/ws/chat/sync/`。
- 优化 Web 的 `/ws/chat/runs/` 重连状态机。

本工单不允许修改 iOS、Android、HarmonyOS 或其他移动客户端的 `/ws/chat/sync/` 连接、Token 和重试策略。

### 17.3 连接来源确认要求

服务端 WS 日志需要补充以下安全字段：

- `connection_id`：每次握手生成，贯穿 connect/disconnect。
- `path`、`auth_mode`（`ticket` 或 `jwt`）。
- `client_platform`、`client_version`、`origin` 和脱敏后的 `user_agent`。
- `auth_failure_reason`：仅允许枚举值，例如 `missing_token`、`invalid_token`、`expired_token`、`session_revoked`、`ticket_invalid`。
- 认证成功后记录 `user_id`；失败时不得记录原始 token 或 ticket。

Web 创建 `/ws/chat/runs/` 时应附加非鉴权查询参数 `client_platform=web`、`client_version` 和 `connection_id`，服务端仅用于诊断，不参与鉴权。验收时必须用 `connection_id` 证明一次关闭对应一次新的握手，并确认截图中 `/ws/chat/sync/` 的实际来源。

### 17.4 Web 重连状态机

Web Run Socket 必须按关闭原因分流：

| 情形 | Web 行为 | 是否自动重连 |
|---|---|---:|
| `4401`、`auth.session.invalidated` | 终止当前循环，清理短票据；仅允许触发一次 WebSession 恢复 | 否，恢复成功后重新建链一次 |
| 恢复失败或 WebSession 已撤销 | 进入未登录态，关闭发送入口 | 否 |
| `1000` 且 Run 已终态或组件卸载 | 正常结束 | 否 |
| `1006`，且此前已收到鉴权失效事件 | 按鉴权终止处理 | 否 |
| `1006`，无鉴权证据且网络离线 | 切换 REST replay/polling，等待网络恢复 | 有界重连 |
| `1012`/`1013` 或临时网络故障 | 指数退避加随机抖动 | 有界重连 |

有界重连要求：

1. 初始等待不小于 500ms，指数退避，上限 10 秒，并加入随机抖动。
2. 连续失败达到上限后停止自动连接，保留 REST Event replay/polling 降级和“重新连接”按钮。
3. 同一 `run_id` 同一浏览器标签页只允许一个 Socket owner、一个 retry timer。
4. React effect 清理必须关闭旧 Socket 和 timer，防止 Strict Mode、thread 切换或 Run 切换产生重复连接。
5. 每次重连重新申请一次性 ticket；禁止复用已消费或过期 ticket。

当前 `RunControlContext.tsx` 对所有 `onclose` 均重试，未检查 close code，也没有最大尝试次数。本项只要求优化 Web 的 `/ws/chat/runs/`，不把移动同步通道纳入改动范围。

### 17.5 WebSocket 验收用例

- [ ] Web 正常页面不会创建 `/ws/chat/sync/`。
- [ ] 每个进行中的 Run 至多存在一个 `/ws/chat/runs/` 活跃连接。
- [ ] `4401` 后不会出现每秒一次的无限握手。
- [ ] WebSession 可恢复时只恢复一次，并使用新 ticket 建链。
- [ ] WebSession 不可恢复时进入登录态处理，不继续重连。
- [ ] 临时网络中断时 REST replay 不丢事件、不重复投影。
- [ ] 日志可通过 `connection_id` 确认连接来源，且不输出 token/ticket。
- [ ] 没有任何移动客户端文件、流程或测试改动。

## 十八、`50392 chat_server_runs_disabled` 与 Web 对话启用门禁

### 18.1 无法发送的直接原因

请求已经携带 Authorization，并且 Thread、Preferences、Active Run 和 Sync API 均返回 `200`。失败发生在创建 Run 的服务端开关检查：

```text
POST /api/v1/ai/chat/threads/{thread_id}/runs/
-> RunService._ensure_enabled()
-> CHAT_AI_SERVER_RUNS_ENABLED == false
-> HTTP 503 / code 50392 / chat_server_runs_disabled
```

当前代码默认值为：

```text
CHAT_AI_SERVER_RUNS_ENABLED=false
CHAT_AI_RUN_EXECUTOR=disabled
```

所以该错误不是对话内容、`preferences_revision`、模型、Apple 登录或 WebSocket 导致的。浏览器显示“服务端对话尚未开启，请联系管理员”与服务端契约一致，且 `retryable=false` 表示 Web 不应自动重复提交。

### 18.2 执行模式矩阵

| Run 开关 | Executor | 结果 | 用途/结论 |
|---:|---|---|---|
| `false` | 任意 | 创建即返回 `50392` | 当前安全默认值 |
| `true` | `disabled` | Run 可能创建但不会入执行队列 | 禁止部署，容易永久停在 `queued` |
| `true` | `mock` | Celery 执行确定性 Mock，不调用模型 | 仅用于 P1/接口联调 |
| `true` | `provider` | Celery 调用真实 Provider 并写入流式事件 | P2 以后真实文本闭环 |

不得只开启 `CHAT_AI_SERVER_RUNS_ENABLED`。Web 开放发送前，开关与 Executor 必须作为一组原子发布配置校验。

### 18.3 如何开启真实对话（运维执行项，不在本工单中代为执行）

真实文本对话至少满足：

1. 数据库已应用 `chat_sync` AI Run/Event/Outbox 相关 migration。
2. 部署环境显式设置 `CHAT_AI_SERVER_RUNS_ENABLED=true`。
3. 部署环境显式设置 `CHAT_AI_RUN_EXECUTOR=provider`。
4. `chat` 场景存在有效模型绑定，Provider 配置、请求地址和服务端密钥可用。
5. Redis/Celery Broker 可用。
6. Celery Worker 正在消费 `chat.ai` 队列。
7. Event Outbox Worker 正在消费 `chat.events` 队列；Celery Beat 可投递 relay/recovery 定时任务。
8. Recovery Worker 正在消费 `chat.recovery` 队列。
9. SparkService 与 Celery Worker 在配置发布后完成滚动重启，确保读取同一版本配置。
10. 内部账号完成创建 Run、收到 delta、`run.done`、Message/Block 落库和 Event replay 冒烟后，Web 发送入口才可灰度开放。

若只需要验证 REST、幂等和事件契约，可临时使用 `CHAT_AI_RUN_EXECUTOR=mock`；Mock 完成不代表模型已可用，也不能作为真实对话上线证据。本工单只记录启用条件，不修改 `.env`、部署配置、Provider、模型绑定或 Worker 进程。

### 18.4 新增 Web Chat Readiness 契约

为避免 Web 在确定不可用时仍提交 Run，新增不含密钥的只读接口规划：

```http
GET /api/v1/ai/chat/readiness/
Authorization: Bearer <web access token>
```

建议响应：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "can_create_run": false,
    "mode": "disabled",
    "provider_ready": false,
    "broker_ready": false,
    "worker_ready": false,
    "events_ready": false,
    "reason_code": "chat_server_runs_disabled",
    "checked_at": "2026-08-25T14:43:52+08:00"
  }
}
```

约束：

- 不返回 `api_key`、Provider URL、模型密钥、Redis 地址或内部异常堆栈。
- 不复用、不修改 `/api/v1/ai/config/bootstrap`。
- `can_create_run=true` 必须同时满足开关、Executor、Provider route、Broker、`chat.ai` Worker 和 Event 通路就绪。
- Readiness 短暂探测失败不得覆盖登录态；只影响 Web 对话发送能力。
- 服务端应把 `enabled=true + executor=disabled`、Provider 未绑定和 Worker 不在线暴露为不同 `reason_code`，避免“请求成功但永久 queued”。

### 18.5 Web Composer 发送门禁

Web 输入框可编辑与“允许提交 Run”分离。发送按钮只有在以下条件同时满足时启用：

```text
WebSession authenticated
AND thread 已加载且当前用户有权限
AND preferences revision 已同步
AND readiness.can_create_run == true
AND 当前 thread 没有冲突的 active Run
AND 当前未提交相同 client intent
```

状态表现：

| reason_code/状态 | Web 展示 | 自动重试 |
|---|---|---:|
| `chat_server_runs_disabled` | “服务端对话尚未开启，请联系管理员。”，禁用发送 | 否 |
| `chat_run_executor_disabled` | “对话执行器未启用。”，禁用发送 | 否 |
| `chat_provider_not_ready` | “模型服务暂不可用。” | 仅重新探测 readiness，不重提消息 |
| `chat_worker_not_ready` | “对话任务服务暂不可用。” | 仅重新探测 readiness，不重提消息 |
| WS 不可用但 REST/Event 可用 | 显示“实时连接已降级”，允许发送并轮询 | 是，按 WS 有界策略 |
| 创建请求网络结果未知 | 使用原 Idempotency-Key 查询/重放 | 禁止生成新 intent 重复提交 |

收到 `50392` 后，Web 必须保留用户尚未发送成功的输入内容，不创建本地伪 assistant 消息，不无限重试 POST，也不把错误归因于 Apple 登录。

### 18.6 开启与回滚顺序

开启顺序：

1. 保持 Web 发送门禁关闭，完成 migration、Provider、Broker、Worker 和 Event 通路部署。
2. Readiness 通过后，仅对内部账号设置 `can_create_run=true`。
3. 验证单 Run 全链路和重复 Idempotency-Key。
4. 小流量开放 Web Composer，监控 queued 时长、首 delta、终态和失败码。
5. 扩大流量前验证 Worker 重启、Redis 短断和 WS 降级回放。

回滚顺序：

1. 先关闭 Web 发送门禁，停止创建新 Run。
2. 等待或取消已有 Run，保证终态和 Outbox 投递完整。
3. 再关闭服务端 Run 开关或 Provider Executor。
4. 回滚不得切换到客户端直连模型，不得修改 bootstrap 或明文 `api_key`。

### 18.7 Run 启用验收

- [ ] 默认禁用环境稳定返回 `50392`，Web 不重试 POST。
- [ ] `enabled=true + executor=disabled` 被 readiness 阻断，不能静默产生孤儿 queued Run。
- [ ] Mock 模式明确标记为联调，不被计入真实模型验收。
- [ ] Provider 模式中 `chat.ai` Worker 可领取 Run，并持续写入 Event/Block。
- [ ] `chat.events` 故障后可由 Outbox 重放，不丢 `run.done`。
- [ ] Worker 不在线时 Web 在发送前获得明确不可用原因。
- [ ] WS 断开时 REST replay 能恢复完整事件序列。
- [ ] `50392` 场景保留输入内容，且不创建重复用户消息。
- [ ] 全流程没有修改 AI bootstrap、明文 `api_key`、模型选择或移动客户端。

---

工单结论：Chat Web 与移动端属于独立会话域，可以同时在线且互不排挤；同一 User 的 iOS、Android、HarmonyOS 共用一个移动单活名额，后登录成功的移动端替换先登录的移动端，但不得影响任何 WebSession。实现仅允许补强服务端事务一致性与 Web 验收，不修改任何移动客户端内容和流程，也不修改 AI bootstrap、明文 `api_key`、Pro 权益、模型场景和 Provider 路由。
