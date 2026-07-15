# ACCOUNT-DEVICE-000001 设备游客账户与正式认证升级服务端需求及详细设计工单

创建日期：2026-07-15  
状态：已确认（1A、2A、3A，可进入开发）  
关联模块：账户登录、SocialIdentity、设备会话、可信设备、Apple、Google、手机号 OTP、邮箱 OTP  
优先级：P0  
需求类型：设备账户 / 游客模式改造 / 身份升级 / 账户切换

## 0. 开发前决策状态

以下 3 项均已确认并作为强制实施口径。数据库迁移、设备凭证模型、接口鉴权字段、身份域和账号切换逻辑均按 `1A + 2A + 3A` 实施。

### 决策 1：设备登录凭证强度（已确认 1A）

| 方案 | 说明 | 优点 | 风险 |
|---|---|---|---|
| **1A（已确认）** | `device_id` 作为安装标识，另生成 Keychain `device_secret`；服务端只存 secret 哈希，登录时校验 secret，并预留 App Attest/DeviceCheck | 即使日志或普通接口泄露 device_id，也不能接管账户 | 客户端和服务端多一个密钥字段及轮换逻辑 |
| 1B | 使用 `device_id + App Attest/DeviceCheck` | 安全性最高，抗伪造能力强 | 接入和异常降级复杂，模拟器/旧系统需兼容 |
| 1C | 仅使用 `device_id` 登录 | 实现最简单 | device_id 实质变成永久密码；日志、抓包、备份泄露后可直接接管账户，不建议上线 |

确认结果：采用 `1A`。禁止把裸 `device_id` 作为唯一登录凭证；客户端必须生成并安全保存高熵 `device_secret`，服务端只能保存其安全哈希。

### 决策 2：设备身份的应用隔离范围（已确认 2A）

| 方案 | SocialIdentity 唯一维度 | 结果 |
|---|---|---|
| **2A（已确认）** | `identity_scope + provider=device + device_id` | 与现有账号身份域规则一致；Health 与 MedicineBox 若配置为同一 scope，则共享设备账户 |
| 2B | `真实 bundle_id + provider=device + device_id` | 两个 App 各自拥有设备账户；需改变 `SocialIdentity.bundle_id` 只存 identity_scope 的既有语义，或新增 `source_bundle_id` 唯一字段 |
| 2C | `platform + device_id`，跨 bundle 共享 | 范围最大，但误合并和凭证碰撞风险最高，不建议 |

确认结果：采用 `2A`。设备身份必须使用 identity scope；不得按真实 bundle_id 各自创建身份。

### 决策 3：正式身份已属于其他用户时，原设备账户如何处理（已确认 3A）

| 方案 | 处理 | 结果 |
|---|---|---|
| **3A（已确认）** | 登录正式身份所属用户，不合并数据，保留原设备身份 | 客户端完成账号切换；用户以后仍可通过游客入口回到原设备账户 |
| 3B | 登录正式身份所属用户，同时吊销原设备身份 | 逻辑更单一，但原设备账户数据将不可自行找回，必须提供恢复/迁移方案 |
| 3C | 阻止登录并要求用户先处理数据 | 数据最安全，但登录流程中断，产品与客服成本高 |

确认结果：采用 `3A`。正式身份已属于其他用户时，不得删除、吊销或迁移原设备身份。

## 1. 背景与问题

当前“游客模式”是客户端本地访客运行态，不创建服务端用户，也不具备完整账户、数据同步和主应用能力。目标是保留“游客模式”这一低门槛入口，但其技术含义改为“设备账户登录”：用户点击后，服务端按安装设备创建或查找一个真实 `User`，签发与 Apple、手机号、邮箱登录相同的 token 和设备会话，客户端进入完整应用。

