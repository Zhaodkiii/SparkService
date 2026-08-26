# AUTH-APPLE-001 移动端 Apple JWKS TLS 证书链故障修复工单

创建日期：2026-08-25  
状态：待开发  
优先级：P0  
故障等级建议：SEV-1（Apple 登录整体不可用且认证凭据进入日志）  
所属模块：账号与认证  
涉及端：SparkService 服务端  
触发接口：`POST /api/v1/auth/apple/login/`  
实施约束：本文件只创建需求工单，不修改业务代码、服务器证书、环境变量、数据库或任何客户端工程。

## 一、故障摘要

2026-08-25 15:37:25，iOS 客户端调用移动端 Apple 登录接口。SparkService 在获取 Apple JWKS（JSON Web Key Set，JWT 签名公钥集合）时发生 TLS 证书链校验失败，最终返回：

```text
HTTP 503
code=50321
msg=apple_jwks_unavailable
reason=[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate
```

本次请求耗时约 563ms，失败发生在 JWT 签名校验之前。当前没有证据表明 `identity_token`、`bundle_id`、`nonce`、Apple subject、`aud` 或客户端 Apple 授权流程本身存在错误。

同时发现 P0 安全问题：认证 API I/O 日志原文记录了 `identity_token`、`authorization_code`、`device_secret`、`nonce` 和 Apple subject，并在错误响应日志中再次复制完整请求体。必须作为同一事故的安全处置项优先治理。

## 二、范围与边界

### 2.1 本工单包含

1. 定位生产运行环境无法验证 `appleid.apple.com` 证书链的具体原因。
2. 修复 SparkService 运行环境的系统 CA/可信根证书链。
3. 保持 Apple JWKS HTTPS 严格证书校验。
4. 完善 JWKS 缓存、受控降级、并发抑制、预热和可观测性。
5. 对认证请求、响应及异常日志进行系统性脱敏。
6. 收敛对客户端暴露的底层 TLS 异常信息。
7. 建立移动 Apple 登录服务端回归、灰度、回滚和故障演练。
8. 对已经进入日志系统的认证凭据执行安全评估和处置。

### 2.2 明确不包含

- 不修改 iOS 客户端文件、接口参数、Apple Sign in 页面、nonce 生成或登录状态机。
- 不修改 Android、HarmonyOS 或 Web 客户端。
- 不把移动端 Apple 登录迁移到 Web Apple 接口。
- 不修改 Apple App ID、Bundle ID 或账号关联规则，除非后续证据证明这些配置另有独立问题。
- 不修改 AI bootstrap、模型配置、对话 Run 或 Pro 权益。
- 不以关闭 TLS 校验作为修复、临时方案或回滚方案。
- 不在代码中内置、固定或手工粘贴 Apple 公钥。
- 不在本工单创建阶段执行证书安装、服务重启、密钥轮换或日志删除。

## 三、当前实现与真实调用链

### 3.1 关键目录

```text
accounts/
├── auth/
│   ├── serializers.py                 # AppleLoginSerializer
│   └── views.py                       # AppleLoginView
├── services/
│   ├── login_service.py               # Apple 登录编排、nonce/账号/Session
│   └── apple_identity_service.py      # JWKS 拉取、JWT 签名与 claim 校验
├── tests_apple_identity_service.py    # JWT 时间/audience 单元测试
├── tests_identity_scope.py            # Apple 身份域测试
└── tests_device_account_login.py      # 设备凭据相关回归

common/
└── middleware/
    └── request_logging_middleware.py  # API 请求/响应正文日志

SparkService/
└── settings.py                        # 日志与运行配置
```

### 3.2 当前调用链

```text
AppleLoginView.post
  -> AppleLoginSerializer 校验输入
  -> LoginService.authenticate_apple_and_issue_tokens
  -> AppleIdentityService.verify_identity_token
  -> 读取 JWT 未验证 header 中的 kid/alg
  -> AppleIdentityService._load_jwks
       -> 读取缓存 sparkservice:apple:jwks
       -> 缓存未命中时访问 https://appleid.apple.com/auth/keys
       -> ssl.create_default_context() 建立严格 TLS 上下文
       -> 当前在 TLS 证书链校验阶段失败
  -X-> 尚未执行 JWKS kid 匹配
  -X-> 尚未执行 JWT 签名、iss/aud/exp/iat 校验
  -X-> 尚未执行 nonce、账号解析和设备 Session
```

