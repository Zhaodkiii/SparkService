# ACCOUNT-LINKING-000001 多登录方式绑定与修改服务端需求及详细设计工单

创建日期：2026-07-15  
关联模块：账户登录、账号管理、SocialIdentity、Apple 登录、手机号 OTP、邮箱 OTP、账号注销  
优先级：P0  
需求类型：账号安全 / 登录方式绑定 / 登录方式修改 / 多身份管理

## 1. 背景

当前 `accounts_socialidentity` 支持一个 `User` 关联多条第三方或手机号身份：

```text
user_id + provider + provider_uid + bundle_id
```

模型层允许同一用户同时拥有手机号登录、Apple 登录等多种登录方式。但当前登录注册流程主要是“登录时查找或创建用户”，缺少面向账号管理页的“绑定新登录方式”和“修改已绑定登录方式”接口。

客户端账号管理页需要展示邮箱、手机号、Apple 登录方式的绑定状态。未绑定时允许绑定；已绑定时，手机号和邮箱允许修改；Apple 本期只支持绑定，不支持修改或解绑。

## 2. 目标

1. 服务端提供账号登录方式列表接口，返回当前用户已绑定和可绑定的登录方式。
2. 服务端提供“先验证已有登录方式”的再认证接口，认证通过后签发一次性 `verification_ticket`。
3. 服务端提供绑定接口：用户完成目标手机号、邮箱或 Apple 验证后，将该登录方式绑定到当前用户。
4. 服务端提供修改接口：用户先验证旧方式，再验证新方式，校验通过后替换手机号或邮箱身份。
5. 绑定和修改前必须检查 `SocialIdentity` 中目标登录方式是否已绑定到其他有效用户。
6. 目标登录方式只绑定到已注销或 inactive 用户时，允许当前用户重新绑定。
7. 所有操作必须按 `ACCOUNT_IDENTITY_SCOPE_ALIASES` 解析账号身份作用域，与 `ACCOUNT-IDENTITY-000001` 保持一致。
8. Apple 登录流程不得覆盖已有账号邮箱；只有当前用户邮箱为空时，才允许用 Apple 已验证邮箱补写。

## 3. 非目标

1. 本工单不实现账号数据合并。
2. 本工单不允许用户在未登录状态下绑定或修改登录方式。
3. 本工单不默认支持 Apple ID 修改；Apple 修改需要先确认 Apple `sub` 和用户体验规则。
4. 本工单不改变现有登录接口的主流程。
5. 本工单不删除历史登录审计、OTP 记录或设备会话。

## 4. 当前代码位置

| 文件 | 当前职责 | 本工单影响 |
|---|---|---|
| `SparkService/accounts/models.py` | `SocialIdentity` 模型与唯一约束 | 新增 `EMAIL` provider，并迁移邮箱登录身份 |
| `SparkService/accounts/services/otp_service.py` | 手机号/邮箱 OTP 登录 | 可复用验证码发送与校验能力，但绑定场景需要新 scene |
| `SparkService/accounts/services/login_service.py` | Apple 登录与 token 签发 | 可复用 Apple token 验签，不能直接复用“首次登录创建用户”逻辑 |
| `SparkService/accounts/otp/views.py` | OTP 请求与校验 API | 可扩展绑定/修改 scene 或新建账号绑定专用 API |
| `SparkService/accounts/services/deactivation_service.py` | 注销相关身份处理 | inactive 用户身份释放规则需对齐 |
| `SparkService/accounts/services/identity_scope_service.py` | bundle 到身份作用域映射 | 绑定与修改必须使用 identity_scope 查询 SocialIdentity |

当前 Apple 登录存在一个需要在本工单内修复的问题：

```text
SparkService/accounts/services/login_service.py
LoginService.authenticate_apple_and_issue_tokens
```

当 Apple identity 命中已有 active 用户时，现有逻辑会使用 Apple token 中的 `email` 更新 `user.email`。如果用户已经通过邮箱绑定或其他流程登记了邮箱，这会导致账号邮箱被 Apple 登录返回的邮箱覆盖。

## 5. 核心业务规则

### 5.1 登录方式类型

目标展示和操作三类方式：

