# CHAT-WEB-020 Web 手机验证码登录与移动会话隔离修复工单

创建日期：2026-08-25  
状态：待实现  
优先级：P0  
阶段归属：Web 对话认证与会话维护  
关联工单：`CHAT-WEB-019 Web Apple 独立登录与会话隔离需求工单`  
关联模块：`accounts`、`chat-web`、`AccountWebSession`、手机验证码登录、Token Refresh  
工单性质：独立缺陷修复需求，不并入 Apple 登录改造  
本次交付边界：只维护本 Markdown 工单，不修改任何业务代码、配置、数据库或客户端文件。

## 一、问题摘要

Chat Web 使用手机验证码登录后，已在线的 iOS 移动会话被服务端标记为 `replaced_by_new_device`。iOS 后续请求先返回 `device_session_replaced`，再调用令牌刷新接口时返回：

```http
POST /api/v1/auth/token/refresh/
HTTP 401

{
  "code": 40102,
  "msg": "token_not_valid"
}
```

这不是 iOS 刷新请求字段缺失，也不是单纯的 Refresh API 解析错误。根因是 Web 手机验证码校验仍进入移动设备会话域，把浏览器当作新移动设备，主动撤销并拉黑了原 iOS 会话的 Refresh JTI。

正确的修复目标是：

```text
Web 登录成功
  → 创建 AccountWebSession
  → 签发 session_class=web 的 Web Token
  → 不读写 AccountDeviceSession / TrustedDevice
  → 原移动会话保持 ACTIVE
  → 原移动 Refresh Token 继续有效
```

## 二、日志证据与事件时间线

### 2.1 可确认的请求来源

2026-08-25 16:33:42，Web BFF 发起手机验证码请求：

```text
POST /api/v1/otp/phone/request/
User-Agent: node
bundle_id: cn.Zhaodk.Health.web
device_id: web-918e452c-...
scene: login
```

`User-Agent: node`、`.web` Service ID 和 `web-*` 设备标识共同证明该请求来自 Chat Web BFF，不是 iOS、Android 或 HarmonyOS。

### 2.2 Web 校验进入移动会话域

2026-08-25 16:33:47，Web BFF 调用现有移动手机 OTP 校验接口：

```text
POST /api/v1/otp/phone/verify/
bundle_id: cn.Zhaodk.Health.web
device_id: web-918e452c-...
```

紧接着服务端记录：

```text
device.session.revoked_on_login
device.session.activated
chat sync device session invalidated session_id=480 reason=replaced_by_new_device
```

返回的 Web Token 实际包含：

```text
device_session_id=481
session_version=1
bundle_id=cn.Zhaodk.Health.web
device_id=web-918e452c-...
```

这说明 Web 手机登录签发的仍是移动设备 Token，而不是已建立的 Web Session Token。

### 2.3 iOS 会话被替换

原 iOS Token 指向：

```text
device_session_id=480
bundle_id=cn.Zhaodk.Health
device_id=680783DA-...
```

Web 手机登录完成后，iOS 调用受保护 API 时返回：

```text
401 / device_session_replaced
```

这是服务端已将 `session_id=480` 标记为 `REVOKED/replaced_by_new_device` 的直接证据。

### 2.4 Refresh 401 是上游会话替换的后果

2026-08-25 16:33:53，iOS 携带 `device_session_id=480` 的原 Refresh Token 请求：

```text
POST /api/v1/auth/token/refresh/
→ 401 / token_not_valid
```

当新设备会话激活时，`DeviceSessionService.activate_session_on_login()` 会：

1. 将旧会话改为 `REVOKED`。
2. 写入 `revoked_reason=replaced_by_new_device`。
3. 将旧会话 `refresh_jti` 加入 SimpleJWT blacklist。
4. 向旧 Chat Sync Session 发送失效通知。

后续 `RefreshToken(provided_refresh)` 在解析阶段即因 JTI 已拉黑而失败，最终被统一映射为 `40102/token_not_valid`。

结论：Refresh 401 是符合当前移动会话替换规则的结果；错误发生在更早的“Web 登录误创建移动会话”。

## 三、根因分析

### 3.1 直接根因

Chat Web 手机验证码 BFF 目前调用通用/移动入口：

```text
/api/v1/otp/phone/request/
/api/v1/otp/phone/verify/
```

`PhoneOTPVerifyView` 调用：

```text
OTPService.verify_phone_otp_and_issue_tokens
  → AccountLoginResolutionService.resolve_verified_identity
  → LoginService._issue_tokens
  → DeviceSessionService.activate_and_issue_tokens
  → DeviceSessionService.activate_session_on_login
```