### 3.3 当前配置事实

- `APPLE_JWKS_VERIFY_SSL=true` 时，代码使用 `ssl.create_default_context()`。
- JWKS 地址为 `https://appleid.apple.com/auth/keys`。
- JWKS 缓存键为 `sparkservice:apple:jwks`。
- 默认缓存时间为 3600 秒。
- 当前捕获所有拉取异常并映射为 `50321 apple_jwks_unavailable`。
- 当前错误响应的 `data.reason` 直接包含底层异常字符串。
- 当前认证路径没有请求体字段脱敏；Chat AI 路径已有局部脱敏，但认证路径未复用。

## 四、根因分析

### 4.1 已确认根因层级

直接原因是 SparkService 所在 Python/OpenSSL 运行环境无法从 Apple 服务端证书构建到本地可信根：

```text
ssl.create_default_context()
  -> TLS handshake
  -> certificate chain validation
  -> unable to get local issuer certificate
  -> urlopen 失败
  -> JWKS 不可用
  -> Apple 登录返回 50321
```

这是服务端出站 HTTPS 信任链故障，不是 iOS 与 SparkService 之间的入站 HTTPS 故障。

### 4.2 待确认的底层原因

按优先级排查：

| 假设 | 说明 | 需要的证据 |
|---|---|---|
| 运行环境 CA bundle 缺失或过期 | 精简系统、镜像或 Python 环境没有可用可信根 | Python verify paths、CA 文件、包版本 |
| Python/OpenSSL 未读取系统 CA | `ssl` 默认路径指向不存在或错误文件 | `ssl.get_default_verify_paths()` 与文件存在性 |
| 出站 HTTPS 代理/网关替换证书 | 代理签发的根证书未进入应用信任库 | 实际 peer issuer、代理配置和网络出口策略 |
| 部署实例配置漂移 | 只有部分实例/Worker 使用不同 CA、Python 或环境变量 | 各实例指纹和逐实例探测 |
| Apple 返回链异常 | 概率较低，需通过不同可信网络交叉验证 | 外部监控与 Apple 端点证书链 |

当前错误不是 DNS 解析失败、连接超时或 HTTP 状态错误，因为连接已经进入 TLS 证书验证阶段。系统时间异常通常产生“证书尚未生效/已过期”错误，与本日志不一致，但仍应在生产基线检查中核验。

### 4.3 不能从本日志得出的结论

- 不能认定 JWT 签名有效，因为尚未取得公钥。
- 不能认定 Token 中未经验证的 `aud`、email、sub 等 claim 可信。
- 不能认定 nonce 正确或错误，因为 nonce 校验尚未执行。
- 不能认定 Apple authorization code 有效；当前移动登录主链路也不依赖该字段完成 JWKS 校验。
- 不能通过重新调用 Apple 登录证明问题已恢复；必须先验证服务端 TLS 和 JWKS readiness。

## 五、生产环境只读诊断工单

以下诊断由运维在故障实例的同一用户、同一 Python 虚拟环境或同一容器内执行。命令及结果不得包含环境密钥、代理密码或请求 Token。

### 5.1 Python/OpenSSL 基线

```bash
python -c 'import platform, ssl; print(platform.python_version()); print(ssl.OPENSSL_VERSION); print(ssl.get_default_verify_paths())'
python -c 'import ssl; p=ssl.get_default_verify_paths(); print(p.cafile, p.capath)'
```

验收证据：Python/OpenSSL 版本、实际 `cafile/capath`、文件是否存在、运行进程用户是否可读。

### 5.2 端点交叉探测