| 登录方式 | provider | provider_uid | 绑定 | 修改 |
|---|---|---|---|---|
| 手机号 | `phone` | 标准化 E.164 手机号 | 支持 | 支持 |
| 邮箱 | `email` | 标准化小写邮箱 | 支持 | 支持 |
| Apple | `apple` | Apple `sub` | 支持 | 暂不支持修改 |

已确认新增邮箱登录身份 provider：

```python
EMAIL = "email"
```

邮箱登录、邮箱绑定、邮箱修改统一使用 `SocialIdentity.Provider.EMAIL`。Django `User.email` 只作为系统用户资料邮箱，不作为邮箱登录身份来源。

邮箱身份强规则：

1. Apple 登录 token 中携带的 `email` 可以写入 Django `User.email`，但不能创建 `SocialIdentity(provider=email)`。
2. 只有用户主动完成邮箱绑定或邮箱修改流程，才能写入 `SocialIdentity(provider=email)`。
3. 用户主动绑定或修改邮箱成功时，必须同时更新 Django `User.email`。
4. 登录判断只认 `SocialIdentity(provider=email)`，不能因为 Django `User.email` 匹配就允许邮箱登录。

### 5.2 账号身份作用域

所有 `SocialIdentity` 查询和写入都必须使用身份作用域：

```text
identity_scope = IdentityScopeService.resolve(real_bundle_id)
```

真实 `bundle_id` 继续进入 OTP、审计、设备会话、通知上下文。

身份作用域必须来自统一配置：

```python
ACCOUNT_IDENTITY_SCOPE_ALIASES = {
    "cn.Zhaodk.Health": "cn.Zhaodk.Health",
    "cn.Zhaodk.MedicineBox": "cn.Zhaodk.Health",
}
```

要求：

1. `cn.Zhaodk.Health` 与 `cn.Zhaodk.MedicineBox` 的绑定状态、冲突检查、邮箱/手机号/Apple SocialIdentity 写入都落在同一个 `identity_scope=cn.Zhaodk.Health` 下。
2. 其他未配置 bundle_id 默认使用自身作为 identity_scope。
3. 接口请求和审计日志必须保留真实 `bundle_id`，不能把客户端真实 bundle 改写成 scope。
4. 禁止任何绑定、修改、登录方式列表接口直接使用真实 `bundle_id` 查询 `SocialIdentity`。
5. `identity_scope` 应在服务端响应中返回，便于客户端和日志排查共享账号状态。

### 5.3 再认证规则

绑定或修改前，用户必须先用“已绑定的任一登录方式”完成再认证。

再认证通过后，服务端签发一次性短效凭证：

```text
verification_ticket
```

建议属性：

| 属性 | 规则 |
|---|---|
| 有效期 | 5 分钟 |
| 使用次数 | 一次 |
| 绑定用户 | 当前登录用户 |
| 绑定 bundle | 当前请求真实 bundle_id 与 identity_scope |
| 绑定操作 | `bind_identity` / `change_identity` |
| 认证来源 | `phone` / `email` / `apple` |

后续绑定或修改接口必须携带该 ticket。

## 6. 接口设计

### 6.1 获取登录方式状态

```http
GET /api/v1/accounts/identities/
Authorization: Bearer <access_token>
```

返回：

```json
{
  "code": 0,
  "msg": "ok",
  "data": {
    "account_id": 100,
    "bundle_id": "cn.Zhaodk.Health",
    "identity_scope": "cn.Zhaodk.Health",
    "identities": [
      {
        "provider": "phone",
        "bound": true,
        "masked_value": "+86138****00",
        "modifiable": true,
        "bindable": false
      },
      {
        "provider": "email",
        "bound": false,
        "masked_value": "",
        "modifiable": false,
        "bindable": true
      },
      {
        "provider": "apple",
        "bound": true,
        "masked_value": "Apple ID",
        "modifiable": false,
        "bindable": false
      }
    ]
  }
}
```

### 6.2 请求再认证

手机号/邮箱再认证可复用 OTP 请求能力，但建议提供账号管理语义接口：

```http
POST /api/v1/accounts/identity-verification/request/
Authorization: Bearer <access_token>
```

请求：