设备账户后续使用 Apple、Google、手机号或邮箱完成首次正式认证时，应把该认证方式添加到当前设备账户，不创建新用户，保证设备账户已有数据仍属于同一 `user_id`。升级成功后删除设备 `SocialIdentity`，因此该设备不能再通过设备登录回到原账户；用户以后退出到登录页并再次点击“游客模式”时，服务端为同一设备创建新的游客账户。

若正式认证方式已经绑定其他有效用户，则不合并账户，直接登录该正式身份所属用户，由客户端执行完整账号切换。

## 2. 目标

1. `SocialIdentity.Provider` 增加 `DEVICE = "device"`。
2. 提供设备登录接口：同一身份范围内首次调用创建用户，再次调用返回同一用户。
3. 设备账户获得与正常登录完全一致的 JWT、`TrustedDevice`、`AccountDeviceSession`、审计、试用权益和完整业务权限。
4. Apple、Google、Phone、Email 登录统一执行“正式身份解析器”，原子判断登录既有用户、升级设备账户或创建新用户。
5. 正式身份首次添加且命中当前设备账户时，将正式身份绑定到设备账户，并删除设备身份。
6. 正式身份已绑定其他用户时，直接登录其他用户，不自动合并或搬迁数据。
7. 返回明确的账户解析结果，供客户端区分“原账户升级”和“切换到其他账户”。
8. 全流程可审计、可幂等、可处理并发登录与失败回滚。

## 3. 非目标

1. 不把两个已有正式账户的数据自动合并。
2. 不迁移设备账户与其他正式账户之间的业务数据。
3. 不把设备账户视为未认证请求；登录成功后它是服务端真实已登录用户。
4. 不允许客户端决定 SocialIdentity 归属或提交目标 `user_id`。
5. 不以客户端显示“未登录”作为服务端权限判断依据。
6. 本工单不新增客户端尚未提供的 Google/邮箱 UI，但服务端身份解析器必须覆盖已有及后续正式 provider。

## 4. 术语和判定规则

| 术语 | 定义 |
|---|---|
| 设备账户 | 仅拥有 `provider=device` 身份，或当前登录来源为 device 的真实用户 |
| 正式身份 | `apple`、`google`、`phone`、`email` SocialIdentity |
| 正式身份首次添加 | 当前 `identity_scope + provider + normalized_provider_uid` 不存在有效 SocialIdentity |
| 正式身份非首次添加 | 上述 SocialIdentity 已存在并绑定有效用户 |
| 当前设备身份 | `identity_scope + provider=device + provider_uid=device_id`，已按决策 2A 锁定 |
| 原账户升级 | 正式身份首次添加，且当前设备身份命中有效设备账户；正式身份绑定到该用户 |
| 账户切换 | 正式身份已属于其他用户；签发其他用户会话，不修改原设备账户数据 |

“首次”只能由服务端在事务内查询 SocialIdentity 判定，不能依赖客户端的 `is_first_login`、Apple 是否返回 email、OTP 是否首次发送或本地登录历史。

## 5. 当前代码与影响范围

| 文件 | 当前状态 | 本工单要求 |
|---|---|---|
| `SparkService/accounts/models.py:117-175` | LoginAudit 无 device provider；SocialIdentity 有 apple/google/phone/email | 增加 device provider、审计 provider；按已确认的决策 1A 增加设备凭证模型 |
| `SparkService/accounts/services/login_service.py` | Apple 独立执行查找/创建用户 | 接入统一正式身份解析器 |
| `SparkService/accounts/services/otp_service.py` | Phone、Email 各自执行查找/创建用户 | OTP 验证成功后接入统一解析器 |
| `SparkService/accounts/services/identity_scope_service.py` | 真实 bundle 解析到 identity_scope | 设备身份按已确认的决策 2A 使用同一规则 |
| `SparkService/accounts/services/device_session_service.py` | 为用户激活单 ACTIVE 设备会话并签发 token | 设备登录与正式登录完全复用 |
| `SparkService/accounts/models.py:20-114` | TrustedDevice 与 AccountDeviceSession 已区分设备画像和登录会话 | 保持职责不变，不用 TrustedDevice 代替登录身份 |
| `SparkService/accounts/auth/views.py` | 已有 Apple 登录，无设备登录 | 新增 device login view；正式登录响应增加 resolution |
| `SparkService/accounts/otp/views.py` | 已有 phone/email OTP 登录 | 保持接口，内部接入统一解析器 |