```bash
curl --fail --silent --show-error --max-time 10 https://appleid.apple.com/auth/keys
openssl s_client -connect appleid.apple.com:443 -servername appleid.apple.com -verify_return_error </dev/null
python -c 'import ssl, urllib.request; print(urllib.request.urlopen("https://appleid.apple.com/auth/keys", timeout=8, context=ssl.create_default_context()).status)'
```

判断矩阵：

| curl | Python | 结论方向 |
|---:|---:|---|
| 成功 | 失败 | Python/OpenSSL verify path 或虚拟环境问题 |
| 失败 | 失败 | 系统 CA、网络出口或 HTTPS 代理问题 |
| 单实例失败 | 其他实例成功 | 部署实例/镜像配置漂移 |
| 全部成功但业务失败 | 进程环境、缓存、权限或实际服务实例不一致 |

### 5.3 代理与证书链核验

- 只确认是否设置 `HTTPS_PROXY`、`HTTP_PROXY`、`NO_PROXY`，不得把包含账号密码的变量值复制进工单或日志。
- 对比 `openssl s_client` 返回的 subject、issuer 和完整链。
- 若存在企业代理，只把受控企业根 CA 安装到运行环境信任库；不得在业务代码中跳过校验。
- 记录实例 ID、镜像 digest、Python/OpenSSL 版本和 CA bundle 校验和，排除滚动发布漂移。

## 六、修复方案

### 6.1 P0：日志与凭据事故处置

先于可用性修复实施：

1. 认证路径请求日志对以下字段递归脱敏：
   - `identity_token`
   - `authorization_code`
   - `device_secret`
   - `nonce`
   - `access_token`
   - `refresh_token`
   - `client_secret`
   - `password`、验证码及 Cookie/Authorization
2. 4xx/5xx 响应日志不得再次附加未脱敏 `request_body`。
3. `data.reason` 不向客户端返回底层路径、OpenSSL、代理或证书细节；客户端仅保留稳定错误码和安全提示。
4. 内部结构化日志可记录 `error_class`、`tls_verify_code`、目标 host、实例 ID 和 request_id，不记录凭据。
5. 盘点 `access_api_io.log`、控制台采集、日志平台、备份和告警通知中的泄露副本，按安全流程限制访问并确定保留/清理方案。
6. 对本次暴露的 `device_secret` 进行风险评估并制定安全轮换方案；不得在未评估设备登录影响前直接破坏现有会话。
7. Apple identity token 和 authorization code 属于短期凭据，但仍按已泄露凭据处理，不得继续复制、重放或写入测试 fixture。

日志脱敏应抽取为认证/API 共用策略，采用“默认敏感字段集合 + 路径专项字段”的方式，不能只针对本次示例字符串硬编码。

### 6.2 P0：修复运行环境 CA 信任链

目标状态：`ssl.create_default_context()` 在业务运行环境中可直接验证 `appleid.apple.com`，无需自定义不安全 Context。

实施要求：

1. 在实际宿主机/容器镜像中安装或更新受信任的 CA bundle。
2. 确认 Python/OpenSSL 默认 verify path 指向真实、可读、随镜像发布的 CA 文件。
3. 若必须配置 `SSL_CERT_FILE` 或等价路径，只能指向经过运维审核的 CA bundle，并保证 Web 进程与 Worker 一致。
4. 若使用 HTTPS 出站代理，将代理根 CA 纳入系统信任链并保留审计，不在应用代码中关闭验证。
5. 修复后滚动重启 SparkService 实例，并逐实例执行 JWKS readiness。
6. 对镜像、CA bundle 和 OpenSSL 版本建立发布清单，避免下一次构建回退。

禁止方案：

```text
APPLE_JWKS_VERIFY_SSL=false
ssl._create_unverified_context()
CERT_NONE
check_hostname=false
捕获证书错误后改用 HTTP
将 Apple 公钥永久写入代码
```

### 6.3 P1：严格 TLS 配置收敛

建议演进：

