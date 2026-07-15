# ACCOUNT-IDENTITY-000001 Health 与 MedicineBox 账号身份共用需求及详细设计工单

创建日期：2026-07-15  
关联模块：账户登录、Apple 登录、手机号 OTP、SocialIdentity、设备会话、通知中心  
优先级：P0  
需求类型：新项目账号体系设计 / 多 App 账号共用 / 登录身份作用域

## 1. 背景

当前账号登录身份由 `accounts_socialidentity` 表承载，唯一键是：

```python
models.UniqueConstraint(
    fields=["bundle_id", "provider", "provider_uid"],
    name="uniq_social_identity_bundle_provider_uid",
)
```

这意味着同一个手机号或同一个 Apple `sub`，只要 `bundle_id` 不同，就可以创建不同内部用户。

现需要将以下两个 App 视为同一个账号体系：

| App | bundle_id | 目标关系 |
|---|---|---|
| 健康 App | `cn.Zhaodk.Health` | 与 MedicineBox 共用账号 |
| 药箱 App | `cn.Zhaodk.MedicineBox` | 与 Health 共用账号 |

用户在任一 App 使用相同手机号或相同 Apple ID 登录时，应命中同一个内部 `User`，而不是创建两个用户。

## 2. 当前问题

### 2.1 手机号登录

当前手机号 OTP 校验成功后，服务端按如下维度查找或创建身份：

```text
bundle_id + provider=phone + provider_uid=normalized_phone
```

因此：

| 手机号 | bundle_id | 当前行为 |
|---|---|---|
| `+8615385056020` | `cn.Zhaodk.Health` | 创建或命中用户 A |
| `+8615385056020` | `cn.Zhaodk.MedicineBox` | 创建或命中用户 B |

这与“Health 与 MedicineBox 共用账号”的目标冲突。

### 2.2 Apple 登录

当前 Apple 登录先校验 `identity_token.aud == bundle_id`，再使用 Apple `sub` 与 `matched_audience` 查找身份：

```text
bundle_id=matched_audience + provider=apple + provider_uid=apple_sub
```

如果 Apple 对这两个 App 返回的 `sub` 一致，则当前仍会因为 `bundle_id` 不同创建两个内部用户。

如果 Apple 对不同 App 返回的 `sub` 不一致，则无法仅依赖 `sub` 自动归并，需要额外确认 Apple 开发者配置是否属于同一 Team / Services ID / App Group 语义。本工单默认按“相同 Apple ID 在这两个 bundle 下可得到可归并身份”设计，但上线前必须用真实设备验签确认。

## 3. 目标

1. `cn.Zhaodk.Health` 与 `cn.Zhaodk.MedicineBox` 共用同一账号身份作用域。
2. 用户用同一手机号登录两个 App 时，必须命中同一个 `User`。
3. 用户用同一 Apple ID 登录两个 App 时，在 Apple `sub` 可归并的前提下，必须命中同一个 `User`。
4. 其他 bundle_id 继续保持现有隔离行为，不被本次改造影响。
5. 设备会话、设备画像、登录审计、通知上下文仍记录客户端真实 `bundle_id`，便于排查与业务统计。
6. 新项目从首版开始按共享身份作用域写入，不产生 Health 与 MedicineBox 双用户分裂。

## 4. 非目标

1. 本工单不合并所有 App 的账号体系，只处理 `cn.Zhaodk.Health` 与 `cn.Zhaodk.MedicineBox`。
2. 本工单不改变 Apple token 的 `aud` 验签规则，仍必须校验真实客户端 bundle_id。
3. 本工单不把 `TrustedDevice`、`AccountDeviceSession` 的真实 `bundle_id` 改成共享值。
4. 本工单不包含存量账号迁移、历史用户合并、历史业务数据归并。
5. 本工单不改变手机号支持地区、短信发送能力、验证码频控策略。

## 5. 核心方案

### 5.1 新增账号身份作用域

新增一个服务端内部概念：`identity_scope`，用于表达“哪些 bundle 共用同一登录身份”。

建议配置：

```python
ACCOUNT_IDENTITY_SCOPE_ALIASES = {
    "cn.Zhaodk.Health": "cn.Zhaodk.Health",
    "cn.Zhaodk.MedicineBox": "cn.Zhaodk.Health",
}
```