当前仓库未发现 Google 登录 endpoint；如 Google 在其他分支实现，必须调用同一解析器。若本期不提供 Google 登录，需保留服务层契约和测试，不伪造一个不可用接口。

## 6. 数据模型

### 6.1 SocialIdentity

```python
class Provider(models.TextChoices):
    APPLE = "apple"
    GOOGLE = "google"
    PHONE = "phone"
    EMAIL = "email"
    DEVICE = "device"
```

推荐存储：

```text
user_id      = 设备账户 User.id
provider     = device
provider_uid = 归一化后的 device_id
bundle_id    = identity_scope（决策 2A 已确认）
```

继续使用现有唯一约束：

```text
UNIQUE(bundle_id, provider, provider_uid)
```

设备 provider 不得出现在普通账号“登录方式管理”列表中，也不得作为绑定、修改或再认证方式。

### 6.2 设备凭证（决策 1A 已确认）

新增 `DeviceLoginCredential`，不要把 secret 明文写入 SocialIdentity：

| 字段 | 规则 |
|---|---|
| `identity_scope` | 索引；与设备身份范围一致 |
| `device_id` | 安装标识，索引 |
| `secret_hash` | 服务端强哈希，不可逆 |
| `status` | `active / revoked` |
| `failed_attempts`、`locked_until` | 防暴力尝试 |
| `created_at`、`last_used_at`、`revoked_at` | 审计字段 |

首次建立凭证时，是否允许客户端自报 secret 必须受风控限制。推荐由客户端生成高熵随机 secret，首次登记结合现有 TrustedDevice 画像和 App Attest；服务端只保存哈希。

### 6.3 升级后的设备身份生命周期

设备账户 U1 成功升级为正式账户后，删除 U1 的 device SocialIdentity，但保留安装级设备凭证。删除结果只表示“该设备不能再通过 device provider 登录 U1”，不表示该设备永久禁止使用游客模式。

后续行为：

```text
U1 完成正式身份升级
-> 删除 U1 的 device SocialIdentity
-> 用户继续使用 U1 的正式会话
-> 用户退出并回到登录页
-> 再次点击游客模式
-> 服务端发现当前设备不存在 device SocialIdentity
-> 创建新的游客账户 U2，并建立 device SocialIdentity -> U2
```

U1 的业务数据、正式 SocialIdentity 和审计记录保持不变，只能通过升级后的 Apple、Google、Phone 或 Email 身份重新登录。不得因为同一 device_id 再次创建 U2 而把 U1 数据复制或迁移到 U2。

## 7. 设备登录接口

```http
POST /api/v1/auth/device/login/
Content-Type: application/json
```

推荐请求：

```json
{
  "bundle_id": "cn.Zhaodk.Health",
  "device_id": "installation-uuid",
  "device_secret": "high-entropy-keychain-secret",
  "attestation": "optional-app-attest-payload"
}
```

成功响应沿用登录标准字段，并新增账户语义：

```json
{
  "code": 0,
  "msg": "login_success",
  "data": {
    "user_id": 100,
    "access_token": "...",
    "refresh_token": "...",
    "token_type": "Bearer",
    "email": "",
    "display_name": "",
    "sign_in_method": "device",
    "is_device_account": true,
    "is_new_user": true,
    "account_resolution": "device_account_created"
  }
}
```

再次登录返回 `device_account_login`，`is_new_user=false`。

### 7.1 事务流程