```json
{
  "provider": "phone",
  "purpose": "bind_identity",
  "bundle_id": "cn.Zhaodk.Health",
  "device_id": "device-uuid"
}
```

返回：

```json
{
  "code": 0,
  "msg": "otp_sent",
  "data": {
    "otp_id": "otp-id",
    "expires_in": 300
  }
}
```

Apple 再认证由客户端发起 Sign in with Apple，服务端只需要校验完成接口。

### 6.3 完成再认证并签发 ticket

```http
POST /api/v1/accounts/identity-verification/verify/
Authorization: Bearer <access_token>
```

手机号请求：

```json
{
  "provider": "phone",
  "otp_id": "otp-id",
  "code": "123456",
  "purpose": "bind_identity",
  "bundle_id": "cn.Zhaodk.Health",
  "device_id": "device-uuid"
}
```

Apple 请求：

```json
{
  "provider": "apple",
  "identity_token": "apple-id-token",
  "authorization_code": "optional",
  "user_identifier": "apple-user-id",
  "purpose": "bind_identity",
  "bundle_id": "cn.Zhaodk.Health",
  "device_id": "device-uuid"
}
```

返回：

```json
{
  "code": 0,
  "msg": "verified",
  "data": {
    "verification_ticket": "one-time-ticket",
    "expires_in": 300
  }
}
```

校验规则：

1. 认证的 provider 必须已绑定当前用户。
2. OTP 目标值必须来自当前用户已绑定身份，不接受客户端传入任意手机号或邮箱作为旧身份。
3. Apple `sub` 必须命中当前用户已绑定的 Apple SocialIdentity。
4. ticket 必须绑定当前用户和 purpose。

### 6.4 绑定新登录方式

```http
POST /api/v1/accounts/identities/bind/
Authorization: Bearer <access_token>
```

手机号/邮箱绑定请求：

```json
{
  "provider": "phone",
  "target": "+8613800138000",
  "otp_id": "new-target-otp-id",
  "code": "123456",
  "verification_ticket": "one-time-ticket",
  "bundle_id": "cn.Zhaodk.Health",
  "device_id": "device-uuid"
}
```

Apple 绑定请求：

```json
{
  "provider": "apple",
  "identity_token": "apple-id-token",
  "authorization_code": "optional",
  "user_identifier": "apple-user-id",
  "verification_ticket": "one-time-ticket",
  "bundle_id": "cn.Zhaodk.Health",
  "device_id": "device-uuid"
}
```

绑定流程：

1. 校验 access token，确认当前用户。
2. 校验 `verification_ticket` 有效、未使用、属于当前用户、purpose=`bind_identity`。
3. 校验目标方式验证码或 Apple token。
4. 计算目标 `provider_uid`。
5. 使用 `IdentityScopeService.resolve(bundle_id)` 计算 identity_scope。
6. 查询 `SocialIdentity(identity_scope, provider, provider_uid)`。
7. 如果不存在，创建绑定到当前用户。
8. 如果存在且 user 是当前用户，返回幂等成功。
9. 如果存在且 user 是 active 其他用户，返回冲突错误。
10. 如果存在且 user 是 inactive 注销用户，允许重绑到当前用户。

示例：

```text
Health 绑定 +8613800138000 后，
MedicineBox 再绑定 +8613800138000 时，
必须命中同一条 identity_scope=cn.Zhaodk.Health 的 SocialIdentity，
不能新建 identity_scope=cn.Zhaodk.MedicineBox 的第二条身份。
```

### 6.5 修改手机号或邮箱

```http
POST /api/v1/accounts/identities/change/
Authorization: Bearer <access_token>
```

请求：

```json
{
  "provider": "phone",
  "new_target": "+8613900139000",
  "new_otp_id": "new-target-otp-id",
  "new_code": "123456",
  "verification_ticket": "one-time-ticket",
  "bundle_id": "cn.Zhaodk.Health",
  "device_id": "device-uuid"
}
```

修改流程：