`DeviceSessionService.activate_session_on_login` 按 User 查找并替换其他 ACTIVE `AccountDeviceSession`。它不应识别 `.web` bundle 特例，因为该 Service 的职责就是维护移动端全平台单活。

### 3.2 架构缺口

`CHAT-WEB-019` 已为 Web Apple 建立：

```text
WebAppleLoginView
  → WebAppleLoginService
  → WebSessionService.create_session
  → WebSessionService.issue_tokens_for_session
```

但 Web 手机验证码登录没有对齐这条会话域分流，仍通过浏览器 `device_id` 进入 `DeviceSessionService`。当前实现只隔离了 Web Apple，没有隔离 Web 手机验证码登录。

### 3.3 不能采用的“假修复”

下列方案禁止实施：

1. 不得让移动 Refresh API 接受已被替换或拉黑的 Token。
2. 不得把 `token_not_valid` 改成 200 或强制签发新 Token。
3. 不得在 `DeviceSessionService` 中根据 bundle ID 字符串判断 `.web` 并跳过替换。
4. 不得根据 `User-Agent: node`、`web-* device_id` 或请求 IP 猜测会话类型。
5. 不得允许同一 User 出现多个 ACTIVE `AccountDeviceSession`。
6. 不得修改 iOS 的 Token 存储、刷新参数、重试或退出流程掩盖服务端错误。
7. 不得在 Web 入口失败后回退调用移动 OTP 校验入口。

## 四、业务目标与强制不变量

### 4.1 最终业务规则

1. Web 登录与移动登录互不排斥，允许同时在线。
2. Web 手机验证码登录只创建 `AccountWebSession`。
3. Web 手机登录不创建、更新或撤销 `TrustedDevice`。
4. Web 手机登录不创建、更新或撤销 `AccountDeviceSession`。
5. Web 登录前已签发的移动 Access/Refresh Token 继续有效。
6. 移动端 iOS、Android、HarmonyOS 之间仍是同一 User 最多一个 ACTIVE 移动会话。
7. 移动端新登录可以替换旧移动会话，但不得撤销 WebSession。
8. Web 与移动登录命中同一 `User` 后，继续共享 Thread、Message、Block、Run 和用户权益。

### 4.2 强制不变量

```text
active_mobile_session_count(user_id) <= 1

Web 手机登录写集合
  ⊆ User + SocialIdentity + PhoneOTP + LoginAudit + AccountWebSession

Web 手机登录写集合
  ∩ (TrustedDevice + AccountDeviceSession + mobile refresh blacklist) = ∅

Web Token claims
  = web_session_id + web_session_version + session_class=web

Web Token claims
  ∩ (device_session_id + device_id + mobile bundle claim) = ∅
```

### 4.3 会话结果矩阵

| 已在线 | 新操作 | 预期结果 |
|---|---|---|
| iOS | Web 手机登录 | iOS 和 Web 同时在线 |
| Android | Web 手机登录 | Android 和 Web 同时在线 |
| HarmonyOS | Web 手机登录 | HarmonyOS 和 Web 同时在线 |
| Web | iOS/Android/HarmonyOS 登录 | Web 不变，新 Mobile 成为唯一 ACTIVE Mobile |
| Web A | Web B 手机登录 | 按现有 WebSession 策略并存 |
| iOS A | Android B 登录 | B 替换 A，所有 WebSession 不变 |
| Android A | HarmonyOS B 登录 | B 替换 A，所有 WebSession 不变 |
| Mobile + Web | Web refresh | 只轮换 WebSession，Mobile 不变 |
| Mobile + Web | Mobile refresh | 只轮换 AccountDeviceSession，Web 不变 |
| Mobile + Web | Web logout | 只撤销当前 WebSession |

## 五、范围与非范围

### 5.1 本工单后续实现范围

1. 新增 Web 专属手机 OTP 请求和校验服务端入口。
2. 复用现有 OTP 校验、账号解析、权益和审计能力。
3. Web 校验成功后仅创建并签发 `AccountWebSession` Token。
4. Chat Web BFF 的手机 OTP route 改调 Web 专属上游入口。
5. 浏览器与 BFF 不再向 Web 手机登录上游传递移动 `device_id`、`device_secret` 或 bundle ID。
6. 增加 Web/Mobile 共存、Refresh 互不影响和禁止移动表写入的自动化测试。
7. 增加渠道级日志、指标、告警与回滚开关。

### 5.2 明确不包含