```text
校验 bundle_id、device_id、设备凭证/证明
-> 解析 identity_scope
-> 锁定 device SocialIdentity 唯一维度
-> 若 device identity 指向有效用户：登录该用户
-> 若指向 inactive 用户：创建新用户并原子重绑，保留旧用户审计
-> 若不存在：创建 User + device SocialIdentity
-> 关联 TrustedDevice、处理试用权益
-> 激活 AccountDeviceSession 并签发 token
-> 写 LoginAudit(provider=device)
-> 返回完整会话
```

用户创建、SocialIdentity 创建和唯一冲突处理必须位于同一事务；并发首次点击只能成功创建一个用户。发生唯一冲突时重新读取赢家身份，不得遗留无身份的孤儿 User。

### 7.2 错误码建议

| HTTP / code | msg | 客户端处理 |
|---|---|---|
| 400 / `40061` | `bundle_id_or_device_id_required` | 提示无法使用游客模式 |
| 401 / `40161` | `device_credential_invalid` | 清理无效本地 secret，禁止静默循环重试 |
| 409 / `40961` | `device_identity_conflict` | 不自动创建第二账户；记录告警并允许有限重试 |
| 423 / `42361` | `device_login_temporarily_locked` | 展示稍后重试 |

## 8. 正式身份统一解析流程

新增单一服务，例如 `AccountLoginResolutionService.resolve_verified_identity(...)`。Apple、Google、Phone、Email 在各自凭证验证成功后调用；该服务只接收已经验证并归一化的 provider UID。

输入至少包含：

```text
provider
normalized_provider_uid
real_bundle_id
identity_scope
device_id
request_id
verified_claims
```

### 8.1 决策矩阵

| 正式身份 | 当前设备身份 | 处理 | account_resolution |
|---|---|---|---|
| 已绑定有效用户 U2 | 不存在或属于任意 U1 | 登录 U2；不改正式身份；按决策 3A 保留原设备身份 | `existing_identity_login` |
| 不存在 | 存在且属于有效 U1 | 把正式身份创建到 U1；删除 device identity；登录 U1 | `device_account_upgraded` |
| 不存在 | 不存在 | 按现有正式登录注册流程创建 U3 和正式身份 | `formal_account_created` |
| 指向 inactive 用户 | 任意 | 延续各 provider 既有 inactive 策略，但不得静默绑定 inactive 用户 | `formal_account_recreated` 或明确错误 |

“正式身份已绑定 U2”优先级高于设备身份命中 U1。禁止因为请求携带同一 device_id 就把 U2 的正式身份迁移给 U1。

### 8.2 原账户升级的原子顺序

```text
select_for_update 正式身份唯一维度
-> select_for_update 设备身份唯一维度
-> 再次确认正式身份不存在
-> 为设备账户创建正式 SocialIdentity
-> 删除 device SocialIdentity
-> 签发同一 user_id 的新会话
-> 提交事务
```

任一步失败必须整体回滚，不能出现“device identity 已删但正式 identity 未创建”的不可登录账户。

### 8.3 已绑定其他用户

按已确认方案 3A：

1. 正式身份属于 U2 时，直接为 U2 签发会话。
2. 不修改 U1 的 SocialIdentity、业务数据、订阅、成员关系或审计历史。
3. 返回 `previous_device_account_id` 仅供服务端审计；默认不向客户端暴露不必要的内部账号信息。
4. 响应 `account_resolution=existing_identity_login`，客户端通过新 `user_id` 与当前 session 比较并执行账户切换。
5. 不应在服务端响应中声称发生“账号合并”。

## 9. 登录响应契约

所有 Apple、Google、Phone、Email、Device 成功响应统一增加：

| 字段 | 类型 | 说明 |
|---|---|---|
| `sign_in_method` | string | 本次成功使用的 provider |
| `is_device_account` | bool | 登录后的账号是否仍只能通过 device 身份进入 |
| `account_resolution` | enum | 本次账户归属判定结果 |
| `is_new_user` | bool | 本次是否新建 Django User；升级设备账户时必须为 false |

