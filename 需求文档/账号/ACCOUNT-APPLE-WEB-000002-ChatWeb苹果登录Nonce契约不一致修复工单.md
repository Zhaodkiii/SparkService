# ACCOUNT-APPLE-WEB-000002 Chat Web 苹果登录 Nonce 契约不一致修复工单

创建日期：2026-08-27  
关联模块：chat-web、accounts、Apple Web 登录、Next.js BFF、Django、请求日志中间件  
优先级：P0  
当前状态：已实现并发布（2026-08-27）  
需求类型：生产登录故障修复 / OAuth 防重放契约修正 / 敏感日志治理

## 1. 问题摘要

用户在生产环境完成 Apple 授权后，页面返回：

```text
登录会话已失效，请重新发起 Apple 登录。
```

生产日志已确认本次请求不是 Cookie 丢失、state 不一致、回调域名错误或 Apple JWKS 不可用，而是 Chat Web 发起端与 Django 校验端对 nonce 的格式约定不一致。

最终错误：

```text
HTTP 401
code=40171
msg=apple_web_nonce_mismatch
```

## 2. 生产证据

关联请求：

```text
request_id=93540d6f-54ef-47da-aeb1-916310f8ef37
```

### 2.1 Chat Web 回调状态

```text
has_state_cookie=true
has_nonce_cookie=true
has_return_cookie=true
state_matches=true
has_identity_token=true
has_authorization_code=true
```

说明：Apple 回调携带了必要字段，浏览器也带回了本次登录事务的 Cookie。

### 2.2 Django 上游状态

```text
Web Apple 登录接口请求开始
Web Apple 登录鉴权开始
Web Apple 身份令牌校验开始
Web Apple JWKS 拉取成功
HTTP 401 / code=40171 / apple_web_nonce_mismatch
```

说明：请求已经到达 Django，Apple 公钥获取成功，失败发生在 identity token 的 nonce 校验阶段，尚未进入授权码兑换、账户解析和 Web Session 签发。

### 2.3 nonce 实际形态

生产现场确认：

```text
Cookie/BFF 提交的 nonce：原始 UUID
Apple id_token nonce：同一个原始 UUID
Django 期望值：SHA-256(原始 UUID)
```

因此当前比较必然失败：

```text
Apple token nonce == 原始 nonce
后端 expected    == SHA-256(原始 nonce)
```

## 3. 根因

### 3.1 发起端没有执行约定的哈希

`chat-web/app/api/auth/apple/start/route.ts` 当前生成一个原始 nonce，并同时用于 Cookie 和 Apple 授权参数：

```ts
const nonce = randomUUID();
authorize.searchParams.set("nonce", nonce);
store.set(APPLE_NONCE_COOKIE, nonce, transientCookieOptions());
```

Apple 将授权请求中的 nonce 关联到返回的 ID token。当前生产结果显示，Apple 返回的 nonce 与授权请求值一致。

### 3.2 校验端固定要求 SHA-256

`accounts/services/web_apple_identity_service.py` 当前执行：

```python
expected = hashlib.sha256(presented_nonce.encode("utf-8")).hexdigest()
if token_nonce != expected:
    raise APIError("apple_web_nonce_mismatch", code=40171, status_code=401)
```

该实现要求：

```text
Cookie 保存原始 nonce
Apple 授权参数使用 SHA-256(原始 nonce)
Apple id_token 返回 SHA-256(原始 nonce)
BFF 向 Django 提交原始 nonce
Django 对原始 nonce 做 SHA-256 后比较
```

但是 Chat Web 实际没有完成第二步，导致前后端契约断裂。

### 3.3 自动化测试掩盖了问题

`accounts/tests_web_session_and_apple_login.py` 的测试 token 直接把 nonce 生成为 SHA-256 值，因此只验证了后端预期，没有覆盖真实 Chat Web 授权 URL 的 nonce 生成方式。

当前测试缺少以下跨模块断言：