- 将生产默认值收敛为严格校验，生产启动时发现 TLS 校验被关闭则 readiness 失败并告警。
- 删除“为避免证书链问题默认不校验证书”的不安全运行假设。
- 将 JWKS URL、TLS 验证状态、超时等非密钥配置纳入启动诊断，但不得输出 CA 私有内容。
- Web Apple 与移动 Apple 可以保持不同缓存键和业务契约，但必须共用安全 TLS/日志规范。

本项属于服务端安全基线，不改变移动客户端接口或流程。

### 6.4 P1：JWKS 可用性与缓存

当前已有一小时缓存，但缓存未命中时登录完全依赖实时出站请求。补充以下能力：

1. 正常缓存：成功拉取后保存 JWKS、拉取时间和来源，TTL 保持可配置。
2. 单飞刷新：同一时刻只允许一个实例/协程刷新，其他请求等待短时间或读取有效缓存，避免登录并发放大 Apple 故障。
3. 短期负缓存/熔断：对连续网络故障进行 15–30 秒抑制，避免每个登录请求都触发出站 TLS 握手。
4. 预热：部署完成和缓存到期前主动刷新，readiness 可识别是否存在可用 key。
5. 有界 stale-if-error：仅在严格 TLS 获取失败、旧 JWKS 尚在允许宽限期、且旧集合中存在当前 JWT `kid` 时使用最近成功缓存。
6. 新 `kid` 不存在于旧缓存时必须刷新；刷新失败继续返回 `50321`，不得绕过签名校验。
7. 缓存内容必须来自曾经通过严格 TLS 获取的 Apple JWKS；禁止把不校验 TLS 的响应写入可信缓存。

宽限期由安全评审确定，建议上限不超过 24 小时，并记录 `jwks_source=stale_cache` 告警。该能力是短时可用性缓冲，不替代 CA 修复。

### 6.5 P1：超时、重试与错误模型

- 连接/读取超时保持有界，并拆分指标。
- DNS、连接复位和 5xx 可进行少量带抖动重试。
- `CERTIFICATE_VERIFY_FAILED` 在单个请求内视为配置/信任链错误，不做无意义快速重试。
- 保持现有对客户端契约：HTTP `503`、业务码 `50321`、`msg=apple_jwks_unavailable`。
- 可在不破坏客户端的前提下增加安全的 `retryable` 与 request_id，但不得暴露原始异常。
- JWKS JSON 空、结构错误继续使用独立 `50322 apple_jwks_invalid`。
- Token kid 不存在、签名失败、aud/时间/nonce 错误不得映射成 JWKS TLS 故障。

## 七、Readiness、监控与告警

### 7.1 内部 Readiness

新增内部或受保护检查项，不暴露 Apple 公钥详情：

```json
{
  "component": "apple_mobile_jwks",
  "ready": false,
  "tls_verified": false,
  "cache_state": "miss",
  "last_success_at": null,
  "last_error_code": "tls_untrusted_issuer"
}
```

Readiness 必须区分：缓存可用、实时拉取成功、使用宽限缓存、完全不可用。不得通过实际伪造登录请求执行健康检查。

### 7.2 指标

- `apple_jwks_fetch_total{outcome,reason,source}`。
- `apple_jwks_fetch_duration_ms`。
- `apple_jwks_cache_total{result=fresh|stale|miss}`。
- `apple_jwks_stale_age_seconds`。
- `apple_login_total{outcome,error_code}`。
- `apple_login_50321_total`。
- `auth_sensitive_log_redaction_total{field}`，仅记录字段名和次数。

### 7.3 告警

- 5 分钟内 `apple_login_50321_total > 0` 触发高优先级告警。
- 连续 JWKS 刷新失败立即告警，不等待缓存完全过期。
- 使用 stale cache 时告警并启动 CA/网络排查。
- 任一生产实例 `tls_verified=false` 或 CA bundle 指纹漂移时告警。
- 日志抽检发现 JWT、authorization code 或 device secret 形态时触发安全告警。

## 八、测试策略

### 8.1 单元测试

补充 `accounts/tests_apple_identity_service.py`：