1. 校验当前用户已绑定该 provider。
2. 校验 `verification_ticket` 有效，purpose=`change_identity`。
3. 校验新目标 OTP。
4. 使用 `IdentityScopeService.resolve(bundle_id)` 计算 identity_scope。
5. 检查新目标是否已被同一 identity_scope 下的其他 active 用户绑定。
5. 若新目标绑定 inactive 用户，允许释放并绑定当前用户。
6. 在事务中替换当前用户该 provider 的 SocialIdentity。
7. 手机号或邮箱修改成功后，返回最新登录方式列表。

Apple 修改暂不开放：

```json
{
  "code": 40071,
  "msg": "apple_identity_change_not_supported"
}
```

## 7. Apple 登录邮箱更新保护

### 7.1 问题说明

Apple 登录请求中，客户端会上送 `identity_token`。服务端验签后可从 payload 中读取：

```json
{
  "sub": "000082.xxxxx",
  "email": "97621528@qq.com",
  "email_verified": true,
  "aud": "cn.Zhaodk.Health"
}
```

该 email 可以作为 Apple 首次注册时的初始邮箱，也可以在老账号邮箱为空时补全。但它不能在已有账号已经登记邮箱的情况下直接覆盖 `user.email`。

否则会出现：

```text
用户原账号邮箱 = a@example.com
Apple 登录 token email = 97621528@qq.com
登录成功后 user.email 被覆盖成 97621528@qq.com
```

这会破坏邮箱绑定、账号管理展示和后续邮箱修改流程。

### 7.2 处理规则

| 场景 | 处理 |
|---|---|
| Apple 首次注册新用户 | 可使用 Apple token email 作为初始 `user.email` |
| Apple 命中已有 active 用户，`user.email` 为空 | 可使用 Apple token email 补写 |
| Apple 命中已有 active 用户，`user.email` 已存在 | 不更新 `user.email` |
| Apple 命中 inactive 用户并创建新用户 | 新用户可使用 Apple token email 作为初始邮箱 |
| Apple token 没有 email 或 `email_verified=false` | 不用该 email 覆盖已有账号邮箱 |
| 任意 Apple 登录场景 | 不创建、不更新 `SocialIdentity(provider=email)` |

### 7.3 推荐代码规则

Apple 登录已有用户分支应从：

```python
if email_from_token and user.email.lower() != email_from_token:
    user.email = email_from_token
    user.save(update_fields=["email"])
```

调整为：

```python
email_verified = payload.get("email_verified") in (True, "true", "1")
if not (user.email or "").strip() and email_from_token and email_verified:
    user.email = email_from_token
    user.save(update_fields=["email"])
```

注意：

1. 只允许补空值，不允许覆盖非空值。
2. 优先使用已验签 payload 中的 email，不信任客户端 body 的 email 覆盖账号邮箱。
3. 登录响应中的 `email` 应返回最终 `user.email`；如果用户已有邮箱，不能返回 Apple token email 误导客户端。
4. Apple email 仅表示 Apple credential 中携带的邮箱，不等价于用户主动绑定的邮箱登录方式。
5. Apple email 永远不作为邮箱登录身份写入 `SocialIdentity(provider=email)`。

### 7.4 与邮箱绑定的关系

本工单已确认新增 `SocialIdentity.Provider.EMAIL`，邮箱登录方式是否已绑定以 `SocialIdentity(provider=email)` 为准。

`user.email` 可以作为 Django 系统用户资料邮箱，但不能单独代表“邮箱登录方式已绑定”。

Apple 登录补写 `user.email` 时，不应自动创建 `provider=email` 的 SocialIdentity。用户要绑定邮箱登录，仍必须走邮箱绑定流程并完成邮箱 OTP 验证。

## 8. 冲突检查规则

查询：

```python
identity_scope = IdentityScopeService.resolve(real_bundle_id)
identity = SocialIdentity.objects.select_for_update().filter(
    bundle_id=identity_scope,
    provider=provider,
    provider_uid=provider_uid,
).select_related("user").first()
```

处理：

| 命中情况 | 行为 |
|---|---|
| 不存在 | 允许绑定 |
| 命中当前用户 | 幂等成功 |
| 命中其他 active 用户 | 拒绝 |
| 命中其他 inactive 用户 | 允许重绑 |