```text
Apple authorize URL 中的 nonce == SHA-256(Cookie 中保存的原始 nonce)
```

## 4. 修复目标

1. Chat Web Apple 登录可以在 Safari 和其他现代浏览器完成授权并建立 Web Session。
2. nonce 继续承担登录事务绑定和防重放作用。
3. nonce 在 Chat Web、Apple 授权请求、Apple ID token 和 Django 之间只有一套明确契约。
4. 不降低 Django 当前严格的 nonce 校验要求。
5. 不影响移动端 Apple 登录流程。
6. 请求日志不得记录完整 Apple identity token、authorization code、nonce、Cookie 或 Web token。

## 5. 非目标

1. 不修改 Apple Services ID：`cn.Zhaodk.Health.web`。
2. 不修改生产回调地址：`https://chat.dreamwhale.top/api/auth/apple/callback`。
3. 不修改移动端 `/api/v1/auth/apple/login/` 的协议。
4. 不修改账号合并、SocialIdentity、Web Session 和移动设备 Session 的业务边界。
5. 不用“同时接受原始 nonce 和哈希 nonce”作为长期兼容方案。

## 6. 修复决策

采用“原始 nonce 仅保存在受保护 Cookie 中，SHA-256 nonce 发给 Apple”的单一协议。

```text
Chat Web 生成 raw_nonce
        │
        ├── HttpOnly Cookie 保存 raw_nonce
        │
        └── Apple authorize 参数发送 SHA-256(raw_nonce)
                                      │
                                      ▼
                         Apple id_token.nonce
                         = SHA-256(raw_nonce)
                                      │
                                      ▼
Callback 从 Cookie 取得 raw_nonce，提交 Django
                                      │
                                      ▼
Django 计算 SHA-256(raw_nonce)，与 token nonce 做恒定时间比较
```

Apple 官方将 nonce 定义为关联客户端会话和 ID token 的值，并在授权请求提供时放入认证结果。本方案把 SHA-256 结果作为发送给 Apple 的关联值，原始 nonce 不离开本站 Cookie 和 BFF 到后端的受控链路。

官方参考：

- https://developer.apple.com/documentation/signinwithapplejs/clientconfigi/nonce
- https://developer.apple.com/documentation/signinwithapple/configuring-your-webpage-for-sign-in-with-apple

## 7. 详细实施方案

### 7.1 Chat Web 发起端

修改：

```text
chat-web/app/api/auth/apple/start/route.ts
```

要求：

1. 使用密码学安全随机值生成原始 nonce。
2. 使用 Node.js `createHash("sha256")` 生成小写十六进制哈希。
3. Cookie 继续保存原始 nonce。
4. Apple authorize URL 的 `nonce` 参数改为哈希值。
5. 日志只记录 `nonce_transform=sha256_hex`，不得记录原始值或哈希值。

参考实现：

```ts
import { createHash, randomUUID } from "node:crypto";

const rawNonce = randomUUID();
const appleNonce = createHash("sha256").update(rawNonce, "utf8").digest("hex");

authorize.searchParams.set("nonce", appleNonce);
store.set(APPLE_NONCE_COOKIE, rawNonce, transientCookieOptions());
```

### 7.2 Chat Web 回调端

检查但不改变协议职责：

```text
chat-web/app/api/auth/apple/callback/route.ts
```

保持：

1. 从 HttpOnly Cookie 读取原始 nonce。
2. 校验 state Cookie 与回调 state。
3. 向 `/api/v1/auth/apple/web/login/` 提交原始 nonce。
4. 成功或失败后清理 state、nonce、return_to Cookie。
5. 所有浏览器跳转继续使用 `SPARK_PUBLIC_WEB_BASE_URL`。

不得在该层自行解码 token 后放宽后端验证。

### 7.3 Django nonce 校验端

修改：

```text
accounts/services/web_apple_identity_service.py
```

