# ACCOUNT-APPLE-WEB-000001 Chat Web 苹果登录回调域名错误修复工单

创建日期：2026-08-27  
关联模块：chat-web、Apple Web 登录、Next.js BFF、Nginx 反向代理、Docker Compose、账号登录  
优先级：P0  
需求类型：生产登录故障修复 / OAuth 回调域名治理 / 反向代理配置修正

## 1. 背景

生产登录页面：

```text
https://chat.dreamwhale.top/login
```

用户点击“使用 Apple 登录”后，可以正常跳转到 Apple 授权页面；Apple 授权返回后，浏览器被重定向到：

```text
https://0.0.0.0:9001/login?error=apple_web_nonce_mismatch
```

Safari 报错：

```text
不允许使用受限制的网络端口
```

该地址不是公网业务域名，也不是用户可访问地址。`0.0.0.0:9001` 只是服务器内 `chat_web` Next.js 容器的监听地址，不能出现在浏览器跳转 URL 中。

## 2. 现场结论

当前已确认：

1. 服务器 `.deploy.env` 中 Apple Web 回调地址是正确的：

```text
SPARK_APPLE_WEB_REDIRECT_URI=https://chat.dreamwhale.top/api/auth/apple/callback
APPLE_WEB_ALLOWED_REDIRECT_URIS=https://chat.dreamwhale.top/api/auth/apple/callback
SPARK_WEB_SERVICE_ID=cn.Zhaodk.Health.web
CHAT_WEB_PORT=9001
```

2. Apple 授权开始接口返回的 `authorization_url` 也使用了正确公网回调：

```text
redirect_uri=https://chat.dreamwhale.top/api/auth/apple/callback
```

3. 问题发生在 Apple 回调进入 `chat-web` 后，`chat-web` 生成失败跳转地址时使用了错误 origin：

```text
Location: https://0.0.0.0:9001/login?error=apple_web_transaction_replayed
```

4. `chat-web` 容器运行日志显示 Next.js standalone 当前监听信息：

```text
Local:   http://localhost:9001
Network: http://0.0.0.0:9001
```

该监听地址被错误用于浏览器重定向，说明应用层或代理层没有可靠固定“公网访问 Origin”。

## 3. 根因分析

### 3.1 直接原因

`chat-web/app/api/auth/apple/callback/route.ts` 在处理回调时使用：

```ts
const origin = new URL(request.url).origin;
```

随后失败时通过：

```ts
NextResponse.redirect(new URL("/login", origin))
```

生成跳转地址。

在生产反代环境中，Next.js standalone 收到的请求 URL 被推断成了自身监听地址：

```text
https://0.0.0.0:9001
```

因此失败跳转被拼成：

```text
https://0.0.0.0:9001/login?error=...
```

### 3.2 深层原因

当前实现把“公网站点 Origin”隐式依赖在 `request.url` 上。这个做法在本地直连开发时通常可用，但在生产环境存在风险：

1. 生产请求经过 Nginx 反向代理，Next.js 看到的 URL 可能来自内部监听地址。
2. Nginx 当前虽传递了 `Host` 和 `X-Forwarded-Proto`，但对 Next.js standalone 来说不一定足以稳定还原公网 origin。
3. 应用没有配置明确的公网 Web Base URL 作为 OAuth 回调后的重定向兜底。
4. Apple OAuth 是跨站 `form_post` 回调，Cookie、SameSite、Secure、Host、Origin、代理头任何一处不稳定都会导致 state/nonce 校验失败或错误跳转。

### 3.3 `apple_web_nonce_mismatch` 的含义

`apple_web_nonce_mismatch` 表示服务端收到 Apple 回调后，校验登录会话时发现 nonce 不一致或上游 Apple Web 登录校验失败。

它可能由以下情况触发：

1. 用户不是从同一个浏览器会话发起和完成 Apple 登录。
2. Apple 回调时 `__Host-spark_apple_nonce` Cookie 未被带回。
3. Cookie 域、Secure、SameSite 或反代 HTTPS 判断异常。
4. 服务端转发到 Django 后，Django 校验 `id_token.nonce` 与 BFF 保存的 nonce 不一致。
5. 重复提交、返回按钮、刷新 Apple 回调页导致一次性 state/nonce 已消费。