共享 scope 下，`cn.Zhaodk.Health` 与 `cn.Zhaodk.MedicineBox` 必须互相视为同一个账号空间。也就是说，Health 已绑定的手机号、邮箱、Apple，在 MedicineBox 绑定或修改时都算“已存在身份”。

建议错误：

```json
{
  "code": 40921,
  "msg": "identity_already_bound_to_active_user",
  "data": {
    "provider": "phone",
    "masked_target": "+86138****00"
  }
}
```

用户提示建议：

```text
该手机号已绑定其他账号，无法绑定或修改。如需继续，请先更换手机号或联系客服处理。
```

## 9. 注销用户重新绑定规则

如果目标身份只绑定到 inactive 用户，允许当前用户绑定，但必须保留审计日志。

推荐处理：

1. 不复活 inactive 用户。
2. 将目标 SocialIdentity 的 `user_id` 更新为当前用户。
3. 写入审计日志：旧 user_id、新 user_id、provider、masked target、request_id。
4. 如果 inactive 用户仍处于注销冷静期，需要确认业务规则是否允许立即释放登录身份。

## 10. 邮箱身份决策

已确认采用方案 A：新增 `SocialIdentity.Provider.EMAIL`，邮箱登录、绑定、修改统一走 SocialIdentity。

实施要求：

1. `accounts.models.SocialIdentity.Provider` 新增 `EMAIL = "email"`。
2. 邮箱 provider_uid 使用标准化小写邮箱。
3. 邮箱 OTP 登录成功后，优先按 `identity_scope + provider=email + provider_uid=email` 查找用户。
4. 邮箱 OTP 首次登录创建用户后，必须创建 `SocialIdentity(provider=email)`。
5. Django `User.email` 可同步写入当前用户资料邮箱，但不能替代 SocialIdentity 唯一约束。
6. 绑定和修改邮箱时必须走 `SocialIdentity(provider=email)` 冲突检查。
7. 历史仅有 `User.email`、没有 email SocialIdentity 的用户不能自动视为邮箱已绑定，必须通过用户主动邮箱 OTP 绑定后创建 SocialIdentity。
8. 邮箱登录、绑定、修改必须遵守 `ACCOUNT_IDENTITY_SCOPE_ALIASES`，Health 与 MedicineBox 共享同一 email SocialIdentity。

## 11. Apple 绑定决策

已确认采用方案 A：支持绑定 Apple，不支持修改 Apple，也不在本期支持解绑 Apple。

实施要求：

1. Apple 未绑定时，允许通过再认证后绑定 Apple。
2. Apple 已绑定时，账号管理页只展示已绑定状态。
3. 服务端不提供 Apple 修改能力。
4. 如客户端或接口请求 Apple 修改，返回 `apple_identity_change_not_supported`。
5. Apple 解绑、Apple 更换进入后续独立工单。

## 12. 验收标准

1. 当前用户可查询手机号、邮箱、Apple 三类登录方式绑定状态。
2. 未绑定手机号时，完成旧方式再认证和新手机号 OTP 验证后，可以绑定手机号。
3. 未绑定邮箱时，完成旧方式再认证和新邮箱 OTP 验证后，可以绑定邮箱。
4. 未绑定 Apple 时，完成旧方式再认证和 Apple token 验证后，可以绑定 Apple。
5. 已绑定手机号或邮箱时，可以先认证旧方式，再验证新目标并完成修改。
6. 目标手机号、邮箱或 Apple 已绑定其他 active 用户时，绑定和修改均被拒绝。
7. 目标身份只绑定 inactive 用户时，允许当前用户绑定。
8. 当前用户不能删除或修改到“没有任何登录方式”的状态。
9. 所有接口写入审计日志，包含 user_id、provider、identity_scope、真实 bundle_id、device_id、request_id。
10. Apple 登录命中已有 active 用户且 `user.email` 非空时，不覆盖账号邮箱。
11. Apple 登录命中已有 active 用户且 `user.email` 为空时，只在 token email 已验证的情况下补写邮箱。
12. Apple 登录响应中的 `email` 返回最终账号邮箱，不能返回未写入账号的 Apple token email。
13. 在 `ACCOUNT_IDENTITY_SCOPE_ALIASES` 中配置共享的 bundle 下，登录方式列表、绑定、修改、冲突检查必须返回同一套共享身份状态。
14. Apple 登录携带的 email 不得写入 `SocialIdentity(provider=email)`。
15. 邮箱登录只允许命中 `SocialIdentity(provider=email)`；仅匹配 Django `User.email` 不允许登录。