- 严格 TLS Context 被使用，禁止 unverified Context。
- 新鲜缓存命中时不访问网络。
- 缓存未命中且合法 JWKS 返回时正确写缓存。
- 证书校验失败映射为 `50321`，客户端响应不含底层异常。
- 未知 `kid` 触发强制刷新一次。
- 严格 TLS 刷新失败时，仅对宽限期内且包含目标 `kid` 的旧缓存降级。
- 旧缓存无目标 `kid` 时拒绝校验。
- 并发刷新只产生一次上游请求。
- 非 TLS 临时错误遵守最大重试次数。
- JWKS 空列表/坏 JSON 映射为 `50322`。

### 8.2 日志安全测试

针对 `common/middleware/request_logging_middleware.py`：

- `/api/v1/auth/apple/login/` 请求日志中敏感字段均为 `<redacted>`。
- 错误响应日志不会复制原始 request body。
- 嵌套 JSON、大小写变体和数组中的敏感字段同样脱敏。
- Authorization、Cookie 和代理认证 Header 不进入日志。
- 非敏感字段如 request_id、path、status 和 duration 保留。
- 测试失败输出本身不得包含真实格式的 Token 或密钥。

### 8.3 集成测试

- 使用本地受控 HTTPS 测试服务验证：可信根成功、不可信根失败、中间证书缺失失败。
- 使用模拟 JWKS 验证 key rotation、缓存刷新和 stale-if-error。
- Redis 暂时不可用时不绕过 JWT 签名校验。
- 多实例并发刷新没有请求风暴。
- 不在 CI 中依赖实时 Apple 端点作为唯一通过条件。

### 8.4 生产冒烟

1. 同一运行环境 Python 严格 TLS 请求 Apple JWKS 成功。
2. 内部 readiness 为 `ready=true`、`tls_verified=true`。
3. 测试账号完成一次 Apple 登录并获得原有响应契约。
4. 验证 SocialIdentity、User 和设备 Session 仍遵循原有逻辑。
5. 搜索全链路日志，确认没有认证凭据原文。
6. 清空测试缓存后再次验证实时刷新与缓存命中。

## 九、分阶段实施

| 阶段 | 内容 | 阶段目标 | 出口证据 |
|---|---|---|---|
| `A0` | 冻结日志传播、凭据风险评估、实例盘点 | 控制认证凭据继续扩散 | 日志抽检与安全处置记录 |
| `A1` | 生产同环境 TLS/CA/代理诊断 | 定位到具体 bundle、路径、代理或实例 | 逐实例诊断矩阵 |
| `A2` | 修复 CA 信任链并滚动验证 | 严格 TLS 可拉取 Apple JWKS | Python/curl/openssl 与 readiness 证据 |
| `A3` | 认证日志递归脱敏与安全错误响应 | 请求和响应不再泄露凭据 | 单元测试与日志扫描 |
| `A4` | 缓存单飞、预热、stale-if-error、熔断 | 上游短故障不形成登录风暴 | 故障注入报告 |
| `A5` | Apple 登录回归、灰度和监控 | 恢复登录且不改变客户端流程 | 生产冒烟与指标面板 |

依赖关系：

```text
A0 日志止血 ───────────────┐
                           ├─> A3 日志安全 ─────┐
A1 TLS 根因 -> A2 CA 修复 ─┘                   ├─> A5 灰度验收
                └────────────> A4 可用性加固 ──┘
```

## 十、子工单拆分

| 子工单 | 责任范围 | 主要文件/系统 | 出口 |
|---|---|---|---|
| `AUTH-APPLE-001A` | 泄露日志盘点与凭据风险处置 | 日志平台、`access_api_io.log` | 安全处置记录 |
| `AUTH-APPLE-001B` | 生产 CA/代理/实例诊断 | 宿主机、镜像、Python/OpenSSL | 根因报告 |
| `AUTH-APPLE-001C` | CA bundle 与部署基线修复 | 镜像/主机/部署配置 | 严格 TLS 证据 |
| `AUTH-APPLE-001D` | 认证请求/响应日志脱敏 | `request_logging_middleware.py` | 日志安全测试 |
| `AUTH-APPLE-001E` | JWKS 缓存与故障保护 | `apple_identity_service.py` | 单元/集成测试 |
| `AUTH-APPLE-001F` | 监控、readiness 与灰度 | 监控/告警/发布系统 | 生产验收报告 |