- 不修改任何 iOS 客户端文件、代码、登录、Token 存储、刷新、退出、WS 或 UI 流程。
- 不修改任何 Android 或 HarmonyOS 客户端内容。
- 不修改移动手机 OTP API 的 URL、DTO、响应、Token claim 和会话替换规则。
- 不修改移动 Apple 登录入口、Apple 验证服务和 JWKS/TLS 流程。
- 不修改 `GET /api/v1/ai/config/bootstrap`。
- 不修改 `bootstrap` 中的 `api_key`，继续保持现有明文返回行为。
- 不修改 Pro 判断、模型列表、模型场景、Provider、Run 或 AI 对话生成流程。
- 不通过改动移动 Refresh 安全策略来接受已拉黑 Token。
- 不增加新的账号合并规则，继续使用现有 `IdentityScopeService` 与 `SocialIdentity`。

## 六、目标架构

```text
Browser
  → Chat Web BFF /api/auth/phone/request
  → SparkService Web Phone OTP request endpoint
  → OTPService.request_phone_otp

Browser
  → Chat Web BFF /api/auth/phone/verify
  → SparkService Web Phone OTP verify endpoint
  → WebPhoneLoginService
      → OTPService: 校验并消费 OTP
      → AccountLoginResolutionService: 解析同一 User/SocialIdentity
      → LoginService: 权益准备与 is_pro 投影
      → WebSessionService.create_session
      → WebSessionService.issue_tokens_for_session
  → BFF 写入 HttpOnly Refresh Cookie
  → Browser 只获得 Access Token

移动端原链路保持不变：

/api/v1/otp/phone/verify/
  → OTPService.verify_phone_otp_and_issue_tokens
  → AccountLoginResolutionService
  → LoginService._issue_tokens
  → DeviceSessionService.activate_and_issue_tokens
```

分流依据必须是独立服务端入口和明确的 Token issuer，不能依赖可伪造字段。

## 七、服务端 API 契约

### 7.1 新增 Web 手机 OTP 请求入口

```http
POST /api/v1/auth/phone/web/otp/request/
Content-Type: application/json
X-Request-ID: <request-id>
```

请求：

```json
{
  "phone_number": "+8613800138000",
  "scene": "login"
}
```

成功响应：

```json
{
  "code": 0,
  "msg": "otp_sent",
  "data": {
    "otp_id": "uuid",
    "expires_in": 300
  }
}
```

约束：

- 只接受 `scene=login`。
- 不接受 `bundle_id`、`device_id`、`device_secret`、`user_id`。
- Web Service ID 由 SparkService 服务端配置决定，不信任浏览器或 BFF 传入值。
- 复用现有发送、频率限制、黑名单、白名单、过期和审计能力。

### 7.2 新增 Web 手机 OTP 校验入口

```http
POST /api/v1/auth/phone/web/otp/verify/
Content-Type: application/json
X-Request-ID: <request-id>
```

请求：

```json
{
  "otp_id": "uuid",
  "phone_number": "+8613800138000",
  "code": "123456"
}
```

成功响应与现有账号登录摘要兼容，但 Token 必须属于 Web 会话域：

```json
{
  "code": 0,
  "msg": "otp_verified",
  "data": {
    "user_id": 265,
    "access_token": "<web-access-token>",
    "refresh_token": "<web-refresh-token>",
    "expires_in": 1799,
    "token_type": "Bearer",
    "session_class": "web",
    "is_pro": true,
    "is_new_user": false,
    "sign_in_method": "phone",
    "is_device_account": false,
    "account_resolution": "existing_identity_login",
    "identity_scope": "cn.Zhaodk.Health"
  }
}
```

强制 Token claim：

```json
{
  "session_class": "web",
  "web_session_id": "uuid",
  "web_session_version": 1
}
```

禁止 Token claim：

```text
device_session_id
device_id
mobile bundle_id
```

### 7.3 刷新入口

对外刷新 URL 不需新增第二套：

```http
POST /api/v1/auth/token/refresh/
```

现有 `TokenRefreshView` 已能按 Token claim 分派：

- `session_class=web + web_session_id` → `WebSessionService`。
- `device_session_id` → `DeviceSessionService`。

本工单的关键是让 Web 手机登录首次签发正确的 Web Token。只要 Token 域正确，后续 Web refresh 会自然进入 `WebSessionService`，不会查询或替换移动 Session。

### 7.4 错误契约