规则：

| 输入 bundle_id | identity_scope |
|---|---|
| `cn.Zhaodk.Health` | `cn.Zhaodk.Health` |
| `cn.Zhaodk.MedicineBox` | `cn.Zhaodk.Health` |
| 其他 bundle_id | 原 bundle_id |

新项目首版可继续复用 `SocialIdentity.bundle_id` 字段存储 `identity_scope`，无需新增数据库字段。代码层必须通过统一函数转换，禁止登录链路直接把客户端 bundle_id 写入 `SocialIdentity.bundle_id`。

建议新增服务：

```text
accounts/services/identity_scope_service.py
```

职责：

```python
class IdentityScopeService:
    @staticmethod
    def resolve(bundle_id: str) -> str:
        ...
```

### 5.2 字段语义约定

| 字段 | 存储内容 | 是否真实 bundle_id |
|---|---|---|
| `SocialIdentity.bundle_id` | 账号身份作用域 `identity_scope` | 否，允许是共享作用域 |
| `LoginAudit.bundle_id` | 本次登录真实客户端 bundle_id | 是 |
| `PhoneOTP.bundle_id` / `EmailOTP.bundle_id` | 本次 OTP 请求真实客户端 bundle_id | 是 |
| `TrustedDevice.bundle_id` | 真实客户端 bundle_id | 是 |
| `AccountDeviceSession.bundle_id` | 真实客户端 bundle_id | 是 |

这样既能共用账号，又不会丢失真实 App 来源。

## 6. 服务端详细设计

### 6.1 手机号 OTP 请求阶段

当前代码位置：

```text
SparkService/accounts/services/otp_service.py
OTPService.request_phone_otp
```

当前按 `normalized_bundle_id` 查询手机号身份。应改为：

```text
identity_scope = IdentityScopeService.resolve(normalized_bundle_id)
SocialIdentity.objects.filter(
    bundle_id=identity_scope,
    provider=SocialIdentity.Provider.PHONE,
    provider_uid=normalized_phone,
)
```

注意：

1. `PhoneOTP.bundle_id` 仍保存 `normalized_bundle_id`，即真实请求来源。
2. 通知中心记录仍传真实 `bundle_id`。
3. `requested_user` 与 `resolved_identity` 按 `identity_scope` 命中结果设置。

### 6.2 手机号 OTP 校验阶段

当前代码位置：

```text
SparkService/accounts/services/otp_service.py
OTPService.verify_phone_otp_and_issue_tokens
```

修改规则：

1. `otp.bundle_id` 与请求 `bundle_id` 的一致性校验继续使用真实 bundle_id。
2. 通过校验后计算：

```text
identity_scope = IdentityScopeService.resolve(normalized_bundle_id)
```

3. 查询或创建 `SocialIdentity` 时使用 `identity_scope`：

```text
SocialIdentity.objects.select_for_update().filter(
    bundle_id=identity_scope,
    provider=SocialIdentity.Provider.PHONE,
    provider_uid=normalized_phone,
)
```

4. 新建身份时写入：

```text
bundle_id=identity_scope
```

5. 设备绑定和 token 签发仍使用真实 `normalized_bundle_id`。

### 6.3 Apple 登录阶段

当前代码位置：

```text
SparkService/accounts/services/login_service.py
LoginService.authenticate_apple_and_issue_tokens
```

修改规则：

1. `APPLE_ALLOWED_BUNDLE_IDS` 必须同时允许：

```text
cn.Zhaodk.Health
cn.Zhaodk.MedicineBox
```

2. Apple token 验签仍使用真实请求 bundle_id：

```text
AppleIdentityService.verify_identity_token(
    identity_token=identity_token,
    audiences=[normalized_bundle_id],
)
```

3. 验签成功后，新增：

```text
identity_scope = IdentityScopeService.resolve(matched_audience)
```

4. 查找和创建 Apple `SocialIdentity` 时使用 `identity_scope`：

```text
_load_apple_identity_for_update(
    bundle_id=identity_scope,
    subject=subject,
    request_id=request_id,
)
```