## 13. 测试建议

1. 同一用户绑定 phone + email + apple 三种身份。
2. 一个 active 用户已绑定手机号时，另一个用户绑定同手机号返回 `identity_already_bound_to_active_user`。
3. inactive 用户已绑定手机号时，active 用户可重新绑定。
4. 修改手机号时，旧手机号验证通过但新手机号 OTP 错误，不产生任何身份变更。
5. `verification_ticket` 重复使用失败。
6. `verification_ticket` 过期失败。
7. Health / MedicineBox 共享账号作用域下，绑定状态一致。
8. 其他 bundle_id 不受共享规则影响。
9. Apple 登录已有用户，用户已有邮箱 `old@example.com`，token email 为 `new@example.com`，登录后 `user.email` 仍为 `old@example.com`。
10. Apple 登录已有用户，用户邮箱为空，token email 已验证，登录后补写 `user.email`。
11. Apple 登录已有用户，用户邮箱为空但 token email 未验证，不补写 `user.email`。
12. Apple 登录补写 `user.email` 时，不自动创建 `provider=email` 的 SocialIdentity。
13. Health 绑定邮箱后，MedicineBox 登录方式列表显示邮箱已绑定。
14. MedicineBox 尝试绑定 Health 已绑定给其他 active 用户的手机号时，返回 `identity_already_bound_to_active_user`。
15. 未配置在 `ACCOUNT_IDENTITY_SCOPE_ALIASES` 的 bundle 使用同一邮箱登录时，不命中 Health / MedicineBox 的 email SocialIdentity。
16. Apple 首登写入 `user.email=apple@example.com` 后，邮箱登录 `apple@example.com` 仍失败，直到用户主动完成邮箱绑定。
17. 用户主动绑定邮箱成功后，同时存在 `SocialIdentity(provider=email)` 且 `user.email` 更新为该邮箱。

## 14. 代码改动清单与实现方案

### 14.1 必改文件

| 文件 | 改动 |
|---|---|
| `SparkService/accounts/models.py` | `SocialIdentity.Provider` 新增 `EMAIL = "email"`；新增再认证 ticket 模型或使用缓存实现 ticket |
| `SparkService/accounts/migrations/0007_*` | 增加 `EMAIL` provider 相关迁移；如新增 ticket 表，同步建表 |
| `SparkService/accounts/services/otp_service.py` | 邮箱 OTP 登录改为按 `identity_scope + provider=email + provider_uid=email` 查找/创建 SocialIdentity |
| `SparkService/accounts/services/login_service.py` | Apple 登录已有邮箱不覆盖；`build_current_session` 识别 `email` provider；必要时密码/identifier 查询支持 email identity |
| `SparkService/accounts/services/identity_scope_service.py` | 继续作为所有身份查询入口；本工单不新增第二套 scope 解析 |
| `SparkService/accounts/services/account_identity_service.py` | 新增，承载登录方式列表、再认证 ticket、绑定、修改、冲突检查 |
| `SparkService/accounts/identity/serializers.py` | 新增，定义登录方式列表、再认证、绑定、修改请求 serializer |
| `SparkService/accounts/identity/views.py` | 新增，提供 identities、verification、bind、change API |
| `SparkService/accounts/urls.py` | 挂载 `/accounts/identities/` 与 `/accounts/identity-verification/*` 路由 |
| `SparkService/accounts/tests_account_identity_linking.py` | 新增绑定、修改、冲突、ticket、共享 scope 测试 |
| `SparkService/accounts/tests_identity_scope.py` | 补充 email provider 与账号管理列表场景 |
| `SparkService/accounts/tests_apple_display_name.py` 或新测试 | 补 Apple 登录不覆盖已有邮箱测试 |

### 14.2 模型与迁移实现

`SocialIdentity.Provider` 增加：

```python
EMAIL = "email"
```

推荐新增 ticket 表，避免只用 cache 导致多进程或重启后难排查：