`device_account_upgraded` 必须返回原 `user_id`。`existing_identity_login` 返回正式身份所属 `user_id`。

`build_current_session()` 当前在无正式 provider 时回退为 apple，必须改为正确返回 `device`，并覆盖 email/google。服务端不能通过 provider 优先级猜测“本次登录方式”；冷启动可返回账户类型与最近会话登录方式两个独立字段。

## 10. 权限、退出与生命周期

1. 设备账户 token 权限与正式账户一致，可使用完整应用和所有普通业务 API。
2. `is_device_account` 只用于 UI 和身份升级提示，不得成为隐式降权标志。
3. 设备账户注销属于高风险操作；在没有正式认证方式时，需单独确认是否允许仅凭设备凭证注销。本工单默认不开放。
4. 正式升级后，现有 access/refresh token 应轮换；旧 device 登录会话必须撤销，防止旧 token 长期保留设备登录能力。
5. 退出登录只撤销会话，不删除仍有效的 device SocialIdentity；但已经升级并删除 device identity 的原账户不会因退出而恢复设备登录能力。
6. 升级后的用户退出并再次点击游客模式时，允许同一安装凭证创建新的设备账户；新账户与原正式账户完全隔离。
7. 设备 ID 丢失、Keychain 清空或换机时，未升级的设备账户无法恢复；客户端需明确提示风险，但本期不实现恢复申诉。

## 11. 审计、风控与隐私

1. `LoginAudit.LoginProvider` 增加 `DEVICE`。
2. 审计 `device_login_created`、`device_login_success`、`device_account_upgraded`、`device_account_recreated_after_upgrade`、`existing_identity_login_from_device_account`。
3. 日志只记录 device_id 的哈希或尾号，不记录 device_secret、完整 token、OTP、Apple identity token。
4. 设备登录接口按 device、IP、bundle、失败次数限流；创建用户的阈值严于普通重复登录。
5. 监控同一 device_id 在多个 IP/地区短时登录、同一证明异常并发创建多个账号，以及同一设备短期内反复“升级后新建游客账户”的滥用行为。
6. 设备账户数据属于服务端账户数据，隐私政策和注销说明不能继续称其为“仅保存在本机的游客数据”。

## 12. 兼容与迁移

1. 不迁移旧版纯本地游客聊天记录；若客户端需要迁移，必须另开数据导入工单。
2. 新字段需向后兼容旧客户端：新增响应字段不能改变现有字段含义。
3. 发布顺序：服务端模型与接口 -> 新客户端灰度 -> 监控 -> 全量。
4. 未升级客户端仍使用旧本地 GuestChat，不会自动创建服务端设备账户。
5. 回滚客户端时不得删除已创建的设备账户；服务端接口可保留但停止入口流量。

## 13. 验收标准

- [ ] 同一 bundle/scope + device 连续并发登录只产生一个 User 和一个 device SocialIdentity。
- [ ] 设备登录返回完整 token，可访问与 Apple/Phone 用户相同的受保护 API。
- [ ] 冷启动可通过 refresh token 恢复设备账户，`sign_in_method=device`。
- [ ] 正式身份首次添加时绑定到原设备 `user_id`，业务数据不变，`is_new_user=false`。
- [ ] 升级事务完成后原账户的 device SocialIdentity 已删除，旧设备会话已撤销。
- [ ] 升级后退出，再次调用 device login 会创建新的游客用户和 device SocialIdentity，且不能访问原账户数据。
- [ ] 正式身份已属于其他用户时返回该用户 token，不迁移原设备账户数据。
- [ ] Apple、Phone、Email 均通过统一矩阵；Google 接入存在时行为相同。
- [ ] 正式身份并发首次绑定不会绑定到两个用户，也不会删除错误的 device identity。
- [ ] inactive 用户、身份唯一冲突、数据库回滚、token 签发失败均有自动化测试。
- [ ] 审计日志不包含 secret、token、OTP 或完整第三方凭证。