本次最明显的问题是错误重定向域名。即使 nonce 本身还有独立问题，也必须先修复公网 Origin，避免错误页跳到 `0.0.0.0:9001`。

## 4. 目标

1. Apple 授权成功后，只能跳转到 `https://chat.dreamwhale.top/...` 下的页面。
2. Apple 授权失败、取消、nonce mismatch、transaction replay 等错误场景，也只能跳转到 `https://chat.dreamwhale.top/login?error=...`。
3. 任何对浏览器可见的重定向地址都不能出现：

```text
0.0.0.0
127.0.0.1
localhost
:9001
http://chat.dreamwhale.top
```

4. Nginx 反代头、Docker 环境变量、Next.js BFF 生成 URL 的规则必须统一。
5. 修复后补充自动化测试，覆盖反代环境下的 Apple callback 重定向。

## 5. 非目标

1. 本工单不重做 Apple 登录整体业务。
2. 本工单不修改移动端 Apple 登录。
3. 本工单不改变 `SPARK_WEB_SERVICE_ID=cn.Zhaodk.Health.web`。
4. 本工单不改变手机号登录、设备登录、Web Session 的业务模型。
5. 本工单不处理 Apple 开发者后台证书、Key ID、Team ID 的申请流程，除非验收发现配置缺失。

## 6. 影响范围

| 位置 | 当前职责 | 本工单影响 |
|---|---|---|
| `chat-web/app/api/auth/apple/start/route.ts` | 生成 Apple 授权 URL，写入 state/nonce/return_to Cookie | 检查授权 URL 和 Cookie 的公网域一致性 |
| `chat-web/app/api/auth/apple/callback/route.ts` | 消费 Apple form_post 回调，调用 Django Web Apple 登录接口，设置 Web refresh Cookie | 修复 redirect origin 来源，禁止使用内部监听地址 |
| `chat-web/lib/server/auth-cookies.ts` | Web refresh、Apple state、nonce、return Cookie 配置 | 检查 `__Host-*` Cookie 与 `SameSite=None/Secure` 是否符合跨站回调 |
| `/root/2026/.deploy.env` | 生产环境变量 | 增加或确认公网 base URL 配置 |
| `/root/2026/docker-compose.yml` | `chat_web` 容器环境变量与监听配置 | 给 `chat_web` 注入公网 base URL |
| `/etc/nginx/nginx.conf` | `chat.dreamwhale.top` 反代 | 补全 `X-Forwarded-Host`、`X-Forwarded-Port` 等代理头 |
| `SparkService/accounts` | Django Web Apple 登录上游校验 | 排查 nonce mismatch 是否来自 Django 上游校验 |
| `README.md` / 2026 运维文档 | 服务器部署说明 | 更新 chat-web 路由规则，避免文档误导 |

## 7. 推荐方案

### 7.1 应用层固定公网 Origin

新增明确环境变量：

```text
SPARK_PUBLIC_WEB_BASE_URL=https://chat.dreamwhale.top
```

`chat-web` 所有对浏览器可见的绝对重定向 URL 优先使用该变量。

推荐封装统一函数：

```ts
function publicWebOrigin(request: Request) {
  const configured = process.env.SPARK_PUBLIC_WEB_BASE_URL;
  if (configured) return new URL(configured).origin;
  return new URL(request.url).origin;
}
```

然后 `apple/callback` 中不再直接使用：

```ts
new URL(request.url).origin
```

而是使用：

```ts
publicWebOrigin(request)
```

要求：

1. `SPARK_PUBLIC_WEB_BASE_URL` 必须是 `https://chat.dreamwhale.top`。
2. 配置值不得带路径。
3. 生产环境缺失该变量时，应记录 warning 日志。
4. 如果配置成 `0.0.0.0`、`localhost`、`127.0.0.1`，生产环境应拒绝启动或至少打印 error。

### 7.2 Nginx 反代头补全

`chat.dreamwhale.top` 反代到 `127.0.0.1:9001` 的 location 中，需要补充：

```nginx
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-Port 443;
proxy_set_header X-Forwarded-Ssl on;
```

所有转发到 `chat_web` 的 location 都要保持一致：

```text
/api/
/
```

所有转发到 Django 的 location 也建议统一补齐：

```text
/api/v1/
/ws/
```

### 7.3 保持 API 路由分流规则

`chat.dreamwhale.top` 的生产反代必须保持：