```text
SocialIdentity.objects.create(
    user=user,
    bundle_id=identity_scope,
    provider=SocialIdentity.Provider.APPLE,
    provider_uid=subject,
)
```

5. `LoginAudit.bundle_id`、`_prepare_login_entitlements(...)`、`_issue_tokens(...)` 继续使用 `matched_audience`，即真实客户端 bundle_id。

### 6.4 密码登录或 identifier 查找

当前代码位置：

```text
SparkService/accounts/services/login_service.py
LoginService._find_user_by_identifier
```

如果手机号走密码登录或通用 identifier 登录，该函数里按手机号查 `SocialIdentity` 时也必须使用 `identity_scope`。

规则：

```text
normalized_bundle_id = request bundle_id
identity_scope = IdentityScopeService.resolve(normalized_bundle_id)
filter(bundle_id=identity_scope)
```

## 7. 新项目初始化规则

本项目按全新项目处理，不考虑历史账号迁移。

初始化要求：

1. 首版上线前即配置 `ACCOUNT_IDENTITY_SCOPE_ALIASES`。
2. 所有登录身份创建入口必须先调用 `IdentityScopeService.resolve(...)`。
3. `SocialIdentity.bundle_id` 从第一条数据开始就写入 `identity_scope`。
4. `PhoneOTP`、`LoginAudit`、`TrustedDevice`、`AccountDeviceSession` 从第一条数据开始就写入真实客户端 bundle_id。
5. 不需要编写存量迁移脚本、冲突扫描脚本、历史账号合并脚本。

新项目数据库期望数据形态：

| 场景 | SocialIdentity.bundle_id | 真实来源记录 |
|---|---|---|
| Health 手机号首登 | `cn.Zhaodk.Health` | `PhoneOTP.bundle_id=cn.Zhaodk.Health` |
| MedicineBox 同手机号登录 | 命中已有 `cn.Zhaodk.Health` 身份 | `PhoneOTP.bundle_id=cn.Zhaodk.MedicineBox` |
| Health Apple 首登 | `cn.Zhaodk.Health` | `LoginAudit.bundle_id=cn.Zhaodk.Health` |
| MedicineBox 同 Apple 登录 | 命中已有 `cn.Zhaodk.Health` 身份 | `LoginAudit.bundle_id=cn.Zhaodk.MedicineBox` |

## 8. 配置与兼容

### 8.1 配置项

建议新增 Django settings：

```python
ACCOUNT_IDENTITY_SCOPE_ALIASES = {
    "cn.Zhaodk.Health": "cn.Zhaodk.Health",
    "cn.Zhaodk.MedicineBox": "cn.Zhaodk.Health",
}
```

没有出现在配置里的 bundle_id，默认返回自身。

### 8.2 兼容策略

1. 老客户端不需要改请求参数。
2. 服务端仍接受两个真实 bundle_id。
3. 登录 token 内的 `bundle_id` 仍是真实客户端 bundle_id。
4. 后台按 App 统计登录、设备、短信发送时，继续使用审计表和 OTP 表里的真实 bundle_id。
5. 后台按账号身份查找时，必须理解 `SocialIdentity.bundle_id` 已经是身份作用域，不一定等于真实客户端包名。

## 9. 测试建议

### 9.1 单元测试

新增测试文件建议：

```text
SparkService/accounts/tests_identity_scope.py
```

覆盖：

1. `IdentityScopeService.resolve("cn.Zhaodk.Health") == "cn.Zhaodk.Health"`。
2. `IdentityScopeService.resolve("cn.Zhaodk.MedicineBox") == "cn.Zhaodk.Health"`。
3. 未配置 bundle 返回自身。

### 9.2 手机号登录测试

覆盖：

1. Health 首次手机号登录创建用户 A 与 `SocialIdentity(bundle_id=cn.Zhaodk.Health, provider=phone)`。
2. MedicineBox 使用相同手机号登录，命中用户 A，不创建用户 B。
3. MedicineBox 的 `PhoneOTP.bundle_id`、`LoginAudit.bundle_id`、`TrustedDevice.bundle_id` 仍记录 `cn.Zhaodk.MedicineBox`。
4. 其他 bundle 使用相同手机号登录，仍创建独立用户。