## 14. 测试矩阵

| 场景 | 预期 |
|---|---|
| 新设备首次游客登录 | 创建 U1 + device identity，返回 U1 完整会话 |
| 同设备再次游客登录 | 返回 U1，不新建用户 |
| U1 首次 Apple/Phone/Email/Google | 正式 identity 绑定 U1，删除 U1 的 device identity |
| U1 升级过程事务失败 | U1 的 device identity 仍可用，正式 identity 不残留 |
| 正式 identity 已属于 U2 | 登录 U2；保留 U1 的 device identity，之后仍可通过游客入口返回 U1 |
| U1 升级并退出后再次游客登录 | 创建新的游客账户 U2；U1 只能通过正式身份登录 |
| 新游客账户 U2 再次游客登录 | 返回 U2，不重复建号 |
| 两请求同时用不同正式身份升级 U1 | 串行处理；结果符合“设备身份只能消费一次”的产品规则并有明确冲突响应 |
| device identity 指向 inactive 用户 | 不登录 inactive 用户；按明确策略新建或拒绝 |
| device_secret 错误/重放 | 拒绝并计数、限流 |
| App 重装但 Keychain 保留 | 恢复同一设备账户 |
| Keychain 丢失 | 视为新安装；不得猜测或接管旧账户 |

## 15. 上线与监控

建议通过 feature flag `device_account_login_enabled` 按 bundle 灰度。监控：设备登录成功率、用户创建率、升级后新游客账户创建率、异常并发重复建号数、升级成功率、升级回滚数、正式身份切换率、401/409/423 比例。

回滚触发：出现同一有效 device identity 同时归属多用户、正式身份错误迁移、升级后数据归属变化，或一次游客登录并发产生多个账户，立即关闭设备登录入口；不得通过删除数据库记录回滚。

## 16. 关联工单

1. `SparkClient/需求文档/账号/ACCOUNT-DEVICE-000001-游客模式设备账户登录与正式账号切换客户端需求工单.md`
2. `SparkService/需求文档/账号/ACCOUNT-LINKING-000001-多登录方式绑定与修改服务端需求及详细设计工单.md`
3. `SparkService/需求文档/账号/ACCOUNT-IDENTITY-000001-Health与MedicineBox账号身份共用需求及详细设计工单.md`

## 17. 服务端详细实现方案

### 17.1 目标架构

登录实现拆成三层，禁止在 Apple、Phone、Email、Google 各自复制用户查找、建号、绑定设备和签发 token 逻辑：

| 层级 | 职责 | 当前/目标实现 |
|---|---|---|
| Provider Credential Verifier | 验证 Apple token、Google token、OTP，并输出已归一化 provider_uid | `AppleIdentityService`、`PhoneNumberService`、OTP service、Google verifier |
| AccountLoginResolutionService | 统一判断已有正式账号、设备账号升级、新建正式账号 | 新增 `accounts/services/account_login_resolution_service.py` |
| DeviceSessionService | 关联 TrustedDevice、激活 AccountDeviceSession、签发 JWT | 复用 `accounts/services/device_session_service.py` |

### 17.2 逐文件改造清单