```text
/api/v1/ -> 127.0.0.1:2026
/ws/     -> 127.0.0.1:2026
/api/    -> 127.0.0.1:9001
/        -> 127.0.0.1:9001
```

原因：

1. `/api/auth/apple/start` 是 Next.js BFF，必须走 `chat_web`。
2. `/api/auth/apple/callback` 是 Next.js BFF，必须走 `chat_web`。
3. `/api/auth/phone/*` 是 Next.js BFF，必须走 `chat_web`。
4. `/api/v1/*` 是 Django REST API，才应该直达 `2026`。

当前 `2026/README.md` 中仍存在“`/api/`、`/ws/` 反代到 `127.0.0.1:2026`”的旧表述，需要在工单实现时同步修正。

### 7.4 Cookie 与跨站回调检查

Apple Web 登录使用 `response_mode=form_post`，Apple 会从 `appleid.apple.com` 跨站 POST 回调到本站。

生产 Cookie 当前应满足：

```text
Secure=true
SameSite=None
Path=/
__Host- 前缀不能设置 Domain
```

需要确认：

1. `__Host-spark_apple_state` 在 Apple 回调时存在。
2. `__Host-spark_apple_nonce` 在 Apple 回调时存在。
3. `__Host-spark_apple_return` 在 Apple 回调时存在。
4. Apple 回调失败后这些临时 Cookie 被清理。
5. 成功后 `__Host-spark_refresh` 正常写入。

### 7.5 nonce mismatch 独立排查

修复错误 Origin 后，如果仍显示 `apple_web_nonce_mismatch`，再继续排查：

1. Django `/api/v1/auth/apple/web/login/` 是否收到 BFF 传入的 `nonce`。
2. Apple `id_token` 内的 `nonce` 是否和 BFF Cookie 保存的 nonce 一致。
3. 是否发生重复点击或重复提交导致一次性 state/nonce 被提前消费。
4. 是否存在多个 `chat.dreamwhale.top` 标签页并行发起 Apple 登录，后一次覆盖前一次 Cookie。
5. `APPLE_WEB_JWKS_VERIFY_SSL`、`APPLE_WEB_TOKEN_ENDPOINT`、`APPLE_WEB_PRIVATE_KEY` 等上游配置是否导致错误被映射成 nonce mismatch。

## 8. 实施步骤

### 8.1 本地代码

1. 在 `chat-web` 增加 public origin 工具函数。
2. 修改 `app/api/auth/apple/callback/route.ts`：
   - 错误跳转使用 `SPARK_PUBLIC_WEB_BASE_URL`。
   - 成功跳转也使用 `SPARK_PUBLIC_WEB_BASE_URL`。
   - `return_to` 仍只能是站内 path，禁止外部 URL。
3. 必要时修改 `app/api/auth/apple/start/route.ts`：
   - 日志记录 `redirect_uri`、`return_to`，但不得记录完整 token。
   - 若 `SPARK_APPLE_WEB_REDIRECT_URI` 域名和 `SPARK_PUBLIC_WEB_BASE_URL` 域名不一致，生产环境记录 error。
4. 增加测试：
   - 模拟 `request.url=https://0.0.0.0:9001/api/auth/apple/callback`。
   - 设置 `SPARK_PUBLIC_WEB_BASE_URL=https://chat.dreamwhale.top`。
   - 断言失败重定向为 `https://chat.dreamwhale.top/login?error=...`。

### 8.2 服务器配置

1. `/root/2026/.deploy.env` 增加：

```text
SPARK_PUBLIC_WEB_BASE_URL=https://chat.dreamwhale.top
```

2. `/root/2026/docker-compose.yml` 的 `chat_web.environment` 增加：

```yaml
SPARK_PUBLIC_WEB_BASE_URL: ${SPARK_PUBLIC_WEB_BASE_URL:-https://chat.dreamwhale.top}
```

3. `/etc/nginx/nginx.conf` 的 `chat.dreamwhale.top` server 补充 `X-Forwarded-*` 代理头。
4. 重载 Nginx：

```bash
nginx -t && systemctl reload nginx
```

5. 重启 `chat_web`：

```bash
cd /root/2026
docker compose --env-file .deploy.env restart chat_web
```

### 8.3 文档同步

同步更新：