### 9.3 Apple 登录测试

覆盖：

1. Health Apple 首登创建用户 A 与 `SocialIdentity(bundle_id=cn.Zhaodk.Health, provider=apple)`。
2. MedicineBox 使用相同 Apple `sub` 登录，命中用户 A。
3. Apple token `aud` 仍必须匹配真实请求 bundle_id。
4. `LoginAudit.bundle_id` 与设备会话仍保留真实 bundle_id。

## 10. 验收标准

1. `cn.Zhaodk.Health` 与 `cn.Zhaodk.MedicineBox` 使用同一手机号登录后返回同一个 `user_id`。
2. `cn.Zhaodk.Health` 与 `cn.Zhaodk.MedicineBox` 使用同一 Apple ID 登录后，在 Apple `sub` 一致时返回同一个 `user_id`。
3. 两个 App 的设备会话互不覆盖真实 bundle 信息，token 中仍能区分来源 App。
4. 通知中心短信发送记录仍能看到真实请求 bundle_id。
5. 其他 bundle_id 的账号隔离行为不变。
6. 新项目库中不会出现 `SocialIdentity(bundle_id=cn.Zhaodk.MedicineBox, provider=phone/apple, ...)` 这类账号身份数据。
7. 新增和修改的登录链路测试全部通过。

## 11. 建议拆分任务

| 任务 | 负责人 | 说明 |
|---|---|---|
| 新增 IdentityScopeService 与配置 | 后端 | 建立 bundle 到 identity_scope 的统一转换 |
| 改造手机号 OTP 身份查找/创建 | 后端 | request 与 verify 阶段都使用 identity_scope |
| 改造 Apple 身份查找/创建 | 后端 | aud 验签保持真实 bundle，SocialIdentity 使用 identity_scope |
| 改造通用 identifier 手机号查找 | 后端 | 避免密码/identifier 登录漏掉共享规则 |
| 补充自动化测试 | 后端测试 | 覆盖手机号、Apple、新项目初始化数据形态、其他 bundle 隔离 |
| 真实设备 Apple 登录联调 | iOS + 后端 | 确认两个 bundle 下 Apple `sub` 是否可归并 |

## 12. 关键代码位置

| 文件 | 需要关注的逻辑 |
|---|---|
| `SparkService/accounts/models.py` | `SocialIdentity` 唯一约束与字段语义 |
| `SparkService/accounts/services/otp_service.py` | 手机号 OTP 请求、校验、身份创建 |
| `SparkService/accounts/services/login_service.py` | Apple 登录、手机号 identifier 查找、token 签发 |
| `SparkService/accounts/services/apple_identity_service.py` | Apple token `aud` 验签，不改为共享 scope |
| `SparkService/accounts/services/device_session_service.py` | token 与设备会话继续使用真实 bundle_id |
| `SparkService/accounts/services/device_linking_service.py` | 设备画像继续使用真实 bundle_id |

## 13. 上线风险

1. Apple 不同 bundle 下 `sub` 是否一致需要真实联调确认；如果不一致，仅靠本工单方案无法自动识别为同一个 Apple ID。
2. 后台或运营报表如果直接把 `SocialIdentity.bundle_id` 当真实 App 包名，需要同步调整认知或查询口径。
3. 登录身份共享后，一个 App 的账号注销、封禁、停用可能影响另一个 App，需要确认账号生命周期是否也共用。
4. 新项目首版必须先完成身份作用域改造再开放注册登录，避免上线后再产生需要合并的双账号。

## 14. 推荐决策

推荐本期采用“复用 `SocialIdentity.bundle_id` 存储 identity_scope”的轻量方案。

原因：

1. 新项目没有历史数据负担，直接用现有唯一约束即可表达共享账号。
2. 不需要立即修改数据库唯一约束。
3. 真实 bundle_id 仍保留在 OTP、审计、设备、会话表中。
4. 后续如果更多 App 需要共用账号，只需扩展 `ACCOUNT_IDENTITY_SCOPE_ALIASES`。

长期如果共享账号体系变多，再考虑给 `SocialIdentity` 增加显式字段 `identity_scope`，并将 `bundle_id` 恢复为真实客户端来源字段。