## 十一、发布与回滚

### 11.1 发布顺序

1. 先限制敏感日志传播并完成风险处置。
2. 在一台不承载正式流量的同构实例修复 CA。
3. 运行严格 TLS、JWKS 和 Apple 登录冒烟。
4. 灰度一个实例，确认无 `50321` 且证书 issuer 符合预期。
5. 滚动其余实例，逐实例验证 CA bundle 指纹。
6. 上线日志脱敏，再上线缓存/熔断增强。
7. 保留至少一个完整 JWKS 缓存周期的重点监控。

### 11.2 回滚原则

- CA 更新异常时回滚到上一份已验证 CA bundle 或上一镜像。
- 将流量摘除故障实例，而不是关闭 TLS 校验。
- 缓存增强异常时可回滚增强逻辑，但保留严格 TLS 和日志脱敏。
- 不回滚到输出完整认证请求体的日志实现。
- 不修改 iOS 客户端以规避服务端故障。

## 十二、验收标准

### 12.1 根因与 TLS

- [ ] 形成生产同运行环境根因报告，明确是 CA bundle、verify path、代理还是实例漂移。
- [ ] 所有生产实例通过 `ssl.create_default_context()` 验证 Apple JWKS。
- [ ] `APPLE_JWKS_VERIFY_SSL` 保持开启。
- [ ] 未使用 unverified Context、`CERT_NONE`、HTTP 或固定 Apple 公钥。
- [ ] 镜像和运行实例的 CA/OpenSSL 基线可追踪。

### 12.2 登录兼容性

- [ ] `POST /api/v1/auth/apple/login/` 的路径、请求 DTO 和成功响应保持兼容。
- [ ] iOS 客户端无代码、配置和流程改动。
- [ ] JWT 签名、iss、aud、exp、iat、sub 与 nonce 校验继续执行。
- [ ] 账号解析、设备 Session 和登录审计逻辑无语义变化。
- [ ] Apple 公钥轮换后可以刷新并命中新 `kid`。

### 12.3 安全与日志

- [ ] 日志中不存在 identity token、authorization code、device secret、nonce、access/refresh token 原文。
- [ ] API 错误响应不暴露 OpenSSL、系统路径、代理或证书内部细节。
- [ ] 已泄露日志的存储位置、访问范围、保留策略和凭据处置有审计记录。
- [ ] 日志仍可通过 request_id、error_code、实例和耗时完成排障。

### 12.4 可用性

- [ ] 新鲜缓存路径不访问 Apple。
- [ ] 同一缓存刷新窗口不会发生并发请求风暴。
- [ ] Apple 短时不可达时，只按安全规则使用有界旧缓存。
- [ ] 未知 `kid` 且无法刷新时安全失败，不接受未验证 Token。
- [ ] `50321` 告警、readiness 和故障看板可用。

## 十三、开发前必须确认

1. 故障请求实际由哪一个生产实例/容器处理，其镜像 digest 和 Python/OpenSSL 版本是什么。
2. 该实例是否经过 HTTPS 出站代理、WAF、透明网关或企业证书替换。
3. Python 默认 CA 文件实际路径、版本、权限和校验和。
4. 同一集群其他实例是否能严格 TLS 拉取 Apple JWKS。
5. Redis 中是否存在最近成功、可验证来源和生成时间明确的 JWKS 缓存。
6. API I/O 日志已同步到哪些平台、备份或通知渠道。
7. `device_secret` 轮换对当前设备账号和 Session 的影响及安全处置负责人。
8. stale-if-error 最大宽限期由账号、安全和运维共同确认。

---

工单结论：本次故障的直接原因是 SparkService 运行环境无法建立 Apple JWKS HTTPS 证书信任链。修复必须落在服务端 CA/部署基线，同时完成认证日志脱敏和 JWKS 可用性加固；不得关闭 TLS 校验，也不得修改任何客户端来绕过问题。