保持 SHA-256 契约，并将普通字符串比较调整为恒定时间比较：

```python
import hmac

expected = hashlib.sha256(presented_nonce.encode("utf-8")).hexdigest()
if not hmac.compare_digest(token_nonce, expected):
    raise APIError("apple_web_nonce_mismatch", code=40171, status_code=401)
```

禁止采用以下临时放宽：

```python
token_nonce in {presented_nonce, sha256(presented_nonce)}
```

原因：同时接受两种契约会掩盖发起端回归，使生产行为和测试再次分叉。

### 7.4 敏感日志治理

当前 `common/middleware/request_logging_middleware.py` 默认完整记录普通 API 请求体。生产日志已出现完整 Apple `identity_token` 和一次性 `authorization_code`，必须随本工单修复。

要求：

1. 所有请求头默认脱敏：
   - `Authorization`
   - `Cookie`
   - `Set-Cookie`
   - `X-API-Key`
2. Apple、手机号、刷新令牌、登出等认证接口按字段递归脱敏：
   - `identity_token`
   - `id_token`
   - `authorization_code`
   - `code`
   - `nonce`
   - `access_token`
   - `refresh_token`
   - `token`
   - `password`
3. 错误响应日志不得因为 `status_code >= 400` 再次附加未脱敏的 `request_body`。
4. 保留排查所需的布尔状态、HTTP 状态码、业务码、耗时和 `request_id`。
5. 增加中间件测试，断言日志文本和结构化 extra 中均不存在原始凭证。

建议新增通用函数：

```text
_redact_sensitive_body(value)
_is_sensitive_auth_path(path)
```

不要只针对当前单个 URL 写字符串替换。

## 8. 测试方案

### 8.1 Chat Web 单元测试

新增或修改测试，必须验证：

1. start 接口写入 nonce Cookie。
2. authorize URL 中的 nonce 是 64 位小写十六进制字符串。
3. authorize URL nonce 不等于 Cookie 原始 nonce。
4. `SHA-256(Cookie nonce) == authorize URL nonce`。
5. state 仍原样写入 Cookie 和 authorize URL。
6. callback 向 Django 提交 Cookie 中的原始 nonce。
7. 日志不包含原始 nonce、Apple token 或 authorization code。

### 8.2 Django 单元测试

保留并加强：

1. token nonce 等于 `SHA-256(raw_nonce)` 时通过。
2. token nonce 等于原始 nonce 时返回 `40171`。
3. token nonce 缺失时返回 `40171`。
4. BFF nonce 缺失时返回 `40171`。
5. token nonce 只差一个字符时返回 `40171`。

### 8.3 跨模块契约测试

增加一个固定测试向量：

```text
raw_nonce -> sha256_hex -> authorize nonce -> id_token nonce -> Django verify
```

Chat Web 和 Django 测试必须共享相同输入输出样例，防止两端再次各自通过、组合后失败。

### 8.4 日志测试

针对成功和失败响应分别断言：

```text
日志包含 request_id、status、业务码
日志不包含 identity_token
日志不包含 authorization_code
日志不包含 nonce 原文
日志不包含 Cookie 和 refresh token
```

## 9. 发布步骤

1. 本地运行 Chat Web 测试、类型检查和构建。
2. 本地运行 accounts Apple Web 登录测试及日志中间件测试。
3. 使用现有 `scripts/deploy_sparkservice.sh` 发布。
4. 发布流程重建 `web` 和 `chat_web`；Celery 服务按现有 Compose 流程重建，但本工单不改 Celery 任务。
5. 确认数据库迁移为 `No migrations to apply`；本工单不应生成数据库迁移。
6. 确认 `web`、`chat_web`、`celery_worker`、`celery_beat` 均为运行状态，具有健康检查的容器必须为 `healthy`。

## 10. 生产验收

### 10.1 正常登录