| HTTP/code | msg | 场景 | 处理 |
|---|---|---|---|
| 400/40041 | `OTP already used` | OTP 已消费 | 重新获取 |
| 400/40042 | `OTP expired` | OTP 过期 | 重新获取 |
| 400/40043 | `Invalid OTP` | 验证码错误 | 允许在剩余次数内重试 |
| 400/40044 | `bundle_id mismatch` | OTP 不属于 Web Service ID | 拒绝 |
| 400/40045 | `OTP unavailable` | OTP 已失效 | 重新获取 |
| 400/40046 | `OTP SMS not sent` | 短信未成功提交 | 重新获取 |
| 423/42311 | `OTP temporarily locked` | 尝试超限 | 等待解锁 |
| 429/42901 | OTP 频率限制 | 发送过频 | 显示可重试时间 |
| 503/50373 | `web_session_store_unavailable` | WebSession 存储不可用 | 登录失败，不回退移动入口 |
| 503/待分配 | `web_phone_login_disabled` | 独立入口开关未开 | 显示服务暂不可用 |

错误响应不得返回原 OTP、Token、手机号明文、Session ID 或内部堆栈。

## 八、核心业务逻辑

### 8.1 共用“已验证身份解析”，分离“会话签发”

当前 `AccountLoginResolutionService.resolve_verified_identity()` 在账号解析末尾固定调用 `LoginService._issue_tokens()`，而该方法固定进入 `DeviceSessionService`。

落地时应引入明确的 Token/Session issuer 注入点：

```python
resolve_verified_identity(
    ...,
    token_issuer=mobile_token_issuer,  # 移动入口的现有默认行为
)
```

Web 手机登录传入：

```python
def web_token_issuer(user):
    web_session = WebSessionService.create_session(
        user=user,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
    )
    tokens = WebSessionService.issue_tokens_for_session(
        user=user,
        session=web_session,
    )
    return {**tokens, "session_class": "web"}
```

移动入口不传入 issuer 时，必须保持与当前完全相同：

```python
LoginService._issue_tokens(
    user,
    bundle_id=real_bundle,
    device_id=normalized_device_id,
    request_id=request_id,
)
```

该注入点必须是服务端内部可调用对象，不得从 HTTP 请求接收 issuer 名称或 `session_class`。

### 8.2 OTP 消费与会话创建必须同一事务

```text
select_for_update(PhoneOTP)
  → 校验手机号/bundle/状态/过期/尝试次数/验证码
  → otp.used_at = now
  → 解析或创建 User/SocialIdentity
  → 准备权益与 is_pro
  → 创建 AccountWebSession
  → 签发 Web Token
  → 提交事务
```

如果 WebSession 创建或 Token 签发失败，整个事务必须回滚，OTP 不应出现“已消费但用户未登录”的半成功状态。

### 8.3 Web 账号解析

1. Web Service ID 必须通过 `ACCOUNT_IDENTITY_SCOPE_ALIASES` 映射至移动主身份作用域。
2. 同一手机号已存在 `SocialIdentity(provider=phone)` 时，Web 登录同一 User。
3. 不得因 `.web` Service ID 创建第二个账号身份孤岛。
4. Web 入口不接收 `device_secret`，不执行设备账号升级逻辑。
5. 首次 Web 正式身份可按现有规则创建 User/SocialIdentity，但不得创建移动 Session。
6. 账号封禁、注销冻结和 AccessControl 仍必须在创建 WebSession 前通过。

### 8.4 Refresh 核心逻辑

Web 手机登录后签发的 Refresh Token 使用现有 Web 分派：

```python
claims = verified_refresh_claims(refresh_token)

if claims contain both web_session_id and device_session_id:
    reject token_session_class_conflict
elif claims require web session:
    validate AccountWebSession
    rotate Web Token
elif claims require device session:
    validate AccountDeviceSession
    rotate Mobile Token
else:
    follow existing legacy-token policy
```

修复后的移动 Refresh 成功不是因为放宽了刷新校验，而是因为 Web 登录没有再撤销和拉黑原移动会话。

## 九、文件级改动规划

> 本节是后续实现指引，本次只写入工单，不对以下文件执行任何修改。

### 9.1 服务端必须改动