| 文件 | 改造内容 |
|---|---|
| `accounts/models.py` | 增加 `SocialIdentity.Provider.DEVICE`、`LoginAudit.LoginProvider.DEVICE`、`DeviceLoginCredential` |
| `accounts/migrations/0008_device_identity_login.py` | 增加 provider choice、设备凭证表和唯一索引 |
| `accounts/auth/serializers.py` | 增加 `DeviceLoginSerializer` |
| `accounts/auth/views.py` | 增加 `DeviceLoginView`，统一登录响应字段 |
| `accounts/urls.py` | 注册 `/auth/device/login/` |
| `accounts/services/device_credential_service.py` | secret 哈希校验、失败计数、锁定和轮换 |
| `accounts/services/device_login_service.py` | 设备身份查找、创建、幂等登录、会话签发 |
| `accounts/services/account_login_resolution_service.py` | 正式身份统一解析、设备账户升级、跨账号登录 |
| `accounts/services/login_service.py` | Apple 验证成功后调用统一解析器 |
| `accounts/services/otp_service.py` | Phone/Email OTP 验证成功后调用统一解析器 |
| `accounts/tests_device_account_login.py` | 设备登录、并发、升级、重新游客建号 |
| `accounts/tests_account_login_resolution.py` | Apple/Phone/Email/Google 决策矩阵 |

### 17.3 `DeviceLoginCredential` 模型

设备凭证属于安装，不属于 User。U1 升级后删除 U1 的 device SocialIdentity，但保留安装凭证，后续游客登录才能创建 U2。

建议字段：`identity_scope`、`device_id`、`secret_hash`、`status`、`failed_attempts`、`locked_until`、`last_used_at`、`last_used_ip`、`revoked_at`、`created_at`、`updated_at`。

数据库约束：`UNIQUE(identity_scope, device_id)`。`secret_hash` 使用 Django `make_password/check_password` 或 Argon2/PBKDF2，不保存明文，不使用裸 SHA-256 作为唯一保护。

实现约束：

1. `device_id` 只能用于索引和审计关联，不能单独签发 token。
2. 正常正式身份升级不吊销 `DeviceLoginCredential`，只删除原 User 的 device SocialIdentity。
3. `status=REVOKED` 仅用于安全事件或主动吊销，不用于正常升级。
4. 同一 scope/device 只能存在一条凭证，网络重试不能创建第二条。

### 17.4 设备凭证服务

服务端首次请求的顺序必须是：归一化 bundle/device -> 解析 identity_scope -> 锁定 `(identity_scope, device_id)` -> 无凭证则创建 secret_hash -> 有凭证则校验 secret -> 更新使用时间和失败信息。

客户端 secret 错误时增加 `failed_attempts`，达到阈值写入 `locked_until`。日志只能记录 device_id 哈希、失败原因和 request_id，不能记录 secret 或 secret_hash。

设备凭证轮换只允许在旧 secret 校验成功或正式身份强认证成功后进行，轮换不能改变 device SocialIdentity 的 User 归属。

### 17.5 SocialIdentity 存储

已确认的 2A 固定为：`bundle_id=IdentityScopeService.resolve(real_bundle_id)`、`provider=device`、`provider_uid=normalized_device_id`、`user_id=当前设备账户`。

继续使用现有唯一约束 `UNIQUE(bundle_id, provider, provider_uid)`。真实 bundle_id 仍写入 `LoginAudit`、`TrustedDevice` 和 `AccountDeviceSession`，不能把真实 bundle 改写成 identity scope。

### 17.6 设备登录事务流程

```text
校验 bundle_id、device_id、device_secret
-> 解析 identity_scope
-> 锁定/创建 DeviceLoginCredential
-> 锁定 scope + device + device_id
-> 命中 active device identity：登录原 User
-> 命中 inactive User：按注销策略创建新 User 并重绑
-> 未命中：创建 User + device SocialIdentity
-> 关联 TrustedDevice、处理试用权益
-> activate_and_issue_tokens()
-> 写 LoginAudit(provider=device)
-> 返回标准登录响应
```

创建 User、创建 SocialIdentity、凭证首次创建和 token 签发必须在 `transaction.atomic()` 内完成。并发首次请求只能创建一个 User；唯一冲突必须重新读取赢家，不能遗留孤儿 User。

## 18. 正式身份统一解析

新增 `AccountLoginResolutionService.resolve_verified_identity()`。它只接收已经验证完成的 provider UID，不能直接接收未验证的 Apple/Google token 或 OTP code。