1. 使用无痕窗口打开 `https://chat.dreamwhale.top/login`。
2. 只点击一次 Apple 登录。
3. 在 Apple 页面完成授权。
4. 回调后进入 `/chat`。
5. `/api/auth/session` 返回已登录状态。
6. 页面不再显示“登录会话已失效”。

### 10.2 日志验收

使用同一个 `request_id` 串联日志，预期顺序：

```text
auth.apple.web.start.received
auth.apple.web.start.issued
auth.apple.web.callback.received
auth.apple.web.callback.validated
Web Apple 身份令牌校验成功
Web Apple code 兑换成功
Web Apple 登录鉴权成功并签发 Web 令牌
auth.apple.web.callback.succeeded
```

不得再出现：

```text
code=40171
apple_web_nonce_mismatch
完整 identity_token
完整 authorization_code
完整 nonce
```

### 10.3 回归验收

1. Apple 用户取消授权后仍返回公开登录域名。
2. 重放同一个 callback 时被拒绝。
3. 篡改 state 时被拒绝。
4. 篡改 nonce 时被拒绝。
5. 手机号登录正常。
6. 移动端 Apple 登录正常。
7. Web refresh/logout 正常。

## 11. 回滚方案

若发布后 Apple 登录出现新的大面积故障：

1. 使用 `/root/2026/bin/rollback.sh` 回滚到上一 release。
2. 回滚后保留诊断日志，但不得恢复完整凭证日志。
3. 不得通过关闭 nonce 校验恢复登录。
4. 不得临时接受空 nonce。
5. 记录回滚版本、请求 ID、错误码和时间，继续在预发布环境复现。

## 12. 风险与补充事项

1. 多标签页同时发起 Apple 登录仍可能互相覆盖单组 state/nonce Cookie，这是独立的并发事务设计问题，不应通过放宽 nonce 校验解决。
2. Apple authorization code 是一次性值，验收时每次失败后必须重新从 start 接口发起，不能刷新 callback 页面重试。
3. 生产服务器时间必须准确，否则 token 的 `iat`、`exp` 校验可能产生另一类失败。
4. `SPARK_APPLE_WEB_REDIRECT_URI`、`APPLE_WEB_ALLOWED_REDIRECT_URIS` 和 Apple Developer 后台配置必须完全一致。
5. 当前生产日志曾记录完整 Apple token 和授权码。修复发布后应按日志保留策略清理到期文件，并限制日志目录访问权限。

## 13. 完成定义

本工单只有同时满足以下条件才能标记完成：

- [x] Chat Web start 发送 SHA-256 nonce，Cookie 保存原始 nonce。
- [x] Django 使用 SHA-256 契约和恒定时间比较。
- [x] 前后端契约测试通过。
- [x] 请求日志敏感字段脱敏测试通过。
- [ ] 生产真实 Apple 登录成功（待用户使用真实 Apple 账号验收）。
- [x] 生产日志出现 start 链路和 nonce 转换记录。
- [x] 生产日志不再包含完整 Apple 凭证。
- [ ] 手机号登录和移动端 Apple 登录回归通过（待业务回归验收）。

## 14. 本次落地记录

### 14.1 已修改文件

```text
chat-web/app/api/auth/apple/start/route.ts
chat-web/lib/server/apple-nonce.ts
accounts/services/web_apple_identity_service.py
common/middleware/request_logging_middleware.py
chat-web/tests/apple-nonce.test.ts
common/tests_request_logging_middleware.py
```

### 14.2 已完成验证

```text
Chat Web：27 个测试文件、127 个测试通过
TypeScript：通过
Python 语法检查：通过
日志脱敏单测：2 个通过
服务器 MySQL 迁移：No migrations to apply
chat_web：healthy
web：healthy
生产 Apple start：nonce_transform=sha256_hex
生产认证探针：401，敏感字段全部 <redacted>
```

### 14.3 生产发布版本

```text
发布版本：20260827_034804
服务器：139.196.215.51
运行目录：/root/2026
```