| 文件 | 改动方向 | 关键约束 |
|---|---|---|
| `accounts/auth/serializers.py` | 新增 Web Phone OTP request/verify Serializer | 拒绝 `bundle_id/device_id/device_secret/user_id`，只接受 Web 字段 |
| `accounts/auth/views.py` | 新增 Web Phone OTP Request/Verify View | 使用固定 Web Service ID，调用 Web 专属 Service，不调移动 View |
| `accounts/urls.py` | 注册 `/auth/phone/web/otp/request/` 与 `/verify/` | 保留现有 `/otp/phone/*` 不变 |
| `accounts/services/web_phone_login_service.py` | 新建 Web 手机 OTP 登录编排 | 只签发 WebSession Token，禁止 import/call `DeviceSessionService` |
| `accounts/services/otp_service.py` | 抽取可共用的 OTP 校验与账号解析流程 | 旧 `verify_phone_otp_and_issue_tokens` 作为移动兼容外壳，输入输出不变 |
| `accounts/services/account_login_resolution_service.py` | 增加服务端内部 Token issuer 注入点 | 默认仍调移动 `LoginService._issue_tokens`，不允许 HTTP 选择 issuer |
| `SparkService/settings.py` | 新增 Web Phone OTP 开关和服务端固定 Service ID | 不修改 AI config bootstrap、Apple 移动配置或 JWT 移动策略 |
| `accounts/tests_web_phone_login_session.py` | 新建服务端 Web Phone 隔离测试 | 覆盖数据库写集合、Token claim、共存和 Refresh |

### 9.2 Chat Web 必须改动

| 文件 | 改动方向 | 关键约束 |
|---|---|---|
| `chat-web/app/api/auth/phone/request/route.ts` | 上游改调 Web Phone OTP request API | 不再传 `bundle_id/device_id` |
| `chat-web/app/api/auth/phone/verify/route.ts` | 上游改调 Web Phone OTP verify API | 只在 BFF 保存 Refresh HttpOnly Cookie，不回退移动 API |
| `chat-web/app/(auth)/login/phone/page.tsx` | 停止生成和提交浏览器移动 `device_id` | 页面交互、验证码倒计时和错误展示保持现状 |
| `chat-web/types/auth.ts` | 将 Web Phone DTO 与移动 DTO 语义分离 | Web DTO 不包含 bundle/device 字段 |
| `chat-web/lib/api/auth-api.ts` | 对齐 Web Phone DTO 与 BFF 路由 | 不修改 `/api/auth/bootstrap` 的现有 Web refresh 语义 |
| `chat-web/tests/phone-auth.test.ts` | 增加 Web DTO、错误和禁止设备字段测试 | 不依赖真实短信服务 |
| `chat-web/tests/web-phone-session-isolation.test.ts` | 新建 BFF 上游路由与 Cookie 测试 | 断言只调 Web 专属上游，响应不暴露 Refresh Token |

### 9.3 只验证、原则上不需改动

| 文件 | 原因 |
|---|---|
| `accounts/models.py` | `AccountWebSession` 已存在，本工单不需新会话表 |
| `accounts/migrations/0016_account_web_session.py` | 复用已有迁移；本工单预期不产生新 migration |
| `accounts/services/web_session_service.py` | 已具备 Web Session 创建、签发、刷新和退出能力，作为直接复用依赖 |
| `accounts/auth/web_tokens.py` | 已定义 Web Token claim，直接复用 |
| `accounts/auth/views.py::TokenRefreshView` | 已按 Web/Mobile claim 分派；只增加回归测试，不通过放宽刷新规则修复 |
| `accounts/services/device_session_service.py` | 移动端全平台单活逻辑正确，禁止增加 `.web` 特例 |
| `accounts/otp/views.py` | 现有移动 OTP View 保持不变；Web 使用新 View |
| `accounts/otp/serializers.py` | 现有移动 DTO 保持不变；Web Serializer 放在 `accounts/auth/serializers.py` |
| `chat-web/app/api/auth/bootstrap/route.ts` | 现有 Web Token refresh 分派可复用，本工单不修改 |

### 9.4 禁止改动

```text
任何 iOS 工程目录
任何 Android 工程目录
任何 HarmonyOS 工程目录
ai_config/
chat_sync/ai_runtime/providers/
GET /api/v1/ai/config/bootstrap 及其 Serializer/Service
移动 Apple Identity/JWKS 实现
```

## 十、服务端核心代码轮廓

> 以下是工单中的伪代码契约，不是本次实际代码修改。

### 10.1 Web Request View

```python
class WebPhoneOTPRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        require_feature("WEB_PHONE_OTP_LOGIN_ENABLED")
        dto = WebPhoneOTPRequestSerializer(data=request.data)
        dto.is_valid(raise_exception=True)

        result = OTPService.request_phone_otp(
            phone_number=dto.validated_data["phone_number"],
            provider_uid="",
            bundle_id=settings.WEB_AUTH_SERVICE_ID,
            device_id="",
            ip_address=request_ip(request),
            request_id=request.request_id,
            scene="login",
        )
        return success_response(result, msg="otp_sent")
```