```text
AccountIdentityVerificationTicket
user
purpose              bind_identity / change_identity
verified_provider   phone / email / apple
identity_scope
bundle_id           真实客户端 bundle_id
device_id
ticket_hash
expires_at
used_at
request_id
created_at
```

技术要求：

1. ticket 明文只返回一次，数据库只保存 hash。
2. ticket 校验必须 `select_for_update()`，校验后立即写 `used_at`。
3. ticket 有效期建议 5 分钟。
4. ticket 绑定 `user_id + purpose + identity_scope`，不能跨用户、跨用途复用。

历史邮箱处理：

1. 不允许仅根据 `auth_user.email` 批量创建 email SocialIdentity。
2. `auth_user.email` 只能作为资料邮箱保留。
3. 历史用户需要邮箱登录能力时，必须在客户端账号管理页主动完成邮箱 OTP 绑定。
4. 如果后续必须迁移历史邮箱登录能力，需要单独工单和冲突审计清单，不能混入本工单默认实现。

### 14.3 AccountIdentityService 设计

新增文件：

```text
SparkService/accounts/services/account_identity_service.py
```

核心方法：

```python
class AccountIdentityService:
    list_identities(user, bundle_id) -> dict
    request_verification(user, provider, purpose, bundle_id, device_id, request_id) -> dict
    verify_and_issue_ticket(user, provider, proof, purpose, bundle_id, device_id, request_id) -> dict
    bind_identity(user, provider, target_proof, ticket, bundle_id, device_id, request_id) -> dict
    change_identity(user, provider, new_target_proof, ticket, bundle_id, device_id, request_id) -> dict
```

内部公共方法：

```python
resolve_identity_scope(bundle_id)
normalize_provider_uid(provider, value)
get_existing_identity(identity_scope, provider, provider_uid, for_update=False)
ensure_target_available_or_rebind_inactive(...)
mask_identity(provider, provider_uid)
```

所有读取/写入 `SocialIdentity` 的入口必须先执行：

```python
identity_scope = IdentityScopeService.resolve(bundle_id)
```

### 14.4 登录方式列表实现

接口：

```http
GET /api/v1/accounts/identities/?bundle_id=cn.Zhaodk.Health
Authorization: Bearer <access_token>
```

实现规则：

1. `bundle_id` 不传时，可从 header 或空值兜底；移动端必须传真实 bundle_id。
2. `identity_scope = IdentityScopeService.resolve(bundle_id)`。
3. 查询当前用户在该 scope 下的 `phone/email/apple` identities。
4. 返回三类固定 provider，不因为未绑定而缺行。
5. `email` 绑定状态只看 `SocialIdentity(provider=email)`，不看 `user.email`。
6. `user.email` 可作为资料邮箱字段返回，但不能影响 `bound`。

### 14.5 再认证实现

手机号/邮箱再认证：

1. 请求阶段不允许客户端传旧手机号或旧邮箱作为目标。
2. 服务端从当前用户已绑定 identities 中取 provider_uid。
3. 调用现有 OTP 发送能力，scene 使用：

```text
identity_reauth
```

4. verify 阶段校验 OTP 对应的旧身份属于当前用户。
5. 成功后签发 `verification_ticket`。

Apple 再认证：

1. 复用 `AppleIdentityService.verify_identity_token(...)`。
2. `aud` 校验真实 bundle_id。
3. `sub` 必须命中当前用户在 identity_scope 下的 Apple SocialIdentity。
4. 成功后签发 `verification_ticket`。

### 14.6 绑定实现

绑定手机号/邮箱：

1. 校验 ticket。
2. 校验新手机号/邮箱 OTP。
3. 标准化 provider_uid。
4. 在同一事务中 `select_for_update()` 查询目标 identity。
5. 不存在则创建 `SocialIdentity(user=current_user, bundle_id=identity_scope, provider, provider_uid)`。
6. 命中当前用户返回幂等成功。
7. 命中其他 active 用户返回 `identity_already_bound_to_active_user`。
8. 命中 inactive 用户则更新 `identity.user = current_user` 并记录审计。
9. provider=email 绑定成功后，同步更新 `current_user.email = provider_uid`。