1. `/Users/hua/Documents/project/Reference/2026/README.md`
2. `/Users/hua/Documents/project/Reference/2026/.deploy.env.example`
3. `/Users/hua/Documents/project/Reference/2026/docker-compose.yml`
4. `/Users/hua/Documents/project/Reference/SparkService/.env`

文档必须明确：

```text
chat.dreamwhale.top:
  /api/v1/ -> Django 2026
  /ws/     -> Django 2026
  /api/    -> chat-web 9001
  /        -> chat-web 9001
```

## 9. 验收标准

### 9.1 服务器 curl 验收

模拟 Apple callback 异常请求：

```bash
curl -k -i -X POST 'https://chat.dreamwhale.top/api/auth/apple/callback' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data 'state=bad&id_token=bad'
```

验收结果：

```text
Location: https://chat.dreamwhale.top/login?error=...
```

不得出现：

```text
https://0.0.0.0:9001
http://0.0.0.0:9001
https://127.0.0.1
http://localhost
```

### 9.2 浏览器验收

1. 打开 `https://chat.dreamwhale.top/login`。
2. 点击“使用 Apple 登录”。
3. Apple 授权后返回。
4. 成功时进入 `/chat` 或指定 `return_to` 页面。
5. 失败时留在 `https://chat.dreamwhale.top/login?error=...`。
6. Safari 不再出现“不允许使用受限制的网络端口”。

### 9.3 Cookie 验收

Apple start 响应必须写入：

```text
__Host-spark_apple_state
__Host-spark_apple_nonce
__Host-spark_apple_return
```

属性必须满足：

```text
Secure
HttpOnly
SameSite=None
Path=/
无 Domain
```

callback 成功后必须写入：

```text
__Host-spark_refresh
```

### 9.4 日志验收

`chat_web` 日志需要能区分：

1. callback body 不可读。
2. state 缺失或重放。
3. nonce 缺失或不匹配。
4. 上游 Django 登录失败。
5. 成功登录。

错误日志不得记录：

1. Apple `id_token` 完整内容。
2. authorization code 完整内容。
3. refresh token。
4. 用户隐私原文。

可以记录：

1. `request_id`
2. `http_status`
3. `upstream_code`
4. 耗时
5. 是否存在 state/nonce，不记录具体值

## 10. 回归测试

1. 手机号登录仍可请求验证码。
2. 手机号验证码校验成功后 Web Session 正常。
3. Apple 登录 start 接口返回正确公网 `redirect_uri`。
4. Apple 登录 callback 失败重定向域名正确。
5. Apple 登录 callback 成功后 refresh cookie 正常写入。
6. `/api/v1/auth/session/` 仍直达 Django。
7. `/api/auth/session` 仍走 chat-web BFF。
8. `/ws/` 仍直达 Django ASGI。
9. `chat_web` 容器健康检查正常。
10. Nginx reload 后 `https://chat.dreamwhale.top/login` 正常访问。

## 11. 风险与注意事项

1. 不能把 `SPARK_APPLE_WEB_REDIRECT_URI` 改成 `0.0.0.0`、`127.0.0.1` 或内网地址。
2. 不能把 `/api/` 全部代理到 Django，否则手机号登录和 Apple BFF 都会再次失效。
3. 不能在 `__Host-*` Cookie 上设置 Domain。
4. `SameSite=None` 必须配合 `Secure`，否则现代浏览器可能丢弃 Cookie。
5. 多标签页同时发起 Apple 登录会互相覆盖 state/nonce，本工单可先记录为已知风险，后续如有需要再改成服务端多事务 nonce 存储。

## 12. 当前建议结论

本次故障不是 Apple 开发者后台回调地址写错，也不是 `SPARK_APPLE_WEB_REDIRECT_URI` 当前值错误。

更可能的根因是：

```text
chat-web Apple callback 使用 request.url 推导公网 origin，
但生产 Next.js standalone 在 Nginx 反代后把自身监听地址 0.0.0.0:9001 当成 origin，
导致失败回跳地址错误。
```

必须同时做两层修复：

1. 应用层：用 `SPARK_PUBLIC_WEB_BASE_URL=https://chat.dreamwhale.top` 作为所有浏览器重定向的唯一公网 Origin。
2. 代理层：Nginx 补齐 `X-Forwarded-Host`、`X-Forwarded-Port`、`X-Forwarded-Proto`，让 Next.js 能正确理解外部访问地址。