### 10.2 Web Verify Service

```python
class WebPhoneLoginService:
    @staticmethod
    @transaction.atomic
    def verify_and_issue_tokens(*, otp_id, phone_number, code,
                                ip_address, user_agent, request_id):
        def issue_web_tokens(user):
            session = WebSessionService.create_session(
                user=user,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
            return {
                **WebSessionService.issue_tokens_for_session(
                    user=user,
                    session=session,
                ),
                "session_class": "web",
            }

        return OTPService.verify_phone_otp_and_resolve_account(
            otp_id=otp_id,
            phone_number=phone_number,
            code=code,
            bundle_id=settings.WEB_AUTH_SERVICE_ID,
            device_id="",
            device_secret="",
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            token_issuer=issue_web_tokens,
            audit_claims={"channel": "web", "session_class": "web"},
        )
```

### 10.3 移动兼容外壳

```python
def verify_phone_otp_and_issue_tokens(...):
    # 原移动 API 继续调用原默认 issuer。
    return verify_phone_otp_and_resolve_account(
        ...,
        token_issuer=None,
    )
```

`token_issuer=None` 时必须继续调用 `LoginService._issue_tokens()`，以确保 iOS、Android、HarmonyOS 的请求与响应完全不变。

### 10.4 BFF 核心转发

```typescript
// /api/auth/phone/verify
const result = await callSparkUpstream(
  "/api/v1/auth/phone/web/otp/verify/",
  {
    method: "POST",
    body: JSON.stringify({ otp_id, phone_number, code }),
  },
  requestId,
);

// Refresh Token 只写 HttpOnly Cookie，不暴露给浏览器 JS。
cookieStore.set(REFRESH_COOKIE, data.refresh_token, refreshCookieOptions());
return jsonEnvelope(stripRefreshToken(result.body));
```

## 十一、数据与事务要求

### 11.1 不新增数据表

本工单复用：

```text
PhoneOTP
User
SocialIdentity
LoginAudit
AccountWebSession
```

不应新增 `WebPhoneSession`、`BrowserDevice`、`WebTrustedDevice` 或第二套 Refresh Token 表。

### 11.2 数据写入断言

Web 手机登录前后必须断言：

```text
AccountDeviceSession 记录数：不变
AccountDeviceSession.status/session_version/refresh_jti：不变
TrustedDevice 记录数与 is_revoked：不变
旧移动 Refresh JTI blacklist 状态：不变
AccountWebSession ACTIVE 数：+1
PhoneOTP.used_at：成功时写入
LoginAudit.raw_claims.channel：web
```

### 11.3 并发要求

- 同一 OTP 并发校验只能一次成功。
- 失败的并发请求不能创建额外 WebSession。
- WebSession 创建失败时回滚 OTP 消费和本次账号变更。
- Web 登录事务不锁定或更新 `AccountDeviceSession`。
- 移动登录事务不锁定或更新 `AccountWebSession`。

## 十二、测试方案

### 12.1 服务单元测试

1. Web Phone request 强制使用服务端 Web Service ID。
2. Web Serializer 拒绝 `bundle_id`、`device_id`、`device_secret`、`user_id`。
3. 正确 OTP 命中已有手机身份的同一 User。
4. Web Phone 成功创建一条 ACTIVE `AccountWebSession`。
5. Web Phone 不创建 `TrustedDevice` 和 `AccountDeviceSession`。
6. Web Token 只含 Web claim，不含移动 claim。
7. Web refresh 成功时只增加 `web_session_version`。
8. Web logout 只撤销当前 WebSession。
9. OTP 错误、过期、重放、锁定和 bundle 不匹配沿用现有错误。
10. WebSession 存储失败时不回退调用移动 Token issuer。

### 12.2 Web/Mobile 隔离回归测试

准备一个 User 和一条 ACTIVE 移动会话 A：

```text
A.id = mobile_session_id
A.status = ACTIVE
A.refresh_jti = mobile_refresh_jti
```

执行 Web 手机验证码登录后必须断言：

1. A 仍是 ACTIVE。
2. A.session_version 不变。
3. A.refresh_jti 不变。
4. A.trusted_device.is_revoked 仍为 false。
5. 未发布 `replaced_by_new_device` 失效事件。
6. 原 iOS Access Token 调用受保护 API 成功。
7. 原 iOS Refresh Token 调用 `/api/v1/auth/token/refresh/` 成功。
8. Web Refresh Token 调用同一 Refresh API 成功。
9. Web refresh 后 A 仍不变。
10. 后续 Android/HarmonyOS 移动登录只按移动单活规则替换 A，WebSession 不变。