绑定 Apple：

1. 校验 ticket。
2. 验签 Apple identity_token。
3. 计算 `provider_uid=payload["sub"]`。
4. 执行同一套冲突检查。
5. 创建或重绑 `SocialIdentity(provider=apple)`。
6. 不写入或覆盖 `SocialIdentity(provider=email)`。

### 14.7 修改实现

手机号/邮箱修改：

1. 校验当前用户在 identity_scope 下已绑定该 provider。
2. 校验 ticket。
3. 校验新目标 OTP。
4. 对新目标执行冲突检查。
5. 事务内更新当前用户该 provider 的 `provider_uid`，或删除旧 identity 后创建新 identity。
6. 推荐更新原 identity 行，保留 id 与审计连续性。
7. 成功后同步 `user.email` 资料字段，仅限 provider=email。

Apple 修改：

1. 不提供修改入口。
2. API 收到 `provider=apple` 且 action=change 时返回 `apple_identity_change_not_supported`。

### 14.8 Apple 登录邮箱保护实现

修改 `LoginService.authenticate_apple_and_issue_tokens` 中已有用户分支。

目标规则：

```python
email_verified = payload.get("email_verified") in (True, "true", "1")
if not (user.email or "").strip() and email_from_token and email_verified:
    user.email = email_from_token
    user.save(update_fields=["email"])
```

响应：

```python
result["email"] = user.email or ""
```

不能使用 `chosen_email` 把未写入账号的 Apple token email 返回给客户端。
不能在 Apple 登录流程内创建或更新 `SocialIdentity(provider=email)`。

### 14.9 邮箱 OTP 登录迁移实现

修改 `OTPService.verify_email_otp_and_issue_tokens`：

1. 标准化 `email = email.strip().lower()`。
2. `identity_scope = IdentityScopeService.resolve(bundle_id)`。
3. 先查 `SocialIdentity(bundle_id=identity_scope, provider=email, provider_uid=email)`。
4. 命中 active 用户则登录该用户。
5. 命中 inactive 用户返回 `user_inactive` 或按注销释放规则处理，需与产品确认。
6. 未命中时，不允许因为 `User.email=email` 就登录该用户。
7. 未命中时按首次邮箱 OTP 登录处理，创建新用户，并创建 email SocialIdentity。
8. 如果该邮箱只是某个 Apple 登录用户的 `User.email`，仍不能命中该 Apple 用户，除非该用户主动绑定过 email SocialIdentity。

### 14.10 错误码

| msg | HTTP | code | 场景 |
|---|---:|---:|---|
| `identity_already_bound_to_active_user` | 409 | 40921 | 目标身份已绑定其他 active 用户 |
| `verification_ticket_expired` | 400 | 40081 | ticket 过期 |
| `verification_ticket_used` | 400 | 40082 | ticket 已使用 |
| `verification_ticket_invalid` | 400 | 40083 | ticket 不存在或不属于当前用户 |
| `identity_not_bound` | 400 | 40084 | 修改前当前用户未绑定该 provider |
| `apple_identity_change_not_supported` | 400 | 40071 | Apple 修改 |

## 15. 建议拆分任务

| 任务 | 负责人 | 说明 |
|---|---|---|
| 新增登录方式状态接口 | 后端 | 返回 phone/email/apple 绑定状态与可操作性 |
| 新增再认证 ticket 机制 | 后端 | 绑定和修改前置安全校验 |
| 新增绑定接口 | 后端 | 支持 phone/email/apple |
| 新增修改接口 | 后端 | 支持 phone/email，Apple 暂不开放 |
| 邮箱 SocialIdentity 实现与迁移 | 后端 | 新增 `email` provider，迁移邮箱登录到 SocialIdentity |
| Apple 登录邮箱覆盖保护 | 后端 | 已有邮箱不覆盖，空邮箱仅用已验证 token email 补写 |
| 冲突与 inactive 用户释放规则 | 后端 | active 冲突拒绝，inactive 允许重绑 |
| 审计日志与错误码 | 后端 | 支持客服排查 |
| 自动化测试 | 后端测试 | 覆盖绑定、修改、冲突、ticket、共享 scope |