解析顺序固定为：锁定 formal identity -> 锁定当前 scope/device identity -> formal identity 属于 active U2 时登录 U2 并保留 U1 device identity -> formal identity 不存在且 device identity 属于 active U1 时绑定到 U1 并删除 U1 device identity -> 两者都不存在时创建正式 User。

正式 identity 的优先级高于 device identity。不能因为请求携带 U1 的 device_id，就把已经属于 U2 的正式身份迁移给 U1。

统一返回字段：

| 场景 | `account_resolution` | `is_new_user` | `is_device_account` |
|---|---|---:|---:|
| 首次设备建号 | `device_account_created` | true | true |
| 设备重复登录 | `device_account_login` | false | true |
| 设备账户升级 | `device_account_upgraded` | false | false |
| 正式身份新建账号 | `formal_account_created` | true | false |
| 正式身份已有其他账号 | `existing_identity_login` | false | false |

### 18.1 Provider 接入点

Apple 保留 `accounts/services/login_service.py:300-505` 中的 audience、nonce、sub 和 email_verified 校验，校验成功后调用统一解析器。Apple email 只能回填空的 `User.email`，不能创建 Email SocialIdentity。

Phone 保留 `accounts/services/otp_service.py:568-750` 中的 OTP 锁定、使用标记和 E.164 归一化；用户查找/创建改为统一解析器。

Email 保留 `accounts/services/otp_service.py:369-565` 中的 lower-case 和 legacy `User.email` 兼容；Email SocialIdentity 的归属改由统一解析器完成。

当前仓库未发现完整 Google 登录 view。后续 Google 接入必须验证 issuer、audience、sub 后调用相同解析器，不能复制独立注册分支。

### 18.2 设备账户升级事务

```text
BEGIN
  select_for_update formal identity 唯一维度
  select_for_update device identity 唯一维度
  确认 formal identity 不存在
  创建 formal SocialIdentity -> U1
  删除 device SocialIdentity -> U1
  撤销旧 device AccountDeviceSession/refresh jti
  创建正式登录 session/token
COMMIT
```

不能删除 `DeviceLoginCredential`，因为同一安装之后还要创建新的游客账户；不能删除 TrustedDevice 历史记录，因为设备画像和审计仍需保留。任一步失败都必须回滚 identity 变化。

## 19. 服务端接口、错误码与迁移

设备接口：`POST /api/v1/auth/device/login/`。请求字段为 `bundle_id`、`device_id`、`device_secret`；响应沿用现有 token 字段，并增加 `sign_in_method`、`is_device_account`、`account_resolution`、`identity_scope`、`is_new_user`。

错误码：`40061 device_id_required`、`40062 device_secret_required`、`40063 device_id_invalid`、`40161 device_credential_invalid`、`42361 device_credential_locked`、`40961 device_identity_conflict`、`50361 device_login_store_unavailable`。

不再使用 `device_login_revoked` 表示正式升级后不能游客登录。正式升级后再次游客登录是正常的新游客账户创建。

建议 migration 为 `0008_device_identity_login.py`，增加 provider choice、DeviceLoginCredential 表、scope/device 唯一约束和索引，不迁移历史 User/TrustedDevice。

## 20. 服务端测试与发布

必须覆盖：首次设备建号、重复登录、响应丢失重试、Apple/Phone/Email 同账号升级、正式身份属于 U2 时保留 U1 device identity、U1 升级后再次创建 U2、U2 不能读取 U1 数据、并发建号、升级失败回滚、token 签发失败回滚、secret 错误锁定和日志脱敏。

发布顺序：数据库 migration -> 凭证服务和 device endpoint -> 正式身份统一解析器 -> 客户端 -> bundle 灰度。监控设备登录成功率、并发重复建号、升级成功率、升级后新游客账户创建率、跨账号切换率以及 401/409/423/503 比例。