### 12.3 移动兼容回归

对现有移动入口执行原有测试：

```text
POST /api/v1/otp/phone/request/
POST /api/v1/otp/phone/verify/
POST /api/v1/auth/token/refresh/
```

必须保持：

- 请求 DTO 不变。
- 成功响应字段不变。
- `device_session_id/session_version/bundle_id/device_id` claim 不变。
- 第二个移动设备仍会替换第一个。
- 旧移动 Access/Refresh Token 仍被拒绝。
- 无需修改任何移动客户端。

### 12.4 Chat Web BFF 测试

1. Browser 请求中带入的 bundle/device 字段不转发上游。
2. BFF request route 只调 Web request endpoint。
3. BFF verify route 只调 Web verify endpoint。
4. Web 上游失败不回退移动 endpoint。
5. Refresh Token 只写入 Secure/HttpOnly/SameSite Cookie。
6. 浏览器响应不含 `refresh_token`。
7. `X-Request-ID` 从 Browser 穿透 BFF 与 SparkService。
8. 成功后 AuthContext 仍能进入 `/chat`，不需 UI 重构。

### 12.5 端到端验收用例

```text
前置：iOS 用户 U 已登录，保留可用 Access/Refresh Token。

1. Web 使用 U 的手机号获取 OTP。
2. Web 校验 OTP 并进入对话页。
3. Web 能读取 U 的同一套 Thread/Message。
4. iOS 继续调用 nutrition/tasks/chat sync API，不出现 device_session_replaced。
5. iOS 刷新 Token 成功。
6. Web 刷新 Token 成功。
7. Web 退出。
8. iOS 仍在线且可刷新。
```

## 十三、可观测性与安全

### 13.1 日志事件

新增或固化以下 action：

```text
auth.phone_otp.web.request.begin
auth.phone_otp.web.request.success
auth.phone_otp.web.request.failed
auth.phone_otp.web.verify.begin
auth.phone_otp.web.verify.success
auth.phone_otp.web.verify.failed
web.session.created
auth.token.refresh session_class=web
```

成功日志应包含：

```text
request_id
user_id
channel=web
session_class=web
web_session_id_tail
identity_scope
account_resolution
duration_ms
```

不得记录：

```text
OTP code
Access Token
Refresh Token
手机号明文
原始 Cookie
device_secret
```

### 13.2 指标与告警

```text
web_phone_otp_request_total{outcome}
web_phone_otp_verify_total{outcome,error_code}
web_phone_login_session_created_total{session_class}
web_phone_login_mobile_session_mutation_total
auth_refresh_total{session_class,outcome,error_code}
```

强制告警：

- `web_phone_login_mobile_session_mutation_total > 0`：立即 P0 告警并回滚 Web Phone 入口。
- Web Phone 登录后 60 秒内同 User 出现 `device_session_replaced`：聚合告警。
- Web Phone verify 成功但没有 `session_class=web`：契约告警。
- Web Phone 签发 Token 含 `device_session_id`：阻断发布。

### 13.3 安全要求

1. Web Phone 入口仍执行 AccessControl、OTP 频率限制、尝试锁定和审计。
2. 不允许 Browser 指定身份作用域或 Token issuer。
3. Web Service ID 只来自服务端配置。
4. BFF Refresh Cookie 保持 `HttpOnly`、`Secure`、合适的 `SameSite`、明确 `Path`。
5. BFF 响应设置 `Cache-Control: no-store`。
6. 不把服务端 Refresh Token 返回给浏览器 JavaScript。

## 十四、配置、灰度与回滚

### 14.1 建议配置

```text
WEB_PHONE_OTP_LOGIN_ENABLED=false
WEB_AUTH_SERVICE_ID=cn.Zhaodk.Health.web
ACCOUNT_IDENTITY_SCOPE_ALIASES={"cn.Zhaodk.Health.web":"cn.Zhaodk.Health"}
```

要求：

- 正式环境在迁移 `0016_account_web_session` 完成后才能开启。
- 开关未开启时明确返回“Web 手机登录未开启”，不允许 BFF 回退调用移动 OTP verify。
- 配置校验必须确认 Web Service ID 存在身份作用域映射。
- 本工单不修改 SimpleJWT 有效期和移动 Refresh 轮换策略。

### 14.2 发布顺序

1. 确认 `AccountWebSession` 迁移已部署。
2. 部署服务端 Web Phone 新入口，开关保持关闭。
3. 执行服务端契约、隔离、移动回归和并发测试。
4. 部署 Chat Web BFF 新上游路由。
5. 在测试环境开启 Web Phone 开关并执行真实手机登录。
6. 灰度 Web 流量，观察移动 Session 变更指标。
7. 全量开启。

### 14.3 回滚

如果 Web Phone 新入口出现账号解析、Session 或 Refresh 故障：

1. 关闭 `WEB_PHONE_OTP_LOGIN_ENABLED`。
2. Web 登录页临时禁用手机登录入口并显示可重试提示。
3. 保留已签发的 WebSession 按现有 refresh/logout 流程自然运行。
4. 不得回退到 `/api/v1/otp/phone/verify/` 作为 Web 登录备用路径。
5. 不得撤销、重签或清空任何移动 Session。

## 十五、实施子工单

### CHAT-WEB-020A：契约与开关

- 固化 Web Phone request/verify DTO、错误码和服务端 Service ID。
- 新增默认关闭的 Web Phone 功能开关。
- 增加“禁止移动字段”Serializer 测试。

### CHAT-WEB-020B：账号解析与 issuer 解耦

- 抽取 OTP 校验/账号解析共享核心。
- 为 `AccountLoginResolutionService` 增加内部 issuer 注入点。
- 固化移动默认 issuer 回归。

### CHAT-WEB-020C：Web Phone Service 与 API

- 新增 `WebPhoneLoginService`。
- 新增 Web request/verify View 和 URL。
- 创建 WebSession，签发 Web Token。

### CHAT-WEB-020D：Chat Web BFF 切换

- BFF 两个 Phone route 切换至 Web 专属上游。
- 移除 Web Phone DTO 的 bundle/device 字段。
- 保持 Refresh Cookie 只在 BFF。

### CHAT-WEB-020E：隔离回归与端到端验收

- 执行 iOS + Web、Android + Web、HarmonyOS + Web 共存矩阵。
- 验证 Web/Mobile 双向 Refresh 互不影响。
- 验证移动端之间仍维持单活。

## 十六、完成定义

只有同时满足以下条件，本工单才能标记为完成：

- [ ] Web 手机登录不再调用 `/api/v1/otp/phone/verify/`。
- [ ] Web 手机登录只调用 Web 专属 OTP 入口。
- [ ] Web 请求不再携带移动 bundle/device 字段。
- [ ] Web 登录只创建 `AccountWebSession`。
- [ ] Web Token 含 `session_class=web`、`web_session_id`、`web_session_version`。
- [ ] Web Token 不含 `device_session_id/device_id/mobile bundle_id`。
- [ ] Web 登录前后原移动 Session 仍是 ACTIVE。
- [ ] Web 登录后原移动 Refresh Token 刷新成功。
- [ ] Web Refresh 成功且不更新移动 Session。
- [ ] Web logout 不影响移动 Session。
- [ ] iOS、Android、HarmonyOS 之间仍最多一个 ACTIVE Mobile Session。
- [ ] 现有移动 OTP 入口、DTO、Token claim、Refresh 和单活测试全部通过。
- [ ] 无 iOS、Android、HarmonyOS 代码 diff。
- [ ] 无 `ai_config` 和 `/api/v1/ai/config/bootstrap` 代码 diff。
- [ ] 无明文 `api_key`、Pro、模型场景或 AI Run 逻辑变更。
- [ ] 日志和响应不暴露 OTP、Token、Cookie 或手机号明文。

## 十七、发布门禁

任一条不满足均禁止发布：

1. Web 登录仍出现 `device.session.activated` 或 `device.session.revoked_on_login`。
2. Web Phone Token 仍包含 `device_session_id`。
3. Web 登录后移动端出现 `device_session_replaced`。
4. Web 登录后原移动 Refresh Token 返回 `token_not_valid`。
5. Web 上游失败时存在移动 OTP API fallback。
6. 移动端之间出现两个 ACTIVE `AccountDeviceSession`。
7. 需要修改移动客户端才能通过验收。
8. 未完成移动登录与 Refresh 回归测试。
9. 实现修改了 AI config bootstrap、明文 `api_key`、Pro 或模型配置。

## 十八、最终结论

本问题已由日志完整定位：Web 手机验证码校验仍使用移动会话 Token issuer，导致浏览器登录被当作“新移动设备登录”，原移动 Session 被替换和 Refresh JTI 被拉黑。

后续实现应对齐 `CHAT-WEB-019` 已建立的 WebSession 域：共用 OTP、User、SocialIdentity、权益和审计，但在会话签发点与移动端分流。不需且不允许修改任何移动客户端，也不应通过放宽 Refresh Token 校验来规避根因。
