# SUBSCRIPTION-REVENUECAT-000001 RevenueCat 订阅与服务端 Pro 权益同步需求确认工单

> 工单状态：代码落地完成，待部署配置与人工验收  
> 当前阶段：已完成服务端、iOS 与后台运营页面实现；按约定未编译或执行测试  
> 创建日期：2026-09-22  
> 适用系统：SparkService、LookHealthClient/SparkClient、RevenueCat、Apple App Store  
> 关联 RevenueCat Entitlement：`健康Pro`  
> 关联 RevenueCat Offering：`standard`

## 1. 需求背景

Look Health iOS 客户端已经接入 RevenueCat SDK、Paywall 和购买恢复能力，并在 SparkService 账号登录成功后调用 RevenueCat `logIn` 绑定用户身份。当前服务端 `is_pro` 仍只由内部 `TrialApplication` 判断，尚未接收 RevenueCat Webhook，也没有 RevenueCat 订阅快照、主动同步和定时对账能力。

这会形成两个彼此独立的 Pro 状态源：

- iOS 从 RevenueCat `CustomerInfo` 得到 `健康Pro` entitlement；
- SparkService 从内部试用记录得到 `is_pro`。

用户完成 Apple 订阅后，客户端可能已经显示 Pro，但服务端仍返回 `is_pro=false`；续费、退款、订阅转移、关闭续费和账单宽限期发生时，服务端也无法在 App 不在线的情况下更新权限。

本工单建立 RevenueCat 与 SparkService 的完整订阅同步架构，使 Apple 订阅、内部试用和后台人工授权保持来源隔离，并由统一解析器计算最终 Pro 权限。

## 2. 用户目标与问题范围

### 2.1 用户目标

1. RevenueCat Customer 必须与 SparkService 登录用户形成稳定的一对一身份关系。
2. iOS 购买完成后，服务端 Pro 权限应尽快生效。
3. 续费、退款、过期、账单问题和订阅转移应在 App 不在线时同步到服务端。
4. SparkService 应通过 RevenueCat 服务端 API 校验当前订阅事实，不能相信客户端上传的 `isPro` 或 `CustomerInfo`。
5. 服务端所有 Pro 权限判断必须收敛到统一入口。
6. RevenueCat 订阅、内部试用和后台人工授权必须分开保存，任何单一来源失效都不能错误覆盖其他有效来源。

### 2.2 最终权限规则

```text
effective_is_pro =
    RevenueCat 健康Pro entitlement 有效
    OR 内部 TrialApplication 有效
    OR 后台人工授权有效
```

### 2.3 数据所有权

| 数据 | 事实来源 | 用途 |
|---|---|---|
| Apple 交易与订阅生命周期 | Apple App Store，经 RevenueCat 汇总 | 支付订阅事实 |
| RevenueCat Customer、Subscription、Entitlement | RevenueCat | 跨设备订阅状态和服务端对账 |
| 内部试用 | SparkService `TrialApplication` | 非付费试用权益 |
| 后台人工授权 | SparkService 后台权益记录 | 客服、运营或特殊授权 |
| `effective_is_pro` | SparkService `ProEntitlementResolver` | 服务端业务鉴权与会话返回 |
| iOS 即时展示状态 | RevenueCat `CustomerInfo` | 购买反馈、Paywall 和本地 UI |

## 3. 当前代码事实

### 3.1 iOS 已实现事实

1. `SparkClientApp` 启动时调用 `RevenueCatClient.shared.configure()`。
2. `RevenueCatClient.configure()` 使用 RevenueCat Public SDK Key 配置 Purchases SDK。
3. SparkService 会话恢复或登录成功后，`AppLifecycleCoordinator.runSignedInPreparation` 调用：

   ```swift
   try await RevenueCatClient.shared.identify(accountID: session.accountID)
   ```

4. `RevenueCatClient.identify` 当前实现为：

   ```swift
   _ = try await Purchases.shared.logIn(String(accountID))
   ```

5. 退出 SparkService 账号时调用 `Purchases.shared.logOut()`，RevenueCat 会进入匿名身份。
6. 客户端 entitlement 标识为 `健康Pro`，offering 标识为 `standard`。
7. 设置页已经能够加载 Offering、打开 RevenueCat Paywall、恢复购买和读取 `CustomerInfo`。
8. Paywall 已归入 `SignedInMainTabHostView` 的统一 `HomeFullScreenCover` 路由，订阅区不再自行叠加第二个 `fullScreenCover`。
9. `UserSession` 已包含 `isPro: Bool`，但它来自 SparkService 登录/当前会话响应，不会被 RevenueCat 客户端状态自动写回。

### 3.2 SparkService 已实现事实

1. `TrialApplication` 保存内部 Pro 试用状态、授权来源、开始时间和过期时间。
2. 实施前，`TrialService.is_pro_user` 只判断有效内部试用：

   ```python
   trial = getattr(user, "trial_application", None)
   trial = TrialService.ensure_status_fresh(trial=trial)
   return bool(trial and trial.is_active_trial())
   ```

3. 现已将 `LoginService._apply_is_pro`、`LoginService.build_current_session`、Apple Web 登录结果、AI 配置接口及后台 Pro 汇总切换至 `ProEntitlementResolver`；`TrialService` 仅作为内部试用/人工授权来源参与解析。
4. 后台管理系统已经能够展示和操作内部 Pro 试用，但该模型不是 Apple 付费订阅模型。
5. 已新增独立 `subscriptions` Django app，保存 RevenueCat 身份、别名、权益快照及 Webhook Inbox。
6. 已新增 RevenueCat Webhook endpoint、Webhook 事件幂等表、服务端 API Client、Celery 异步处理与 6 小时对账任务。

### 3.3 RevenueCat 当前集成事实

1. 当前 SDK 在获得 SparkService 会话前先匿名配置，登录后再通过 `logIn(String(accountID))` 识别用户。
2. 因此 RevenueCat Customer 可能同时包含自定义 App User ID 和 `$RCAnonymousID:` alias。
3. Webhook 用户解析不能只看 `app_user_id`，还必须检查 `original_app_user_id`、`aliases`，并为 `TRANSFER` 处理转入和转出 ID。

## 4. 已知偏差与风险

| 编号 | 偏差或风险 | 当前影响 | 目标处理 |
|---|---|---|---|
| R1 | 服务端只认内部试用 | 已购买用户可能仍不是服务端 Pro | 增加 RevenueCat 权益快照和统一解析器 |
| R2 | 没有 Webhook | 续费、退款、过期无法后台同步 | 增加带认证、幂等和异步处理的 Webhook |
| R3 | 没有购买后主动同步 | 依赖 Webhook 会产生生效延迟 | iOS 购买/恢复完成后调用服务端 sync |
| R4 | 没有定时对账 | Webhook 最终失败后会长期不一致 | Celery 定时对账和失败补偿 |
| R5 | 事件可能重复或乱序 | 旧事件可能覆盖新状态 | `event.id` 唯一约束；事件只触发服务端查询当前事实 |
| R6 | `CANCELLATION` 不等于到期 | 提前回收用户权益 | 以当前 active entitlement 为准，不直接按事件类型授权/撤权 |
| R7 | Sandbox 污染正式权益 | 测试购买可能解锁正式账号 | 已确认 Sandbox 只保存和测试，永远不参与正式 `effective_is_pro` |
| R8 | RevenueCat Secret Key 泄漏 | 可访问敏感客户/订阅接口 | Secret Key 只进入服务端环境变量和密钥管理 |
| R9 | 当前 App User ID 是可递增 accountID | ID 可猜测且与 RevenueCat 官方建议不一致 | 已确认保持 `String(accountID)`；服务端接口不得允许未鉴权的任意用户订阅查询 |
| R10 | 多来源权益可能互相覆盖 | 试用结束可能误关有效订阅 | 每个来源独立存储，最终取逻辑 OR |

## 5. 已确认总体架构

```text
┌─────────────┐
│   iOS App   │
│             │
│ 登录用户     │
│ 打开 Paywall │
│ 完成购买     │
└──────┬──────┘
       │ Purchases.logIn(rcAppUserID)
       │ StoreKit purchase
       ▼
┌─────────────────┐
│   RevenueCat    │
│                 │
│ Customer        │
│ Subscription    │
│ 健康Pro         │
│ Entitlement     │
└──────┬──────────┘
       │
       ├── Webhook：续费、过期、退款、转移
       │
       └── REST API：服务端主动查询当前状态
                     │
                     ▼
┌──────────────────────────┐
│       SparkService       │
│                          │
│ RevenueCatWebhookEvent   │
│ RevenueCatEntitlement    │
│ TrialApplication         │
│ 后台人工授权              │
│                          │
│ ProEntitlementResolver   │
└─────────────┬────────────┘
              │
              ▼
       effective_is_pro
              │
      ┌───────┴────────┐
      │ API 权限检查    │
      │ UserSession     │
      │ AI Pro 功能     │
      └────────────────┘
```

架构决策：

1. RevenueCat 是 Apple 付费订阅事实来源。
2. SparkService 是 Look Health 业务权限事实来源。
3. iOS `CustomerInfo` 只负责即时 UI 和购买反馈，不是服务端授权凭证。
4. Webhook 是后台生命周期同步入口，但不直接按事件类型改最终 Pro。
5. SparkService 收到变化通知后查询 RevenueCat 当前 active entitlement，再更新本地快照。
6. 购买后主动同步用于缩短生效时间。
7. 定时对账用于最终一致性和灾难恢复。

## 6. 初步业务流程

### 6.1 登录与 RevenueCat 身份绑定

```text
iOS 完成 SparkService 登录/会话恢复
  → 获得 accountID
  → Purchases.logIn(String(accountID))
  → 获取 CustomerInfo
  → 客户端更新本地订阅展示
  → SparkService UserSession.isPro 仍来自 ProEntitlementResolver
```

身份绑定失败不得阻塞正常登录，但必须记录脱敏日志并允许后续前台重试。

### 6.2 购买完成后主动同步

```text
PaywallView.onPurchaseCompleted
  → 客户端确认 健康Pro entitlement active
  → POST /api/v1/subscriptions/revenuecat/sync
  → SparkService 从 request.user 取得 RevenueCat 身份
  → SparkService 调 RevenueCat Secret API
  → 原子更新 RevenueCatEntitlement
  → ProEntitlementResolver 重新计算 effective_is_pro
  → 返回订阅摘要
  → iOS 刷新 UserSession/订阅状态
```

客户端不得上传可信的 `app_user_id`、`isPro`、过期时间或产品状态。服务端必须从当前鉴权用户解析身份并向 RevenueCat 查询。

### 6.3 Webhook 同步

```text
RevenueCat POST Webhook
  → 读取原始请求体
  → 验证 Authorization/HMAC 和时间窗口
  → 校验 project、app、environment
  → 按 event.id 幂等写入 Inbox
  → 快速返回 HTTP 200
  → Celery 异步解析 app_user_id/original_app_user_id/aliases
  → 找到 SparkService 用户
  → 调 RevenueCat API 查询当前 active entitlement
  → 更新本地快照
  → 标记事件 processed 或 failed
```

### 6.4 定时对账

定时任务扫描：

- 本地状态为 active 且临近/超过 `expires_at` 的记录；
- Webhook 处理失败或身份无法解析的事件；
- 超过 24 小时未同步的活跃订阅；
- 最近发生过退款、转移或人工 RevenueCat entitlement 变更的用户。

建议初始频率为每 6 小时；正式频率需要结合用户量、RevenueCat API 限流和 Celery 容量确认。

## 7. 初步数据模型方案

计划新增独立 `subscriptions` Django app。以下为设计草案，不是当前已实现代码。

### 7.1 `RevenueCatCustomerIdentity`

```python
class RevenueCatCustomerIdentity(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="revenuecat_identity",
    )
    app_user_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

约束：

- 一个 SparkService User 只对应一个主 RevenueCat App User ID；
- 一个 App User ID 不能属于多个 SparkService User；
- `app_user_id` 固定写入 `str(user.id)`，不增加 UUID、HMAC 或额外外部用户 ID；
- 已有 RevenueCat Customer 和历史订阅继续沿用数字 ID，不执行身份迁移；
- `RevenueCatCustomerIdentity` 是显式映射、唯一约束和审计记录，不改变现有 ID 生成规则；
- RevenueCat alias 不直接创建第二个用户；如需保存 alias，应新增独立 alias 表或受控 JSON 快照；
- 不使用邮箱、手机号、Apple subject 或 device ID 作为 RevenueCat App User ID。

### 7.2 `RevenueCatEntitlement`

```python
class RevenueCatEntitlement(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active"
        EXPIRED = "expired"
        REVOKED = "revoked"
        UNKNOWN = "unknown"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="revenuecat_entitlements",
    )
    entitlement_id = models.CharField(max_length=100)
    status = models.CharField(max_length=16, choices=Status.choices)
    product_id = models.CharField(max_length=255, blank=True)
    store = models.CharField(max_length=32, blank=True)
    environment = models.CharField(max_length=16)
    period_type = models.CharField(max_length=32, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    will_renew = models.BooleanField(default=False)
    original_transaction_id = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
    )
    provider_updated_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "entitlement_id", "environment"],
                name="unique_rc_user_entitlement_environment",
            )
        ]
```

规则：

- Production 和 Sandbox 必须分行保存；
- 正式服务端 `effective_is_pro` 只读取 Production，不提供按客户端参数切换到 Sandbox 的能力；
- Sandbox 快照仅用于联调、审计和自动化测试，不得提升正式用户权限；
- `status=active` 仍需同时满足 `expires_at is null or expires_at > now`；
- 订阅关闭自动续费但仍未到期时保持 active，`will_renew=false`；
- Webhook 原始事件不能直接覆盖较新的 Provider 快照。

### 7.3 `RevenueCatWebhookEvent`

```python
class RevenueCatWebhookEvent(models.Model):
    class ProcessStatus(models.TextChoices):
        RECEIVED = "received"
        PROCESSING = "processing"
        PROCESSED = "processed"
        FAILED = "failed"

    event_id = models.CharField(max_length=100, unique=True, db_index=True)
    event_type = models.CharField(max_length=64)
    app_user_id = models.CharField(max_length=100, db_index=True)
    environment = models.CharField(max_length=16)
    event_timestamp_ms = models.BigIntegerField()
    payload = models.JSONField()
    process_status = models.CharField(max_length=16)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
```

规则：

- `event_id` 是 Webhook Inbox 幂等键；
- 重复事件返回 200，不重复执行业务更新；
- 原始 payload 仅用于审计和重放，不作为当前权限快照；
- payload 和日志不得额外复制 Secret、Authorization Header 或不需要的个人信息；
- 失败事件保留可重试状态和脱敏错误原因。

## 8. 初步服务端核心服务

### 8.1 `RevenueCatClient`

职责：

- 使用服务端 Secret API Key 调用 RevenueCat API；
- 查询 Customer 当前 active entitlements 和必要的订阅详情；
- 统一超时、重试、429、5xx、协议解码和日志脱敏；
- 不承担本地数据库写入和最终 Pro 判断。

设计接口：

```python
class RevenueCatClient:
    def get_active_entitlements(self, *, app_user_id: str):
        """调用 RevenueCat API v2，返回规范化 active entitlement 列表。"""
```

服务端配置至少包括：

```text
REVENUECAT_SECRET_API_KEY
REVENUECAT_PROJECT_ID
REVENUECAT_APP_ID
REVENUECAT_WEBHOOK_AUTHORIZATION
REVENUECAT_WEBHOOK_HMAC_SECRET
REVENUECAT_ENTITLEMENT_ID=<RevenueCat-v2-internal-entitlement-id>
REVENUECAT_ENTITLEMENT_IDENTIFIER=健康Pro
```

真实 Secret 不得写入代码、工单、客户端、日志或数据库业务表。

### 8.2 `RevenueCatSubscriptionSyncService`

职责：

- 按 SparkService User 加载 RevenueCat 身份；
- 查询 RevenueCat 当前事实；
- 原子更新 entitlement 快照；
- 对查询失败保持上一次已验证状态，不把网络失败当作订阅过期；
- 返回 `ProEntitlementResolver` 的最终结果。

设计示例：

```python
class RevenueCatSubscriptionSyncService:
    @transaction.atomic
    def sync_user(self, *, user):
        identity = RevenueCatCustomerIdentity.objects.select_for_update().get(
            user=user,
        )
        active_entitlements = revenuecat_client.get_active_entitlements(
            app_user_id=identity.app_user_id,
        )
        update_local_entitlement_snapshot(
            user=user,
            entitlements=active_entitlements,
        )
        return ProEntitlementResolver.resolve(user=user)
```

### 8.3 `ProEntitlementResolver`

服务端所有业务代码必须通过该服务判断 Pro，不再分别查询 RevenueCat、试用或人工授权表。

```python
class ProEntitlementResolver:
    @staticmethod
    def resolve(*, user):
        revenuecat_active = RevenueCatEntitlement.objects.filter(
            user=user,
        entitlement_identifier="健康Pro",
        environment="production",
            status="active",
        ).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        ).exists()

        trial = TrialService.build_pro_summary(user=user)
        trial_active = trial["is_pro"]
        manual_active = trial_active and trial["grant_source"] == "manual"

        return {
            "is_pro": revenuecat_active or trial_active or manual_active,
            "revenuecat_active": revenuecat_active,
            "trial_active": trial_active,
            "manual_active": manual_active,
        }
```

说明：当前后台人工授权仍复用了 `TrialApplication` 的 manual grant 语义。是否在本期拆成独立人工授权模型，需要后续问题确认；在拆分前，解析器不得重复计算同一条记录。

## 9. 初步接口契约

### 9.1 查询当前订阅与有效 Pro

```http
GET /api/v1/subscriptions/me
Authorization: Bearer <SparkService access token>
```

成功响应草案：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "isPro": true,
    "effectiveSource": "revenuecat",
    "sources": [
      {
        "type": "revenuecat",
        "active": true,
        "entitlement": "健康Pro",
        "productId": "health_yearly_99_intro3days_free",
        "expiresAt": "2027-09-22T12:00:00Z",
        "willRenew": true
      },
      {
        "type": "trial",
        "active": false,
        "expiresAt": null
      }
    ],
    "lastSyncedAt": "2026-09-22T12:00:05Z"
  }
}
```

### 9.2 当前登录用户主动同步

```http
POST /api/v1/subscriptions/revenuecat/sync
Authorization: Bearer <SparkService access token>
Idempotency-Key: <client generated UUID>
Content-Type: application/json

{}
```

规则：

- 不接受客户端传入的 `app_user_id`；
- 不接受客户端传入的 `isPro` 或 entitlement 状态；
- 服务端从 `request.user` 查找身份；
- 同一用户并发同步应合并、加锁或短时限流；
- RevenueCat 暂时不可用时返回稳定业务错误，不删除上一次有效快照；
- 成功响应复用 `/subscriptions/me` 的订阅摘要结构。

初步业务错误：

| HTTP | 业务码 | 标识 | 说明 |
|---|---:|---|---|
| 401 | 40101 | `authentication_required` | 未登录或 Token 失效 |
| 404 | 40481 | `revenuecat_identity_not_found` | 当前用户尚未建立 RevenueCat 身份 |
| 409 | 40981 | `subscription_sync_in_progress` | 当前用户已有同步任务执行中 |
| 429 | 42981 | `subscription_sync_rate_limited` | 用户短时间重复主动同步 |
| 503 | 50381 | `revenuecat_temporarily_unavailable` | RevenueCat 查询暂时失败 |
| 500 | 50081 | `subscription_snapshot_update_failed` | 本地快照事务失败 |

### 9.3 RevenueCat Webhook

```http
POST /api/v1/integrations/revenuecat/webhook/
Authorization: <configured webhook authorization>
X-RevenueCat-Webhook-Signature: t=<timestamp>,v1=<signature>
```

规则：

- endpoint 不使用 SparkService 用户 JWT；
- 必须验证配置的 Authorization Header；
- 启用 HMAC 时必须使用解析 JSON 前的原始 body 验签；
- 使用常量时间比较并校验时间窗口，防止重放；
- 未通过认证统一拒绝，响应不得泄露验签细节；
- 合法事件入库后快速返回 200，耗时同步进入异步任务；
- 重复 `event.id` 返回 200；
- 未知新事件类型允许入库并安全忽略，不导致持续重试风暴。

## 10. Webhook 事件边界

本期至少识别：

- `INITIAL_PURCHASE`
- `RENEWAL`
- `UNCANCELLATION`
- `CANCELLATION`
- `EXPIRATION`
- `BILLING_ISSUE`
- `PRODUCT_CHANGE`
- `TRANSFER`
- `REFUND_REVERSED`
- `SUBSCRIPTION_EXTENDED`
- `TEMPORARY_ENTITLEMENT_GRANT`

业务规则：

1. 所有已识别事件默认只触发重新同步，不直接决定最终 `is_pro`。
2. `CANCELLATION` 只表示停止续费；未到期 entitlement 仍然有效。
3. `BILLING_ISSUE` 不等于立即过期；宽限期内按 RevenueCat active entitlement 处理。
4. `EXPIRATION` 触发同步；确认 active entitlement 已不存在后才撤销 RevenueCat 来源权限。
5. `TRANSFER` 必须同步转入和转出相关用户，不能只更新 Webhook 当前用户。
6. 身份解析必须检查 `app_user_id`、`original_app_user_id`、`aliases`。
7. Sandbox 事件不得改变正式环境的 `effective_is_pro`。

## 11. 客户端与服务端权限边界

### 11.1 iOS 可以使用 RevenueCat 状态

```swift
customerInfo.entitlements
    .activeInCurrentEnvironment["健康Pro"] != nil
```

仅用于：

- 购买完成后即时关闭 Paywall；
- 更新设置页订阅展示；
- 显示会员状态；
- 临时解锁不消耗服务端资源的纯本地 UI；
- 触发服务端主动同步。

### 11.2 SparkService 必须决定的权限

- Pro AI 模型和服务端推理额度；
- 云端同步额度；
- 家庭共享高级功能；
- 服务端导出；
- 付费 API；
- 其他消耗服务端资源或读取受限数据的功能。

客户端不得上传并要求服务端信任：

```json
{
  "isPro": true
}
```

## 12. 当前关键文件

### 12.1 SparkService 当前文件

- `ai_config/models.py`
  - `TrialApplication`
  - `TrialApplicationRequest`
- `ai_config/services.py`
  - `TrialService.is_pro_user`
  - `TrialService.build_pro_summary`
- `accounts/services/login_service.py`
  - `LoginService._apply_is_pro`
  - `LoginService.build_current_session`
- `accounts/auth/views.py`
  - `CurrentSessionView`
- `accounts/urls.py`
  - 当前会话路由
- `backoffice/views.py`
  - 内部 Pro 试用授权与回收
- `backoffice/serializers.py`
  - 当前 Pro 状态展示
- `notification_center/business_scenes.py`
  - 已有会员试用通知场景

### 12.2 SparkClient 当前文件

- `SparkClient/Projects/Core/Subscriptions/RevenueCat/RevenueCatClient.swift`
- `SparkClient/Projects/Core/Subscriptions/RevenueCat/RevenueCatConfiguration.swift`
- `SparkClient/Projects/Features/Settings/Subscription/RevenueCatSubscriptionSection.swift`
- `SparkClient/Projects/App/Sources/App/Architecture/AppLifecycleCoordinator.swift`
- `SparkClient/Projects/App/Sources/App/SignedInMainTabHostView.swift`
- `SparkClient/Projects/Core/Domain/Entities/UserSession.swift`
- `SparkClient/Projects/Core/Networking/API/Auth/AuthAPI.swift`
- `SparkClient/Projects/Features/Auth/Infrastructure/DefaultAuthRepository.swift`

### 12.3 计划新增服务端目录

以下是计划位置，不代表文件已经存在：

```text
SparkService/subscriptions/
├── __init__.py
├── apps.py
├── models.py
├── urls.py
├── views.py
├── serializers.py
├── tasks.py
├── admin.py
├── services/
│   ├── revenuecat_client.py
│   ├── revenuecat_webhook_service.py
│   ├── subscription_sync_service.py
│   └── pro_entitlement_resolver.py
└── tests/
    ├── test_revenuecat_webhook.py
    ├── test_subscription_sync.py
    ├── test_pro_entitlement_resolver.py
    └── test_subscription_api.py
```

实施前应以目标分支最新结构为准。

## 13. 当前非目标

1. 不替换 RevenueCat 为自建 Apple 收据校验系统。
2. 不由 iOS 保存或调用 RevenueCat Secret API Key。
3. 不把 RevenueCat 订阅写入 `TrialApplication`。
4. 不删除现有内部试用、自动试用和后台人工授权能力。
5. 不把 `CustomerInfo` 请求体当作服务端可信订阅凭证。
6. 不在本工单中修改 RevenueCat Paywall 页面视觉设计。
7. 不在需求确认阶段执行迁移、创建 Django app、修改数据库或发布 Webhook。
8. 不默认让 Sandbox 购买解锁正式生产账号。

## 14. 官方依据

- RevenueCat Identifying Customers：<https://www.revenuecat.com/docs/customers/identifying-customers>
- RevenueCat CustomerInfo：<https://www.revenuecat.com/docs/customers/customer-info>
- RevenueCat Webhooks：<https://www.revenuecat.com/docs/integrations/webhooks>
- RevenueCat Webhook Event Fields：<https://www.revenuecat.com/docs/integrations/webhooks/event-types-and-fields>
- RevenueCat Common Webhook Flows：<https://www.revenuecat.com/docs/integrations/webhooks/event-flows>
- RevenueCat API v2 Customer Resources：<https://www.revenuecat.com/docs/api-v2/customer/resources>

## 15. 一问一答确认记录

### 第 1 问：RevenueCat App User ID 是否继续使用当前 SparkService `accountID`

为什么要问：当前 iOS 已经使用 `String(accountID)` 调用 RevenueCat `logIn`。保持不变最省改造且不会切断已有 Customer；改为不可猜测 ID 更符合 RevenueCat 官方建议，但需要增加字段、修改登录契约，并处理现有 Customer/订阅迁移。该决定会影响身份表设计、历史订阅归属、Webhook 查找和发布顺序，必须先确认。

请选择：

- A. 继续使用当前 `String(accountID)`，ID 不做特殊处理（推荐用于已有正式订阅或希望最小改造）  
  iOS、Webhook 和服务端均沿用当前数字用户 ID；新增 `RevenueCatCustomerIdentity` 只保存现有映射，不迁移历史 Customer。接受 ID 可猜测风险，并确保任何服务端查询都要求鉴权。

- B. 在正式上线前统一改为不可猜测 UUID（推荐用于尚无正式付费数据）  
  为用户增加稳定 `revenuecat_app_user_id`，登录接口返回该字段，iOS 改用 UUID；上线前清理或迁移测试 Customer，后续不再暴露数字主键。

- C. 老用户保留数字 ID，新用户使用 UUID  
  避免迁移现有订阅，但系统长期存在两套 ID，需要身份表和后台工具同时支持，测试与排障成本最高。

- D. 使用服务端 HMAC 派生的稳定不透明 ID  
  不新增随机 UUID 生成流程，但必须长期保管派生密钥并制定轮换策略；密钥变化会改变用户 ID，因此实现和运维风险高于 UUID。

请选择 A、B、C 或 D。

#### 第 1 问确认

**已确认选择 A：继续使用当前 `String(accountID)`，ID 不做特殊处理。**

落地约束：

- iOS 继续使用 `Purchases.shared.logIn(String(session.accountID))`，不新增 RevenueCat UUID 字段；
- SparkService `RevenueCatCustomerIdentity.app_user_id` 固定保存十进制 `str(user.id)`；
- 不迁移、重命名或重新 alias 已存在的 RevenueCat Customer；
- Webhook 身份解析以数字 `app_user_id` 为主，同时兼容 `original_app_user_id` 和 `aliases` 中的匿名 RevenueCat ID；
- 所有服务端订阅查询都必须从已鉴权 `request.user` 推导 App User ID，不提供按任意数字 ID 查询订阅的公开接口；
- RevenueCat Secret API Key 仍只保存在服务端；保持数字 ID 不代表允许客户端直接调用 Secret API；
- 后续如果需要更换为不可猜测 ID，必须新建独立迁移工单，不得在普通登录流程中静默切换。

### 第 2 问：后台人工 Pro 授权本期是否继续复用 `TrialApplication`

为什么要问：当前后台人工发放通过 `TrialApplication.grant_source=manual` 实现，而总体权限公式把“内部试用”和“后台人工授权”列为两个来源。如果本期拆表，需要迁移现有人工授权记录、改后台接口和通知流程；如果继续复用，则数据模型改动更小，但 `TrialApplication` 会继续同时承载试用与人工授权语义。

请选择：

- A. 本期继续复用 `TrialApplication`，由 `grant_source` 区分自动试用、申请试用和人工授权（推荐）  
  只新增 RevenueCat 订阅模型；`ProEntitlementResolver` 调用现有 `TrialService`，并在状态接口中根据 `grant_source` 展示 `trial` 或 `manual` 来源，不迁移现有数据。

- B. 本期新增独立 `ManualProGrant` 模型并迁移现有人工授权  
  试用和人工授权边界最清楚，但需要同步修改后台发放/回收、通知、审计、测试和历史数据，实施范围明显扩大。

- C. 后台人工授权改为 RevenueCat Promotional Entitlement  
  所有 Pro 权益集中到 RevenueCat，但后台操作会依赖第三方可用性，内部授权也会产生 RevenueCat 侧记录，并改变现有通知与审计链路。

- D. 本期取消后台人工授权，只保留 RevenueCat 订阅和内部自动/申请试用  
  权益来源最少，但现有后台发放与客服补偿能力将停止使用，需要明确下线和历史记录处理方案。

请选择 A、B、C 或 D。

#### 第 2 问确认

**已确认选择 A：本期继续复用 `TrialApplication`，通过 `grant_source` 区分自动试用、申请试用和后台人工授权。**

落地约束：

- 不新增 `ManualProGrant`，不迁移现有后台发放记录；
- `TrialApplication.grant_source=manual` 继续代表后台人工 Pro 授权；
- `TrialApplication.grant_source=auto/application` 继续代表内部自动试用或用户申请试用；
- RevenueCat 订阅独立保存到 `RevenueCatEntitlement`，不得写入 `TrialApplication`；
- `ProEntitlementResolver` 分别计算 RevenueCat、TrialApplication 的有效状态，最终按逻辑 OR 汇总；
- 订阅状态接口根据 `grant_source` 区分 `trial` 和 `manual` 来源；
- 既有后台授权、回收、通知和审计链路保持兼容；
- 如果未来需要彻底拆分人工授权，必须另建数据迁移工单。

### 第 3 问：Sandbox 订阅是否允许影响服务端 Pro 权限

为什么要问：RevenueCat Webhook 和 REST API 都会区分 `SANDBOX`、`PRODUCTION` 环境。若 Sandbox 事件直接写入正式权限，测试账号可能获得正式 Pro；若完全忽略 Sandbox，开发和联调阶段无法验证购买后主动同步、Webhook 和过期流程。该选择会影响数据库唯一约束、服务端 `effective_is_pro` 规则、测试配置和 RevenueCat Webhook 环境筛选。

请选择：

- A. Sandbox 只保存和测试，永远不影响正式用户 Pro 权限（推荐）  
  `RevenueCatEntitlement.environment=SANDBOX` 独立保存；正式环境 `effective_is_pro` 只读取 `PRODUCTION`。开发/测试可通过专用测试账号或非生产配置验证流程。

- B. Sandbox 在 Debug/测试服务端允许解锁 Pro，Production 服务端禁止  
  需要明确服务端环境标识和账号隔离，避免 Debug 客户端连接生产 API；数据模型保留环境字段，测试环境可计算 Sandbox Pro。

- C. Sandbox 与 Production 都可以直接解锁同一套正式 Pro  
  实现最简单，但会把测试购买混入正式权限，存在明显越权和数据污染风险。

- D. 完全忽略 Sandbox，不保存 Sandbox 事件  
  正式数据最干净，但无法利用真实 RevenueCat Webhook/REST 链路做联调和回归测试。

请选择 A、B、C 或 D。

#### 第 3 问确认

**已确认选择 A：Sandbox 只用于测试，永远不影响正式 Pro 权限。**

落地约束：

- `RevenueCatEntitlement` 按 `environment` 分别保存 `SANDBOX` 与 `PRODUCTION` 快照；
- 正式 `ProEntitlementResolver` 只读取 `environment=PRODUCTION`；
- Sandbox Webhook 可以通过验签、幂等入库、异步同步和审计全链路，但不得改变正式 `effective_is_pro`；
- `/subscriptions/revenuecat/sync` 不接受客户端上传环境参数，服务端按 RevenueCat 返回数据和部署配置处理；
- Sandbox 与 Production 必须在查询、唯一约束、指标、后台展示和测试数据中明确区分；
- 测试环境可以验证 Sandbox 流程，但不得把测试结果写入生产用户的正式权限；
- Production 服务不得提供临时开关让某个客户端自行把 Sandbox 当作正式订阅。

### 第 4 问：购买成功但 SparkService 主动同步暂时失败时，客户端如何处理

为什么要问：RevenueCat 购买可能已经成功且客户端 `CustomerInfo` 已显示 `健康Pro`，但 SparkService 可能因网络、RevenueCat API、数据库或限流暂时未更新。如果强制等待服务端确认，用户已付款却无法离开 Paywall；如果完全信任客户端，服务端付费资源可能在尚未校验时被越权调用。需要明确即时 UI 和服务端权限之间的短暂不一致策略。

请选择：

- A. 客户端立即确认购买并关闭 Paywall，纯本地 Pro UI 可更新；服务端 Pro 功能等待同步成功并自动重试（推荐）  
  客户端显示“购买成功，权益同步中”，后台重试 `/subscriptions/revenuecat/sync`；服务端受限 API 仍以 `ProEntitlementResolver` 为准，Webhook 可作为后续补偿。

- B. 必须等 SparkService 同步成功后才关闭 Paywall并显示购买成功  
  客户端与服务端状态最一致，但服务端短暂故障会让已完成 Apple 支付的用户停留在购买页，容易造成重复操作和投诉。

- C. 购买成功后客户端 RevenueCat 状态临时授权全部 Pro，包括服务端功能  
  体验即时，但服务端必须接受客户端证明或令牌，显著扩大安全边界，也违背服务端作为业务权限事实源的既定架构。

- D. 购买后不调用主动同步，只等待 RevenueCat Webhook  
  客户端实现最少，但 Webhook 可能延迟或最终失败，用户购买后的服务端权益生效时间不可控。

请选择 A、B、C 或 D。

#### 第 4 问确认

**已确认选择 A：购买成功后立即关闭 Paywall，显示“权益同步中”；服务端功能等待同步成功并自动重试。**

落地约束：

- RevenueCat `CustomerInfo` 确认购买成功后，iOS 可以立即关闭 Paywall，避免用户重复购买或误以为支付失败；
- 客户端可以立即更新纯本地 UI，但不得把客户端 Pro 状态作为服务端权限凭证；
- 客户端向 SparkService 发起主动同步，失败时按退避策略自动重试，并显示可理解的“权益同步中”状态；
- 服务端主动同步失败不得删除上一次已验证的有效 RevenueCat 快照，也不得因网络失败直接撤销 Pro；
- 服务端受保护 API 继续只使用 `ProEntitlementResolver`；同步未成功前，新的服务端 Pro 权限可以暂时等待；
- Webhook 到达后仍需重新同步 RevenueCat 当前状态，作为主动同步失败的补偿路径；
- 客户端重试必须幂等，不能因为重复点击、页面重建或网络恢复触发重复购买；
- 同步最终失败时需要提供“稍后重试/刷新订阅状态”的入口，并记录 request ID 供排查。

### 第 5 问：主动同步成功后，iOS 如何更新现有 `UserSession.isPro`

为什么要问：当前 `UserSession.isPro` 来自 SparkService 会话响应，而 RevenueCat 购买完成后是一个独立的异步流程。如果只更新 Paywall 内部状态，主界面、AI 权限和设置页可能继续显示旧状态；如果客户端自行修改会话字段，又可能让本地状态超出服务端事实。需要确定同步接口响应、当前会话刷新和本地缓存的职责边界。

请选择：

- A. `/subscriptions/revenuecat/sync` 返回完整订阅摘要，客户端用服务端响应更新当前 Session 状态（推荐）  
  服务端同步成功后直接返回 `isPro` 和来源摘要；iOS 通过统一 SessionStore/认证仓储更新 `UserSession.isPro`，不必额外等待下一次登录。

- B. 主动同步成功后，客户端再次调用 `GET /auth/session/` 获取完整 UserSession  
  Session 只有一个服务端来源，但会多一次网络请求；适合当前会话接口字段较多且不希望维护订阅响应合并逻辑的情况。

- C. 只更新 RevenueCat 本地状态，UserSession 等下次冷启动再刷新  
  实现最少，但当前登录期间主界面和服务端会话缓存可能持续显示旧 Pro 状态。

- D. 客户端直接把 `UserSession.isPro` 改为 true，不等待服务端结果  
  UI 立即一致，但本地状态可能伪造服务端权限，不符合服务端作为业务权限事实源的设计。

请选择 A、B、C 或 D。

#### 第 5 问确认

**已确认选择 A：主动同步接口返回完整订阅摘要，客户端直接使用服务端响应更新当前 Session。**

落地约束：

- `/api/v1/subscriptions/revenuecat/sync` 成功响应必须包含 `isPro`、权益来源、订阅状态、产品、过期时间、续费状态和最近同步时间；
- iOS 通过统一的 SessionStore/认证仓储更新当前 `UserSession.isPro`，不由页面局部状态长期代替会话状态；
- 客户端可以先显示 RevenueCat 即时购买结果，但最终 Session 状态以 SparkService sync 响应为准；
- sync 失败时不把本地 `isPro=true` 写入持久化 Session，只保留“权益同步中/待重试”状态；
- sync 成功后主界面、设置页和服务端 Pro 功能应使用同一份更新后的 Session/权限结果；
- `GET /api/v1/subscriptions/me` 与 sync 响应使用兼容的订阅摘要结构，避免客户端维护两套解析模型。

### 第 6 问：RevenueCat Webhook 的异步处理与失败事件如何管理

为什么要问：RevenueCat Webhook 要求快速返回 HTTP 200，实际订阅更新应在后台完成；同时事件可能重复、乱序、暂时失败或包含未来新增事件类型。若没有明确的队列、重试和人工重放边界，Webhook 失败后只能等待定时对账，排障和恢复会比较困难。

请选择：

- A. Webhook 入库 Inbox 后由 Celery 异步处理，失败自动重试，并提供后台人工重放（推荐）  
  HTTP 请求只负责验签和幂等入库；Worker 调 RevenueCat 查询当前状态并更新快照；失败事件保留错误和重试次数，后台可按 event ID 重放。

- B. Webhook 请求内同步完成 RevenueCat 查询和数据库更新  
  代码路径较短，但容易超过响应时间，网络慢或 RevenueCat 暂时不可用时会触发重复投递，可靠性较差。

- C. Webhook 只记录日志，完全依赖定时任务对账  
  实现简单，但订阅续费、过期、退款的生效延迟不可控，无法快速定位具体事件处理失败。

- D. 引入独立消息队列服务处理 Webhook，不使用现有 Celery 任务体系  
  可扩展性高，但会新增基础设施、运维和监控成本；当前项目已有 Celery 场景时不适合作为首期方案。

请选择 A、B、C 或 D。

#### 第 6 问确认

**已确认选择 A：Webhook 先写入 Inbox，再由 Celery 异步处理，失败自动重试，并支持后台人工重放。**

落地约束：

- Webhook HTTP 请求只负责认证、校验、幂等入库和快速返回 200；
- RevenueCat 当前状态查询、快照更新和 Pro 权限刷新由 Celery Worker 异步执行；
- `RevenueCatWebhookEvent.event_id` 唯一，重复投递不得重复更新订阅状态；
- 任务失败记录 `process_status`、`retry_count`、脱敏错误原因和最后处理时间；
- 自动重试必须有最大次数、退避间隔和死信/失败状态，不能无限重试；
- 后台提供按事件 ID 查看、重试和人工重放能力，但操作人必须有订阅运维权限；
- 人工重放仍复用同一事件 ID 和幂等逻辑，不能复制出新的业务事件；
- 定时对账继续作为 Webhook 失败后的全局兜底，不替代 Inbox 和事件审计。

### 第 7 问：RevenueCat Webhook 采用什么认证方式

为什么要问：Webhook 是公开 HTTP endpoint，必须防止伪造订阅事件、重放旧请求和恶意触发 RevenueCat API 查询。RevenueCat 支持配置 Authorization Header，也支持 HMAC 签名；认证方案会影响环境变量、验签中间件、部署配置和安全验收。

请选择：

- A. Authorization Header + HMAC-SHA256 双重校验（推荐）  
  Authorization Header 用于快速拒绝未配置请求，HMAC 使用原始 body、时间戳和签名密钥进行完整性校验；同时检查时间窗口和常量时间比较。

- B. 只使用 RevenueCat Authorization Header  
  配置简单、开发成本低，但无法校验请求 body 是否被篡改，也需要依赖单一静态 Header 密钥。

- C. 只使用 HMAC-SHA256  
  完整性和防重放能力较强，但部署配置和排障复杂度略高；不使用额外 Authorization Header。

- D. 只使用来源 IP 白名单  
  配置和网络环境依赖较重，不能单独证明请求内容来自 RevenueCat，不适合作为主要认证方式。

请选择 A、B、C 或 D。

#### 第 7 问确认

**已确认选择 B：Webhook 只使用 RevenueCat Authorization Header。**

落地约束：

- RevenueCat Dashboard 配置固定 Authorization Header，服务端通过环境变量读取期望值；
- Webhook endpoint 对每个请求执行 Header 常量时间比较，认证失败直接拒绝；
- 不使用来源 IP 白名单作为主要安全机制；
- 本期不实现 HMAC 签名验签，不要求保存 HMAC Secret；
- Authorization Header 不写入日志、Webhook Inbox payload 或后台页面；
- 仍必须使用 `event.id` 幂等、时间戳/事件时间审计和有限重试，Authorization Header 不替代业务幂等；
- 如果未来 RevenueCat 项目启用 HMAC，需要另建安全升级变更并兼容现有 Header 配置。

### 第 8 问：客户端主动同步失败后的重试策略

为什么要问：第 4 问已确认购买后立即关闭 Paywall并进入“权益同步中”，但尚未确定同步失败后由谁、何时、重试多少次。无限重试会消耗电量和接口额度；只提供手动重试又会增加用户等待成本；重试策略还会影响 Webhook 补偿和订阅状态提示。

请选择：

- A. 立即有限重试 + 前台恢复重试 + 手动刷新兜底（推荐）  
  购买完成后立即尝试，按退避策略进行有限次数重试；失败后记录待同步状态，App 回到前台或用户点击“刷新订阅”时继续，成功后清除待同步状态。

- B. 持续后台无限重试直到成功  
  最终成功概率高，但会持续消耗设备、电量和服务端资源，且 iOS 后台执行并不保证可靠。

- C. 只重试一次，失败后完全依赖 RevenueCat Webhook  
  客户端逻辑简单，但主动同步失败后用户只能等待 Webhook，无法及时恢复状态。

- D. 不自动重试，只提供手动“刷新订阅”  
  服务端请求最少，但购买后的状态恢复完全依赖用户主动操作，体验和客服排障成本较高。

请选择 A、B、C 或 D。

#### 第 8 问确认

**已确认选择 A：立即有限重试、App 前台恢复重试，并提供手动刷新兜底。**

落地约束：

- 购买完成后立即发起一次服务端 sync；
- 临时网络或服务端错误按退避策略进行有限次数重试；
- 达到自动重试上限后，客户端保留待同步状态，不持续后台无限运行；
- App 回到前台时检查待同步状态并恢复重试；
- 设置页提供“刷新订阅/重试同步”入口；
- 重试请求必须使用幂等键或等价的服务端幂等机制；
- 成功后清除待同步状态并更新当前 `UserSession.isPro`；
- 最终失败不删除服务端已有有效快照，继续等待 Webhook 或定时对账。

### 第 9 问：RevenueCat 或服务端暂时不可用时，已保存的订阅状态如何处理

为什么要问：服务端可能暂时无法访问 RevenueCat，或 Webhook/主动同步暂时失败。如果每次失败都立即撤销 Pro，会把短暂网络故障变成用户权限中断；如果无限期保留 active，又可能让真实过期用户长期使用服务。需要明确 `expires_at`、最后成功同步时间和服务端故障之间的关系。

请选择：

- A. 以最后一次成功校验的订阅快照为准，未到 `expires_at` 前继续有效；超过到期时间后默认失效（推荐）  
  网络失败不改变已验证的 active 状态；到期后即使 RevenueCat 暂时不可用，也不继续延长服务端 Pro，待恢复后重新对账。

- B. RevenueCat 或服务端不可用时，进入短暂宽限期继续保留 Pro  
  可减少服务中断，但需要额外定义宽限期长度、风险控制、异常监控和过期后的补偿逻辑。

- C. 只要最近一次状态是 active，就无限期保留 Pro，直到收到明确 EXPIRATION 事件  
  用户体验稳定，但 Webhook 丢失或账号异常时可能造成长期越权，不适合作为正式权限规则。

- D. 查询失败立即撤销 Pro  
  安全边界直接，但会把网络故障、服务端短暂异常和真实过期混为一谈，容易造成付费用户突然失去权益。

请选择 A、B、C 或 D。

#### 第 9 问确认

**已确认选择 A：以最后一次成功校验的订阅快照为准，未到 `expires_at` 前继续有效；超过到期时间后默认失效。**

落地约束：

- 服务端网络失败、RevenueCat 暂时不可用或 Webhook 处理失败时，不立即撤销已验证的 active 订阅；
- `RevenueCatEntitlement.status=active` 且 `expires_at` 仍在未来时，继续计算 RevenueCat 来源有效；
- `expires_at` 已到期时，即使暂时没有收到 `EXPIRATION` Webhook，也默认不再授予正式 Pro；
- 订阅状态不能因为“请求失败”自动延长 `expires_at`；
- 恢复服务后，通过主动同步、Webhook 重试或定时对账重新获取 RevenueCat 当前状态；
- 后台状态页必须区分“已过期”“同步失败”“待重试”和“未找到 RevenueCat 身份”；
- 如未来需要业务宽限期，必须作为独立策略配置和工单确认，不能隐式加入本规则。

### 第 10 问：后台订阅运维页面允许哪些操作

为什么要问：本方案已经要求支持 Webhook 失败事件查看和人工重放，但后台是否可以直接修改 RevenueCat 订阅、撤销 Pro 或手动刷新，会影响权限边界、审计要求和误操作风险。现有后台已经能操作 `TrialApplication`，需要把 RevenueCat 事实与内部人工授权区分开。

请选择：

- A. 后台只读订阅状态、查看事件，并允许重放失败 Webhook/触发重新同步；不直接修改 RevenueCat 订阅（推荐）  
  RevenueCat 继续作为付费事实来源，后台操作只负责恢复同步和排障；人工 Pro 仍通过现有 `TrialApplication.grant_source=manual` 管理。

- B. 后台除了重放，还允许直接撤销本地 RevenueCat Pro 快照  
  处理紧急风控更快，但可能造成 RevenueCat 与本地状态不一致，必须增加高权限、二次确认和后续强制对账。

- C. 后台通过 RevenueCat API 直接授予/撤销订阅权益  
  操作集中，但会把内部人工授权与第三方 Promotional Entitlement 混合，改变当前 `TrialApplication` 业务和审计链路。

- D. 本期不增加订阅运维页面，只保留日志和定时对账  
  实现范围最小，但 Webhook 失败无法人工快速恢复，客服和研发只能通过数据库或脚本排查。

请选择 A、B、C 或 D。

#### 第 10 问确认

**已确认选择 A：后台只读订阅状态、查看事件、重放失败 Webhook、触发重新同步；不直接修改 RevenueCat 订阅。**

落地约束：

- 后台可查看用户当前 RevenueCat entitlement、产品、环境、状态、到期时间、最后同步时间和同步错误；
- 后台可查看 Webhook Inbox 事件、处理状态、失败原因和重试次数；
- 后台可对失败事件执行人工重放，对用户执行重新同步；两者都必须记录操作人、时间、request ID 和结果；
- 后台不得直接修改 RevenueCat 订阅、修改 RevenueCat entitlement 或覆盖本地 `expires_at`；
- 后台人工 Pro 继续使用 `TrialApplication.grant_source=manual`；
- 后台订阅运维权限与内部人工 Pro 发放权限分开配置；
- 所有后台查询默认脱敏展示 App User ID、交易 ID 和错误详情，避免暴露不必要的支付信息。

### 第 11 问：RevenueCat 产品与 Entitlement 如何映射到 Pro 权限

为什么要问：当前 RevenueCat 有年度、月度等多个产品，但业务权限是统一的 `健康Pro`。如果服务端按产品 ID 判断权限，未来改价格、增加套餐或更换产品时需要同步修改权限代码；如果按 entitlement 判断，产品只作为订阅明细，更适合 RevenueCat 的权益模型。

请选择：

- A. 只用 `健康Pro` entitlement 作为权限判断，产品 ID 只保存为订阅明细（推荐）  
  年度、月度、试用和未来新增产品只要映射到 `健康Pro`，都获得同一套 Pro 权限；服务端不硬编码具体产品 ID 作为授权条件。

- B. 每个产品 ID 单独写入 Pro 权限规则  
  能精确控制不同产品，但价格调整、换 SKU 和新增套餐都需要同步修改服务端逻辑，容易漏配。

- C. 年度和月度分别创建不同 Entitlement  
  适合不同功能层级，但会扩大客户端、服务端和 Paywall 的权益模型；当前只有统一 Pro 能力时复杂度偏高。

- D. 只按 RevenueCat Offering 判断权限，不读取 Entitlement  
  Offering 主要是展示和销售配置，不适合作为历史购买、续费、恢复和退款后的最终权限事实。

请选择 A、B、C 或 D。

#### 第 11 问确认

**已确认选择 A：只使用 `健康Pro` entitlement 判断权限，产品 ID 仅保存为订阅明细。**

落地约束：

- `健康Pro` 是服务端和 iOS 判断 Pro 的唯一 RevenueCat entitlement key；
- 年度、月度、试用期和未来新增产品，只要在 RevenueCat 中映射到 `健康Pro`，都归入同一套 Pro 权限；
- `product_id`、`store`、`period_type`、价格周期和是否续费只用于展示、审计、分析和客服排障；
- 服务端不得把某个具体 SKU 写死为唯一 Pro 授权条件；
- RevenueCat Offering 只负责销售和 Paywall 展示，不参与最终服务端权限判断；
- 新增产品时优先配置 RevenueCat Entitlement 映射，不修改 Pro 权限解析代码。

### 第 12 问：订阅状态主动同步的触发时机

为什么要问：购买完成后同步只能覆盖新购买流程，无法覆盖用户在其他设备续费、App 长时间后台、退款或 Webhook 延迟后的状态变化。需要明确登录恢复、App 回到前台和用户主动查看订阅时是否触发服务端同步，避免频繁请求又保证状态足够新。

请选择：

- A. 登录/会话恢复、App 回到前台、购买/恢复完成和用户手动刷新时触发；按最小间隔限流（推荐）  
  覆盖主要生命周期，服务端通过用户级同步冷却时间避免重复请求；Webhook 和定时对账负责后台事件。

- B. 只在购买或恢复完成时触发主动同步  
  请求量较少，但跨设备续费、退款和 App 长时间离线后的状态可能不能及时刷新。

- C. 每次进入设置页或每次 App 前台都无条件同步  
  状态新鲜度高，但会增加 RevenueCat API、服务端和电量压力，需要更复杂的限流和失败处理。

- D. 只依赖 Webhook 和定时对账，客户端不主动同步登录/前台状态  
  客户端实现简单，但用户当前设备无法快速获得最新服务端订阅状态。

请选择 A、B、C 或 D。

#### 第 12 问确认

选择：A。订阅主动同步在登录/会话恢复、App 回到前台、购买/恢复完成和用户手动刷新时触发，并按用户级最小同步间隔限流。

确认后的约束：

- 登录或会话恢复时，仅在用户已登录且 RevenueCat 身份可确定时触发同步。
- App 回到前台时触发一次受限同步，不能因为页面重建或多次生命周期回调产生并发请求。
- 购买完成和恢复完成优先触发同步，使服务端尽快得到最新权益；Paywall 关闭和“权益同步中”展示逻辑继续遵循第 4 问结论。
- 用户手动刷新允许在正常冷却限制下发起一次同步，并保留有限重试、前台恢复重试和手动兜底策略。
- 同一用户的并发同步请求需要去重；具体冷却时间在实现阶段作为配置项确定，不写死在客户端业务页面中。
- Webhook Inbox/Celery 和定时对账仍是服务端后台同步入口，客户端主动同步不能替代它们。
- 同步失败不阻塞登录或主界面；客户端保留当前服务端 Session 状态，并进入可重试状态。服务端权限始终以最后一次成功校验的快照和 `ProEntitlementResolver` 为准。

### 第 13 问：现有用户的 RevenueCatCustomerIdentity 如何初始化

为什么要问：本方案保持当前 `String(accountID)` 作为 RevenueCat App User ID，但现有用户可能尚未有 `RevenueCatCustomerIdentity` 记录。需要明确身份映射是在登录时补齐、发布前批量迁移，还是只在购买时创建，避免同步接口因为缺少身份映射而失败。

请选择：

- A. 每次成功登录/会话恢复时 `get_or_create` 映射为 `String(user.id)`；存量用户按需懒创建，不做一次性全量迁移（推荐）  
  改动小、可回滚，能覆盖活跃用户；后台可另行补充数据检查和统计。

- B. 发布前为全部存量用户一次性创建映射，登录和同步必须依赖映射存在  
  数据完整性更明确，但需要额外迁移窗口和失败处理，发布前准备成本较高。

- C. 只有购买或订阅同步时才创建映射  
  能减少登录请求，但普通登录后的状态同步缺少稳定身份，首次购买前的恢复和查询链路更复杂。

- D. 不创建身份映射表，每次使用当前用户 ID 即时计算  
  实现最少，但不利于记录 RevenueCat alias、审计和后续身份迁移，也不符合本工单已确定的身份关联模型。

请选择 A、B、C 或 D。

#### 第 13 问确认

选择：A。登录/会话恢复时通过 `get_or_create` 创建或补齐 `RevenueCatCustomerIdentity`，使用 `String(user.id)` 作为 RevenueCat App User ID；存量用户按需懒创建，不做发布前强制全量迁移。

确认后的约束：

- 登录或会话恢复成功后，服务端以当前认证用户为准，创建或校验 `user.id → String(user.id)` 的唯一映射。
- 同一用户重复登录必须幂等，不能重复创建身份记录，也不能自动改写已有合法映射。
- 订阅同步接口从服务端认证用户和身份映射取得 `app_user_id`，客户端不得提交任意用户 ID 代查。
- 存量用户第一次登录/恢复时补齐映射；购买前、恢复购买和主动同步均依赖该映射存在。
- 发现映射冲突、已有 App User ID 属于其他用户或 RevenueCat alias 异常时，进入异常记录和人工排查流程，不自动覆盖关系。

### 第 14 问：iOS 端 RevenueCat 登录与登出应在什么时机执行

为什么要问：RevenueCat 默认可能先产生匿名 Customer，再由登录用户购买或恢复。如果没有在购买前绑定 SparkService 用户 ID，订阅可能落到匿名 Customer，服务端也无法稳定按用户同步。需要明确 SDK 配置、登录、登出和用户切换的顺序。

请选择：

- A. SDK 配置后，登录/会话恢复成功立即调用 `Purchases.shared.logIn(String(accountID))`；退出登录时调用 `logOut()`；购买、恢复和主动同步只在绑定完成后执行（推荐）  
  保证订阅归属当前业务用户，减少匿名 Customer 和跨账号恢复的歧义。

- B. 仅在用户点击购买时调用 `logIn(String(accountID))`  
  普通登录和恢复流程仍可能使用匿名 Customer，跨设备恢复和服务端同步时机不稳定。

- C. 永远不调用 RevenueCat `logIn`，只依赖 SDK 自动生成的匿名 ID  
  无法可靠将订阅与 SparkService 用户 ID 关联，不满足本工单的身份设计。

- D. 每次打开 Paywall 都先 `logOut()` 再 `logIn(String(accountID))`  
  会造成不必要的 Customer 切换和状态刷新，可能增加 alias、恢复和并发请求问题。

请选择 A、B、C 或 D。

#### 第 14 问确认

选择：A。RevenueCat SDK 配置后，在登录/会话恢复成功时立即调用 `Purchases.shared.logIn(String(accountID))`；退出登录时调用 `logOut()`；购买、恢复和主动同步只允许在 RevenueCat 用户绑定完成后执行。

确认后的约束：

- `Purchases.configure` 只负责初始化 SDK，不代表已经绑定 SparkService 用户。
- SparkService 登录成功后，iOS 先完成 RevenueCat `logIn`，再触发订阅状态同步和订阅相关 UI。
- `logIn` 的完成回调/异步结果必须被等待或转换为可观察状态；绑定失败时不能继续购买、恢复或请求订阅同步。
- 用户退出 SparkService 账号时调用 RevenueCat `logOut()`，清理当前订阅视图状态，避免下一位用户继承前一位用户的 CustomerInfo。
- 账号切换时必须先完成旧用户退出，再绑定新用户；禁止并发执行两个用户的 `logIn`、`logOut` 或订阅同步。
- Paywall 只接收当前已绑定用户的 Offering/CustomerInfo；不会在 Paywall 打开时重复 `logOut()`/`logIn()`。

### 第 15 问：匿名 RevenueCat Customer 与已登录用户绑定时如何处理

为什么要问：如果 SDK 在用户登录前已经生成匿名 Customer，随后调用 `logIn(String(accountID))` 可能触发 RevenueCat 的 alias/合并逻辑。需要明确匿名期间是否允许购买、如何避免把匿名购买错误归属到其他业务账号，以及客户端如何处理 `logIn` 返回的 CustomerInfo。

请选择：

- A. 登录前不允许购买和恢复；若已存在匿名 Customer，登录时由 RevenueCat 按官方 `logIn` 规则处理 alias，随后以登录用户 CustomerInfo 为准（推荐）  
  业务账号是订阅归属的唯一入口，避免匿名购买成为服务端无法关联的孤立状态。

- B. 允许匿名用户购买，登录后再尝试把匿名订阅迁移到业务用户  
  体验看似更顺畅，但迁移依赖 RevenueCat alias 规则，且可能造成家庭共享、恢复和账号归属争议。

- C. 登录前完全禁止 RevenueCat SDK 初始化  
  能减少匿名 Customer，但会影响登录前 Paywall 预加载和 SDK 生命周期管理；同时仍需处理用户登录后的初始化时机。

- D. 登录时忽略 `logIn` 返回的 CustomerInfo，只以 SparkService 本地状态为准  
  会丢失 RevenueCat 对 alias、恢复和最新 CustomerInfo 的结果，不利于购买完成后的状态更新。

请选择 A、B、C 或 D。

#### 第 15 问确认

选择：A。登录前不允许购买和恢复；登录时由 RevenueCat 官方 `logIn` 规则处理已有匿名 Customer，登录完成后以登录用户 CustomerInfo 为准。

确认后的约束：

- 未完成 SparkService 登录和 RevenueCat `logIn` 绑定时，Paywall 不允许进入购买或恢复流程。
- 已存在匿名 Customer 时，不在业务侧自行拼接、迁移或覆盖 alias；由 RevenueCat 官方登录规则处理关联结果。
- iOS 端必须消费 `logIn` 返回的 CustomerInfo，并刷新当前订阅展示和本地会员状态。
- 服务端仍以 RevenueCat 服务端查询、Webhook 和本地快照作为权限事实源；客户端 CustomerInfo 不能直接替代服务端权限。
- 如果 `logIn` 失败、CustomerInfo 不一致或发现账号归属异常，停止订阅操作并展示可重试状态，不自动切换到另一个业务用户。

### 第 16 问：RevenueCat API Key 与 Sandbox/Production 配置如何隔离

为什么要问：客户端 SDK 需要 Public SDK Key，服务端查询和 Webhook 需要 Secret API Key。若测试 Key、生产 Key 或 Secret Key 混用，可能造成 Sandbox 影响正式权限、Secret 泄露或服务端查询到错误项目数据。需要明确密钥来源、环境隔离和代码仓库中的保存方式。

请选择：

- A. iOS 使用对应环境的 Public SDK Key；服务端使用环境变量保存 Secret API Key、Project ID 和 Webhook Authorization；Sandbox 与 Production 分开配置（推荐）  
  满足最小权限和环境隔离要求，Secret 不进入客户端、不提交代码仓库，服务端只允许 Production 数据参与正式 Pro 权限。

- B. iOS 和服务端共用同一个 API Key，按接口类型自行判断权限  
  配置简单，但会扩大客户端泄露后的影响范围，也不符合 RevenueCat 公钥/密钥的权限边界。

- C. 将 Secret API Key 写入 iOS 配置文件，方便客户端直接查询 RevenueCat  
  会把高权限密钥暴露给用户，不能接受。

- D. 所有环境都使用当前测试 Key，发布时再手动替换  
  容易出现正式环境误用 Sandbox、配置漂移和正式 Pro 权限被测试数据影响。

请选择 A、B、C 或 D。

#### 第 16 问确认

选择：A。iOS 使用对应环境的 RevenueCat Public SDK Key；服务端通过环境变量保存 Secret API Key、Project ID 和 Webhook Authorization；Sandbox 与 Production 分开配置。

确认后的约束：

- iOS 只打包 Public SDK Key，不能包含 RevenueCat Secret API Key、Webhook Authorization 或服务端访问凭据。
- SparkService 通过环境变量或部署平台 Secret 管理服务端 Secret API Key、Project ID、Webhook Authorization 和相关配置。
- Sandbox、Production 使用独立的 RevenueCat 项目/Key/配置组合；服务端以环境配置决定查询和写入的环境。
- Sandbox 事件和快照不得参与正式 `健康Pro` 权限计算；正式环境发布前必须检查生产 Key、产品、Entitlement 和 Webhook 配置。
- 日志不得输出完整 API Key、Authorization、Customer 身份敏感信息或支付交易敏感字段。

### 第 17 问：Webhook 到达时暂时无法匹配 SparkService 用户，如何处理

为什么要问：RevenueCat Webhook 可能先于客户端登录映射、用户数据迁移或别名同步到达。如果事件无法通过 `app_user_id`、`original_app_user_id` 或 alias 找到业务用户，直接丢弃会造成订阅状态永久缺失；自动创建业务用户又可能引入错误账号和安全问题。

请选择：

- A. Webhook 先完整写入 Inbox，标记为“待匹配/待重试”；按 `app_user_id`、`original_app_user_id` 和已知 alias 查找，匹配成功后再异步同步当前 RevenueCat 状态（推荐）  
  保留事件和审计证据，兼容登录映射延迟与账号转移，同时避免根据第三方事件自动创建业务账号。

- B. 找不到用户时直接返回 200 并丢弃事件  
  接收端看似稳定，但会丢失关键订阅变更，后续只能依赖定时对账补救。

- C. 找不到用户时自动创建一个 SparkService 用户  
  可能把错误、匿名或恶意事件变成真实业务账号，破坏账号体系和安全边界。

- D. Webhook 处理线程同步等待用户登录后再继续  
  会阻塞 RevenueCat 回调，增加超时和重复投递风险，不符合 Inbox 异步处理模型。

请选择 A、B、C 或 D。

#### 第 17 问确认

选择：A。Webhook 先完整写入 Inbox；暂时无法匹配 SparkService 用户时标记为“待匹配/待重试”，通过 `app_user_id`、`original_app_user_id` 和已知 alias 查找，匹配成功后再异步查询 RevenueCat 当前状态。

确认后的约束：

- RevenueCat Webhook 接收层不因为暂时找不到业务用户而丢弃事件，原始 payload、事件 ID、环境和接收时间都必须保留。
- 事件匹配优先使用当前 `app_user_id`，再结合 `original_app_user_id` 和已保存 alias 关系；不能仅依赖单一字段。
- 待匹配事件由 Celery 重试，并支持后台人工重放；重放仍使用事件 ID 幂等保护。
- 找不到用户时不自动创建 SparkService 用户，也不直接修改任何其他用户的 Pro 状态。
- 一旦匹配成功，不直接根据旧 Webhook 事件推导最终权限，而是查询 RevenueCat 当前有效 entitlement 后更新本地快照。

### 第 18 问：定时对账任务的频率和扫描范围如何确定

为什么要问：Webhook 和客户端主动同步都可能延迟或失败，定时对账是最终兜底。如果扫描全部用户会产生不必要的 RevenueCat API 压力；如果只扫描当前 active 用户，又可能漏掉退款、过期和历史失败事件。需要明确默认频率与优先扫描范围。

请选择：

- A. 每 6 小时执行一次增量对账；优先扫描本地 active、最近失败、待匹配已解决、超过 24 小时未成功同步的用户；每天再执行一次低频全量异常检查（推荐）  
  兼顾状态及时性、API 成本和失败兜底，正常用户不会被无差别高频查询。

- B. 每次 App 启动都由服务端扫描全部用户  
  状态更新直观，但会造成高额 API 请求和服务端负载，且与客户端触发同步重复。

- C. 只扫描本地当前 active 用户，每天一次  
  成本较低，但可能漏掉状态已过期、Webhook 失败或历史映射异常的用户。

- D. 不做定时对账，只依赖 Webhook 和客户端主动同步  
  实现简单，但无法可靠修复长期离线、回调失败和数据漂移问题。

请选择 A、B、C 或 D。

#### 第 18 问确认

选择：A。每 6 小时执行一次增量对账，优先扫描本地 active、最近失败、待匹配已解决和超过 24 小时未成功同步的用户；每天再执行一次低频全量异常检查。

确认后的约束：

- 增量对账任务需要分页、限流和失败重试，不能一次性加载全部用户或无界调用 RevenueCat API。
- 对账优先处理可能影响当前权限的用户，同时保留任务运行结果、成功数、失败数、跳过数和 API 错误原因。
- 全量异常检查用于发现缺失身份映射、重复关系、长期未同步、环境错配和本地 entitlement 与 RevenueCat 不一致。
- 对账仍通过 `RevenueCatSubscriptionSyncService` 和 `ProEntitlementResolver` 更新状态，不另写一套权限判断逻辑。
- 对账任务只读取 RevenueCat 状态并更新 SparkService 本地快照，不直接修改 RevenueCat 订阅。

### 第 19 问：订阅功能上线时采用什么迁移与发布顺序

为什么要问：订阅身份映射、快照、Webhook Inbox、定时任务和权限解析会同时涉及数据库、后端配置、iOS 客户端和 RevenueCat 控制台。如果直接切换权限逻辑，可能出现旧用户无法登录、Webhook 无法入库或本地 Pro 状态瞬间失效。需要明确可回滚的上线顺序。

请选择：

- A. 先做兼容性数据库迁移与只读模型，再部署服务端同步/Resolver，配置并验证 Webhook，最后发布 iOS 登录绑定和 Paywall 购买链路；确认数据稳定后再切换所有 Pro 权限入口（推荐）  
  采用渐进式上线，旧的试用/人工授权逻辑可暂时保留，出现问题时可以关闭主动同步或 Webhook 消费而不影响基础登录。

- B. 先发布 iOS Paywall，再补服务端同步和数据模型  
  用户可能已经购买，但服务端没有稳定的归属、Webhook 和权限解析，容易出现付费后无法解锁。

- C. 一次性修改数据库、服务端权限和 iOS 客户端并强制切换  
  发布速度快，但失败时影响面大，回滚和问题定位困难。

- D. 先删除旧 TrialApplication 权限逻辑，再接入 RevenueCat  
  会在新链路尚未稳定时让现有试用和人工授权用户失去权限，不符合兼容上线要求。

请选择 A、B、C 或 D。

#### 第 19 问确认

选择：A。订阅功能采用分阶段、兼容且可回滚的上线顺序：先完成数据库迁移与只读模型，再部署服务端同步和 `ProEntitlementResolver`，配置并验证 Webhook，最后发布 iOS 用户绑定和 Paywall 购买链路；数据稳定后再切换全部 Pro 权限入口。

确认后的约束：

- 数据库迁移必须向后兼容，先增加模型、索引和状态字段，不在第一阶段删除旧字段或旧权限逻辑。
- 服务端先支持只读快照、同步接口、Resolver 和日志，再逐步接入 Webhook Inbox、Celery 与定时对账。
- Webhook 必须先在 Sandbox 验证认证、幂等、重试、待匹配和人工重放，再配置 Production。
- iOS 发布前必须完成 RevenueCat 登录绑定、退出清理、购买完成同步、恢复购买同步和前台重试链路。
- 旧的 `TrialApplication` 试用/人工授权逻辑在切换前继续有效，最终权限统一由 `ProEntitlementResolver` 合并判断。
- 每个阶段都要有可观测指标和关闭开关；出现异常时可暂停 Webhook 消费、主动同步或新权限入口，不直接破坏现有用户权限。

### 第 20 问：订阅功能验收测试范围如何确定

为什么要问：订阅问题往往出现在购买完成后的异步同步、跨设备、恢复、退款、过期、Webhook 重复投递和账号切换，而不仅是 Paywall 能否打开。需要确定上线前必须覆盖的测试场景，避免只验证单次 Sandbox 购买成功。

请选择：

- A. 覆盖完整核心链路：登录绑定、Paywall 展示、月度/年度购买、恢复购买、购买后同步失败重试、跨设备刷新、续费/取消/过期/退款 Webhook、重复事件、待匹配、账号切换、Sandbox/Production 隔离、试用与人工授权合并权限（推荐）  
  能验证客户端、RevenueCat、Webhook、服务端快照和最终 Pro 权限之间的完整闭环。

- B. 只测试 Paywall 能打开和购买成功  
  验收成本最低，但无法发现服务端权限、Webhook、恢复购买和失败重试问题。

- C. 只测试服务端 API 和数据库，不测试真实 StoreKit/RevenueCat 流程  
  能验证后端逻辑，但不能证明客户端用户购买、恢复和账号绑定链路可用。

- D. 只在 Production 上用真实付费账号验证  
  风险高且不可控，不适合作为首次接入的主要验收方式。

请选择 A、B、C 或 D。

#### 第 20 问确认

选择：A。上线前覆盖完整订阅闭环：登录绑定、Paywall 展示、月度/年度购买、恢复购买、购买后同步失败重试、跨设备刷新、续费、取消、过期、退款、重复 Webhook、待匹配、账号切换、Sandbox/Production 隔离，以及 RevenueCat 订阅、内部试用和人工授权的合并权限。

确认后的验收约束：

- 验收必须同时覆盖 iOS 客户端行为、RevenueCat Customer/Entitlement 状态、Webhook Inbox、异步任务、本地快照和最终服务端 API 权限。
- 购买成功但主动同步失败时，必须验证 Paywall 关闭、“权益同步中”、有限重试、App 前台恢复重试和手动刷新兜底。
- 取消不应在 `expires_at` 前立即失去 Pro；过期、退款和撤销必须按最终有效 entitlement 正确失效。
- 重复 Webhook、乱序 Webhook、待匹配 Webhook 和人工重放不得造成重复数据或错误覆盖新状态。
- Sandbox 只能影响 Sandbox 数据；任何 Sandbox 购买都不能让正式 Production Pro 权限生效。
- 账号切换和退出登录后，不能读取或继承前一位用户的 CustomerInfo、Session Pro 状态或订阅快照。
- 内部试用、人工授权和 RevenueCat entitlement 必须按已确认规则独立保存并由 Resolver 合并，不能互相覆盖。

### 第 21 问：上线后的订阅监控与告警范围如何确定

为什么要问：订阅链路是异步系统，购买失败、Webhook 延迟、同步队列堆积、RevenueCat API 错误和本地快照漂移可能不会直接表现为接口 5xx。需要明确上线后必须监控的指标，避免用户已付费但服务端没有及时授予权益。

请选择：

- A. 监控并告警核心链路：Webhook 接收/认证失败、Inbox 待处理和待匹配数量、Celery 重试与死信、RevenueCat API 错误率/延迟、主动同步失败率、快照过期数量、Pro 权限不一致、对账失败和 Production/Sandbox 环境错配（推荐）  
  能覆盖从 RevenueCat 事件到最终 Pro 权限的主要故障点，并支持按用户和事件 ID排查。

- B. 只监控 Webhook HTTP 失败
  能发现部分入口问题，但无法发现异步队列堆积、同步失败和权限漂移。

- C. 只监控 RevenueCat 控制台，不增加 SparkService 指标
  能看到第三方侧数据，但无法确认本地用户权限是否已经正确更新。

- D. 暂不增加订阅专项监控，出现用户反馈后再排查
  初期成本低，但付费权限问题会变成被动投诉，且难以还原异步链路。

请选择 A、B、C 或 D。

#### 第 21 问确认

选择：D。本阶段暂不增加订阅专项监控和主动告警系统，出现用户反馈后再排查。

保留的最低运行保障：

- Webhook Inbox、同步记录、失败原因、事件 ID、处理状态和人工重放记录仍必须保留，作为问题排查依据。
- Celery 失败任务仍按既定策略重试并保留失败状态，不因为暂不告警而取消重试和审计。
- 服务端日志保留必要的错误上下文，但不得记录 Secret API Key、Authorization 或不必要的支付敏感信息。
- 后续若出现付费用户无法解锁、Webhook 堆积或同步失败反馈，再基于实际问题补充专项指标和告警。

### 第 22 问：本次工单确认完成后，下一阶段如何执行

为什么要问：当前工单已经明确用户 ID、数据模型、客户端绑定、同步入口、Webhook、对账、上线顺序和验收范围。需要确认是先完成需求文档作为设计基线，还是立即按照工单进入代码实施，避免在没有明确阶段边界的情况下直接修改项目代码。

请选择：

- A. 先将本工单标记为需求确认完成，随后按实施顺序进入代码改造；实施阶段再拆分数据库、服务端、iOS 和验收子任务（推荐）  
  保留当前设计基线，便于按阶段交付和回滚；本次确认过程不直接替代代码实施评审。

- B. 只保留需求文档，本阶段不进入代码实施  
  适合先做方案评审，但订阅能力不会产生实际代码变更。

- C. 立即一次性修改所有服务端和 iOS 代码，不再拆分实施阶段  
  交付速度看似较快，但不符合已经确认的渐进式上线顺序。

- D. 先只改 iOS Paywall，服务端后续再补
  会产生购买成功但服务端无法确认 Pro 的不完整链路。

请选择 A、B、C 或 D。

#### 第 22 问确认

选择：A。先将本工单标记为“需求确认完成”，随后按实施顺序进入代码改造，并拆分数据库、服务端、iOS 和验收子任务。本次需求确认过程不直接修改业务代码，也不执行编译或运行测试。

## 16. 最终确认结论

本工单已完成需求确认，最终设计基线如下：

- RevenueCat App User ID 继续使用当前 `String(accountID)`，不新增特殊 ID 算法。
- 登录/会话恢复时 `get_or_create` `RevenueCatCustomerIdentity`；存量用户按需懒创建。
- RevenueCat 订阅与内部 `TrialApplication` 分开保存，通过 `grant_source` 区分试用和人工授权。
- Sandbox 只用于测试，永远不参与正式 Production Pro 权限。
- 只使用 `健康Pro` entitlement 判断 RevenueCat Pro 权限，产品 ID 仅作为订阅明细。
- iOS 登录/会话恢复成功后调用 `Purchases.shared.logIn(String(accountID))`；退出时调用 `logOut()`；购买、恢复和同步必须在绑定完成后执行。
- 登录前不允许购买和恢复；匿名 Customer 按 RevenueCat 官方 `logIn` 规则处理。
- 购买完成后立即关闭 Paywall，显示“权益同步中”；服务端同步失败时有限重试、App 前台恢复重试，并提供手动刷新兜底。
- `/subscriptions/revenuecat/sync` 返回完整订阅摘要，客户端使用服务端响应更新当前 Session。
- Webhook 采用 Authorization Header，先写入 Inbox，再由 Celery 异步处理、自动重试并支持后台人工重放。
- Webhook 无法匹配用户时保留为待匹配/待重试，不自动创建业务用户。
- 服务端以最后一次成功校验为准，在 `expires_at` 前继续有效，超过到期时间后失效。
- 主动同步触发于登录/会话恢复、App 前台、购买/恢复完成和手动刷新，并按最小间隔限流。
- 每 6 小时增量对账，每天低频全量异常检查。
- 本阶段不增加订阅专项监控告警，但保留 Inbox、失败重试、事件审计和必要错误日志。

## 17. 实施拆分与顺序

### 17.1 数据库与迁移

1. 新增 `RevenueCatCustomerIdentity`、`RevenueCatEntitlement`、`RevenueCatWebhookEvent` 或对应 Inbox 模型。
2. 增加唯一约束、环境字段、事件 ID 幂等索引和必要查询索引。
3. 扩展 `TrialApplication` 的 `grant_source`，兼容已有试用和人工授权数据。
4. 先完成向后兼容迁移，不删除旧字段，不改变现有登录和试用行为。

### 17.2 服务端同步与权限

1. 实现服务端 `RevenueCatClient`，Secret API Key 只从环境变量读取。
2. 实现 `RevenueCatSubscriptionSyncService`，以当前认证用户解析 App User ID，查询 RevenueCat 当前有效 entitlement 并更新快照。
3. 实现 `ProEntitlementResolver`，统一合并 RevenueCat、TrialApplication 和人工授权来源。
4. 新增 `POST /api/v1/subscriptions/revenuecat/sync` 和 `GET /api/v1/subscriptions/me`。
5. 将现有登录响应和服务端 Pro 权限检查逐步切换到 Resolver，保留兼容回退窗口。

### 17.3 Webhook 与后台任务

1. 新增 Webhook Authorization Header 校验和环境校验。
2. Webhook 只负责快速入 Inbox，使用事件 ID 幂等。
3. Celery 异步处理、重试、待匹配和人工重放。
4. 实现每 6 小时增量对账和每日低频全量异常检查。
5. 保留事件状态、失败原因、处理时间和重放记录。

### 17.4 iOS 客户端

1. 保持 SDK 初始化使用 Public SDK Key。
2. 登录/会话恢复完成后调用 `Purchases.shared.logIn(String(accountID))`。
3. 绑定完成前禁止购买和恢复；退出账号调用 `Purchases.shared.logOut()`。
4. 购买/恢复完成后关闭 Paywall，展示“权益同步中”，调用服务端同步接口。
5. 处理前台恢复、有限重试、手动刷新和服务端 Session 更新。
6. 不把客户端 `CustomerInfo` 或 `isPro` 作为服务端权限凭证。

### 17.5 验收与发布

1. 先在 Sandbox 验证登录绑定、购买、恢复、Webhook、重试、待匹配和账号切换。
2. 验证月度/年度产品均映射到 `健康Pro`，Sandbox 不影响 Production。
3. 验证续费、取消、过期、退款、重复事件、跨设备和人工授权合并权限。
4. 验证服务端同步失败时客户端行为和最终权限一致性。
5. 验收通过后再配置 Production Webhook、生产 Key 和正式客户端发布配置。

## 18. 本阶段交付边界

- 本阶段交付：需求确认工单、架构基线、实施拆分、接口和验收约束。
- 本阶段不交付：数据库迁移代码、服务端业务代码、iOS 代码修改、编译产物和运行测试结果。
- 下一阶段开始前，应以本工单为设计基线，分别创建数据库、SparkService、LookHealthClient/SparkClient 和验收子任务。

## 19. 最终确认矩阵

| 确认项 | 最终结论 | 实施影响 |
|---|---|---|
| RevenueCat 用户 ID | `String(accountID)` | 服务端仅从认证用户得到 ID；不接受客户端指定查询对象 |
| 内部授权 | 继续复用 `TrialApplication`，以 `grant_source` 区分 | RevenueCat 订阅绝不写入 TrialApplication |
| 正式权限 | 仅 Production 的 `健康Pro` entitlement | Sandbox 只留测试快照，Resolver 不读取 |
| 权限事实源 | SparkService `ProEntitlementResolver` | 客户端 CustomerInfo 只用于界面即时反馈 |
| 购买完成 | 关闭 Paywall，显示“权益同步中” | 服务端同步成功前，耗费服务端资源的 Pro 能力不放行 |
| 主动同步 | 登录恢复、前台、购买/恢复完成、手动刷新 | 用户级冷却、并发去重、失败后有限重试 |
| Webhook | Authorization Header + Inbox + Celery | 快速 200、事件 ID 幂等、失败可重放 |
| 用户匹配失败 | 待匹配/待重试 | 不丢事件、不自动创建 SparkService 用户 |
| 对账 | 每 6 小时增量；每日异常全检 | 按 active、失败、长期未同步等优先级分页执行 |
| 后台能力 | 只读、重放、触发重新同步 | 不允许通过后台直接修改 RevenueCat 订阅 |
| 监控 | 暂不建专项告警 | 仍保留 Inbox、失败记录、审计日志与可查询状态 |

## 20. 完整状态与业务流程

### 20.1 统一权限计算

```text
RevenueCat Production snapshot
          │
          ├── active `健康Pro` 且 expires_at > now ──┐
          │                                          │
TrialApplication（auto/application/manual）          ├── ProEntitlementResolver
          │                                          │          │
          └── active 且 expires_at > now ────────────┘          └── effective_is_pro
                                                                  ├── 登录/当前会话响应
                                                                  ├── AI Pro API 鉴权
                                                                  ├── 其他服务端付费能力
                                                                  └── iOS Session 展示
```

`RevenueCatEntitlement` 只保存某个环境的 RevenueCat 快照；`TrialApplication` 只保存内部来源。任何一个来源过期、撤销或同步失败，都不得覆盖另一个仍有效来源。

### 20.2 已登录与主动同步流程

```text
iOS 登录或会话恢复
  → SparkService 登录响应 / 当前会话返回服务端 effective_is_pro
  → AppLifecycleCoordinator 绑定 RevenueCat: logIn(String(accountID))
  → 绑定成功：SubscriptionSyncCoordinator 请求 POST /subscriptions/revenuecat/sync/
  → SparkService get_or_create RevenueCatCustomerIdentity
  → 同步服务查询 RevenueCat Production active_entitlements
  → 原子更新本地快照 + Resolver 计算 effective_is_pro
  → 返回订阅摘要
  → iOS 原子替换 UserSession.isPro 并持久化 SessionSnapshotStore
```

购买和恢复购买复用同一条服务端同步链路。若服务端查询暂时失败：iOS 立即关闭 Paywall，显示“权益同步中”，不将本地 CustomerInfo 写成服务端事实；后台任务和前台恢复继续尝试。同步成功后才刷新服务端 Pro 功能。

### 20.3 Webhook 与对账流程

```text
RevenueCat POST /api/v1/integrations/revenuecat/webhook/
  → 常量时间比较 Authorization Header
  → 校验 JSON、project/app/environment 白名单
  → INSERT RevenueCatWebhookEvent(event_id UNIQUE, status=received)
  → on_commit 投递 Celery task
  → 立刻返回 HTTP 200

Celery worker
  → select_for_update 锁定事件
  → 匹配 app_user_id / original_app_user_id / aliases
  → 未匹配：unmatched + next_retry_at
  → 已匹配：查询 RevenueCat 当前 Production entitlement
  → 更新快照，标记 processed
  → TRANSFER：对转出和转入用户分别排队同步

Beat
  → 每 6 小时增量扫描 → 同一同步服务
  → 每日全量异常扫描 → 记录不一致并安排重试
```

Webhook 事件类型只用于决定需要同步哪些 Customer，不能直接授予或撤销 Pro；例如 `CANCELLATION` 只表示停止续费，权限仍由当前 entitlement 和到期时间决定。

## 21. 数据模型与状态机（实施规格）

新增独立 Django app：`subscriptions`。它是 RevenueCat 同步和最终 Resolver 的唯一归属；`ai_config` 继续拥有内部 TrialApplication。

### 21.1 `RevenueCatCustomerIdentity`

| 字段 | 规则 |
|---|---|
| `user` | `OneToOneField(settings.AUTH_USER_MODEL, on_delete=CASCADE)` |
| `app_user_id` | `CharField(max_length=100, unique=True, db_index=True)`，值固定为 `str(user.id)` |
| `last_sync_attempt_at` | nullable，用于最小间隔限流和排障 |
| `last_successful_sync_at` | nullable，作为“最后成功校验”时间 |
| `last_sync_error_code` | `CharField(max_length=64, blank=True)`，只保存受控错误码 |
| `created_at` / `updated_at` | 审计时间 |

创建规则：登录/会话恢复成功后，服务端以当前 `request.user` 执行 `get_or_create`。如果已有映射的 `app_user_id != str(user.id)`，必须记录 `identity_conflict` 并停止同步；不得自动覆盖。

### 21.2 `RevenueCatCustomerAlias`

该表是为已确认的 `original_app_user_id` / `$RCAnonymousID:` alias 匹配而新增的辅助表，不改变“一个 SparkService 用户只有一个稳定 App User ID”的主关系。

| 字段 | 规则 |
|---|---|
| `identity` | `ForeignKey(RevenueCatCustomerIdentity, related_name="aliases", on_delete=CASCADE)` |
| `alias` | `CharField(max_length=1500, unique=True, db_index=True)` |
| `source` | `login_result`、`webhook` 或 `server_sync` |
| `first_seen_at` / `last_seen_at` | 用于审计和清理 |

只有 RevenueCat `logIn` 结果、Webhook payload 或服务端 RevenueCat 查询结果中的 alias 才允许入库；客户端请求体不得提交 alias。若 alias 已归属于另一 identity，保留事件并进入人工排查，不做自动转移。

### 21.3 `RevenueCatEntitlement`

每个 `(user, entitlement_identifier, environment)` 只保留一行当前快照。

| 字段 | 规则 |
|---|---|
| `user` | ForeignKey，查询索引 |
| `entitlement_identifier` | 本期只接受 `健康Pro` |
| `environment` | `production` / `sandbox`，与 RevenueCat 原始环境值一一映射 |
| `status` | `active`、`expired`、`revoked`、`unknown` |
| `product_id` / `store` / `period_type` | 订阅明细，不参与授权 |
| `started_at` / `expires_at` / `will_renew` | 当前权益事实 |
| `original_transaction_id` | 可空索引，仅用于客服排障与去重，不向普通客户端返回 |
| `provider_updated_at` / `last_synced_at` | Provider 时间与本地成功同步时间 |

唯一约束：`UniqueConstraint(fields=["user", "entitlement_identifier", "environment"], name="subscriptions_unique_rc_entitlement_snapshot")`。

快照写入必须在事务内执行：先锁定 identity 与现有快照，再比较 `provider_updated_at`；旧 Provider 数据不得覆盖较新的快照。生产 Resolver 只查询 `environment="production"`。

### 21.4 `RevenueCatWebhookEvent`（Inbox）

| 字段 | 规则 |
|---|---|
| `event_id` | RevenueCat `event.id`，全局唯一索引 |
| `event_type` / `environment` / `app_user_id` | 接收时的最小可查询字段 |
| `payload` | 原始 JSON，限制为已验证对象；不得把 Authorization 写入 payload |
| `process_status` | `received` → `processing` → `processed`；或 `unmatched` / `retryable` / `failed` |
| `attempt_count` / `next_retry_at` / `locked_at` | 任务重试与租约 |
| `matched_user` | nullable ForeignKey，匹配成功后写入 |
| `error_code` / `error_message` | 受控错误码与脱敏原因 |
| `received_at` / `processed_at` | 审计时间 |

状态转换：`received → processing → processed`；可恢复失败使用 `retryable → processing`；找不到用户使用 `unmatched → processing`；达到尝试上限或发现不可恢复配置错误时进入 `failed`。`processed` 和 `failed` 均为终态，但后台“重放”只能将 `failed` / `unmatched` 创建为新的处理尝试，不能改写原始 payload 或 event ID。

### 21.5 并发、锁与保留策略

- 主动同步以 `RevenueCatCustomerIdentity` 行锁和 Redis/Celery 任务唯一键双重去重；同一用户同时只允许一个真实 Provider 查询。
- Webhook 使用 `event_id` 数据库唯一约束抵御至少一次投递；重复请求直接返回 200，不再次入队。
- 默认同步冷却时间为 300 秒，购买/恢复与后台人工重放可忽略普通冷却，但仍必须复用同一用户锁。
- Webhook 原始 payload、处理记录与失败原因保留 180 天；生产环境的详细支付交易字段仅管理员审计可见。实际保留天数如受合规要求影响，以部署环境规则为准。

## 22. 服务端接口契约

所有普通客户端接口沿用现有响应包装：`{"code": 0, "msg": "success", "data": {...}}`。路径末尾保留 `/`，与当前 Django URL 风格一致。

### 22.1 查询当前订阅：`GET /api/v1/subscriptions/me/`

鉴权：`IsAuthenticated`。不接受用户 ID、App User ID、环境或产品 ID 参数。

```json
{
  "code": 0,
  "msg": "success",
  "data": {
    "isPro": true,
    "effectiveSource": "revenuecat",
    "syncState": "synced",
    "lastSyncedAt": "2026-09-22T12:00:05Z",
    "sources": [
      {
        "type": "revenuecat",
        "active": true,
        "environment": "production",
        "entitlement": "健康Pro",
        "productId": "health_yearly_99_intro3days_free",
        "expiresAt": "2027-09-22T12:00:00Z",
        "willRenew": true
      },
      {"type": "trial", "active": false, "expiresAt": null},
      {"type": "manual", "active": false, "expiresAt": null}
    ]
  }
}
```

`effectiveSource` 是展示优先级，不是唯一授权来源；若多来源同时有效，仍返回 `isPro=true`，并在 `sources` 中完整列出。

### 22.2 主动同步：`POST /api/v1/subscriptions/revenuecat/sync/`

鉴权：`IsAuthenticated`。Body 为空；严禁接收 `app_user_id`、`customer_info`、`is_pro`、交易 ID 或产品 ID。支持请求头 `Idempotency-Key`（UUID，最长 128 字符）用于客户端网络重试追踪。

处理规则：

1. 依据 `request.user` 取得或创建 identity；
2. 若用户已有进行中的同步，返回当前快照，`syncState="syncing"`，HTTP 202；
3. 冷却期内且无 `force` 管理权限时，返回当前快照，`syncState="cooldown"`，HTTP 200；
4. 正常情况下进行一次受超时保护的 RevenueCat 查询；成功后返回最新完整摘要，HTTP 200；
5. Provider 临时失败时排入重试任务，返回最后成功快照和 `syncState="pending_retry"`，HTTP 202；
6. 身份冲突返回 HTTP 409，且不查询其他 Customer。

受控错误码：`42001 sync_in_progress`、`42002 revenuecat_unavailable`、`42003 identity_conflict`、`42004 invalid_idempotency_key`。不把 RevenueCat 原始错误、Secret 或 Customer 全量信息返回给客户端。

### 22.3 RevenueCat Webhook：`POST /api/v1/integrations/revenuecat/webhook/`

不使用 JWT。必须精确比较 `Authorization` Header 与 `REVENUECAT_WEBHOOK_AUTHORIZATION`；比较使用 `secrets.compare_digest`。请求必须是 JSON 且满足已配置 Project/App/环境白名单。认证失败返回 401，格式错误返回 400；成功接收、重复事件和已存在事件都返回 200。

Webhook handler 只能入 Inbox 和排队，禁止在 HTTP 请求内调用 RevenueCat API 或更新最终 Pro 权限。RevenueCat 官方建议快速返回 200 并在响应后异步处理；其文档也明确支持 Authorization Header 验证和失败重投。 [Webhook 文档](https://www.revenuecat.com/docs/integrations/webhooks)

### 22.4 后台只读运维接口

沿用 `/api/admin/v1/` 与 `AdminOnlyPermission` / `AdminCodePermission`：

| 方法与路径 | 权限 | 行为 |
|---|---|---|
| `GET /api/admin/v1/subscriptions/users/<user_id>/` | `AdminOnlyPermission` | 查看用户汇总、快照、试用/人工授权来源（敏感字段脱敏） |
| `GET /api/admin/v1/subscriptions/events/` | `AdminOnlyPermission` | 分页查看 Inbox，支持 status、event_id、user_id、environment 过滤 |
| `POST /api/admin/v1/subscriptions/events/<event_id>/replay/` | `AdminCodePermission` | 记录操作员和 request ID 后重新投递处理任务 |
| `POST /api/admin/v1/subscriptions/users/<user_id>/sync/` | `AdminCodePermission` | 触发该用户的服务端重新同步 |

后台不得提供“取消、退款、授予或编辑 RevenueCat 订阅”的接口。内部人工 Pro 仍走已有 TrialApplication 管理入口，且在用户详情中明确展示它不是 RevenueCat 订阅。

## 23. 服务端落地位置与核心设计示例

以下为计划改动位置；除明确标记为“当前已存在”的文件外，均不代表已经实现。

```text
SparkService/
├── SparkService/settings.py                         # 当前已存在：新增 subscriptions 配置、Celery 路由与 Beat
├── SparkService/urls.py                              # 当前已存在：include subscriptions 与 webhook 路由
├── accounts/services/login_service.py                # 当前已存在：_apply_is_pro 改为 Resolver
├── accounts/auth/views.py                            # 当前已存在：当前会话响应改为 Resolver
├── ai_config/views.py                                # 当前已存在：AI Pro 检查改为 Resolver
├── backoffice/urls.py                                # 当前已存在：增加订阅运维路由
├── backoffice/views.py                               # 当前已存在：增加只读/重放/重新同步 View
└── subscriptions/                                    # 已新增 app
    ├── models.py, admin.py, apps.py, urls.py, views.py, tasks.py
    ├── services/revenuecat_client.py
    ├── services/subscription_sync_service.py
    ├── services/pro_entitlement_resolver.py
    ├── services/webhook_inbox_service.py
    └── tests/test_models.py, test_sync.py, test_webhook.py, test_api.py, test_resolver.py
```

配置项（均由 `.env` /部署密钥管理注入，严禁提交真实值）：

```text
REVENUECAT_API_BASE_URL=https://api.revenuecat.com/v2
REVENUECAT_PROJECT_ID=<production-project-id>
REVENUECAT_SECRET_API_KEY=<server-only-secret>
REVENUECAT_WEBHOOK_AUTHORIZATION=<random-long-secret>
REVENUECAT_ENTITLEMENT_ID=<entl_xxx>
REVENUECAT_ENTITLEMENT_IDENTIFIER=健康Pro
REVENUECAT_PRODUCTION_ENABLED=true
REVENUECAT_SYNC_MIN_INTERVAL_SECONDS=300
REVENUECAT_SYNC_TIMEOUT_SECONDS=8
REVENUECAT_WEBHOOK_MAX_ATTEMPTS=8
REVENUECAT_WEBHOOK_RETRY_BASE_SECONDS=60
```

RevenueCat API v2 基础地址为 `https://api.revenuecat.com/v2`；服务端先使用 `GET /projects/{project_id}/customers/{customer_id}/active_entitlements` 读取当前有效权益，再以 `GET /projects/{project_id}/customers/{customer_id}/subscriptions?environment=production` 校验正式环境和补全订阅明细。Secret API Key 需要 `customer_information:customers:read` 与 `customer_information:subscriptions:read` 两项只读权限。active-entitlements 返回的是内部 `entitlement_id`，所以 `REVENUECAT_ENTITLEMENT_ID` 必须填写该内部 ID；缺失时同步失败关闭，绝不误授予 Pro。 [API v2 Customer Resources](https://www.revenuecat.com/docs/api-v2/customer/resources), [Entitlement API](https://www.revenuecat.com/docs/api-v2/entitlement)

设计级伪代码（不是当前代码修改）：

```python
@transaction.atomic
def sync_user(*, user, reason: str) -> SubscriptionSummary:
    identity, _ = RevenueCatCustomerIdentity.objects.select_for_update().get_or_create(
        user=user,
        defaults={"app_user_id": str(user.id)},
    )
    if identity.app_user_id != str(user.id):
        raise SubscriptionError("identity_conflict")

    provider_result = revenuecat_client.get_active_entitlements(
        customer_id=identity.app_user_id,
        environment="production",
    )
    update_entitlement_snapshot(user=user, provider_result=provider_result)
    identity.last_successful_sync_at = timezone.now()
    identity.last_sync_error_code = ""
    identity.save(update_fields=["last_successful_sync_at", "last_sync_error_code", "updated_at"])
    return ProEntitlementResolver.resolve(user=user)
```

```python
def resolve(*, user) -> SubscriptionSummary:
    revenuecat_active = RevenueCatEntitlement.objects.filter(
        user=user,
        entitlement_identifier=settings.REVENUECAT_ENTITLEMENT_IDENTIFIER,
        environment="production",
        status="active",
    ).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())).exists()
    trial = TrialService.build_pro_summary(user=user)
    return SubscriptionSummary.from_sources(revenuecat_active=revenuecat_active, trial=trial)
```

## 24. iOS 客户端落地与状态边界

### 24.1 真实现有文件与必须修改点

| 文件 | 当前事实 | 实施要求 |
|---|---|---|
| `Core/Subscriptions/RevenueCat/RevenueCatClient.swift` | 已 configure、`logIn`、`logOut` | 返回可观察的绑定结果；暴露当前 identity 状态，不能把绑定失败静默当作可购买状态 |
| `App/.../AppLifecycleCoordinator.swift` | 登录准备中调用 `identify`，但失败只记录日志并继续 | 增加 SubscriptionSyncCoordinator；绑定失败不阻塞普通登录，但必须使购买/恢复入口禁用并展示可重试状态 |
| `Features/Settings/Subscription/RevenueCatSubscriptionSection.swift` | 直接刷新 Offering、恢复购买、调用 Paywall coordinator | 改为先校验已绑定，再由同步协调器处理购买/恢复后的服务端同步和提示 |
| `App/.../SignedInMainTabHostView.swift` | 已使用一个 `HomeFullScreenCover` 承载 Paywall | 保持单一 presentation owner；回调只发出“购买/恢复完成”，由协调器关闭并同步，禁止再新增嵌套 cover |
| `Core/Domain/Entities/UserSession.swift` | `isPro` 是 `let` | 增加不可变复制方法，例如 `replacing(isPro:)`，不在 View 中直接改字段 |
| `App/.../AppSessionStore.swift` | 只有 setAuthenticated / setSignedOut | 增加原子 `replaceCurrentSession`：校验同 accountID、更新内存、保存 SessionSnapshotStore |
| `Features/Auth/Infrastructure/SessionSnapshotStore.swift` | 当前可保存完整 UserSession | 仅通过 AppSessionStore 更新，避免内存会话和快照分裂 |

### 24.2 建议新增客户端模块

```text
SparkClient/Projects/Core/Subscriptions/
├── RevenueCat/RevenueCatClient.swift                 # 已存在，扩展 identity 状态
├── RevenueCat/RevenueCatConfiguration.swift          # 已存在，改为构建配置读取 Public Key
├── Networking/SparkSubscriptionAPI.swift             # 新增：me/sync DTO 与请求
├── Domain/SubscriptionSummary.swift                  # 新增：服务端订阅摘要
└── Application/SubscriptionSyncCoordinator.swift     # 新增：生命周期、限流、重试、Session 原子更新
```

### 24.3 客户端状态机

```text
unbound → binding → bound
                   ├── syncIdle
                   ├── syncing
                   ├── pendingRetry
                   └── failedRetryable

任何状态 → signedOut → resetIdentity → unbound
```

- 普通登录可在 `binding` 时进入主界面；订阅购买和恢复按钮必须在 `bound` 前禁用。
- Paywall 只允许在 `bound + offeringLoaded + noActiveFullScreenCover` 时打开。
- `.onPurchaseCompleted` / `.onRestoreCompleted` 先更新本地展示、关闭当前 cover，再异步调用服务端 sync；不得在回调内新建第二个 `fullScreenCover`。
- 前台恢复只触发一次受冷却限制的同步；并发的登录、前台和购买回调合并到同一个 coordinator Task。
- 服务端摘要返回 `isPro=true` 后，调用 `AppSessionStore.replaceCurrentSession`；若仅 RevenueCat 本地 CustomerInfo 为 active 而服务端同步尚未成功，界面可显示“权益同步中”，但 AI/云端 Pro API 仍以服务端 403/订阅摘要为准。
- iOS 只保存 Public SDK Key；Production/Sandbox Key 由 Build Configuration / xcconfig 注入，不能把 Secret、Webhook Authorization 或项目管理凭据打入包内。

设计级 Swift 伪代码（不是当前代码修改）：

```swift
func handlePurchaseCompleted(_ customerInfo: CustomerInfo) {
    paywallCoordinator.apply(customerInfo)
    paywallCoordinator.dismiss()
    activeHomeFullScreenCover = nil
    subscriptionSyncCoordinator.schedule(.purchaseCompleted)
}

func applyServerSummary(_ summary: SubscriptionSummary, session: UserSession) async {
    guard summary.accountID == session.accountID else { return }
    appSessionStore.replaceCurrentSession(session.replacing(isPro: summary.isPro))
}
```

## 25. 安全、审计、重试与配置细则

### 25.1 安全边界

- RevenueCat Secret API Key、Webhook Authorization 与 Project ID 只允许部署环境读取；日志、异常、后台返回和测试快照均不得回显。
- Webhook 使用 HTTPS，拒绝缺失或不匹配的 Authorization Header；使用 `compare_digest`，不以来源 IP 作为唯一信任依据。
- 客户端 sync 只根据 JWT 的 `request.user` 查询本人数据；无 user ID 参数，防止枚举可递增 accountID。
- `original_transaction_id`、alias、App User ID、Webhook 原始 JSON 在后台默认脱敏；仅具备后台权限者可查看受限审计字段。
- 所有后台重放/重新同步记录 `operator_id`、request ID、事件 ID/用户 ID、原因、发起时间和结果；不得记录凭据。

### 25.2 重试与失败分类

| 场景 | 客户端 | 服务端 |
|---|---|---|
| RevenueCat 429/5xx/网络超时 | 显示同步中；有限退避；前台恢复/手动刷新 | 标记 retryable，指数退避，保留最后成功快照 |
| Webhook 重复 | 不适用 | event ID 冲突后直接 HTTP 200，不重复处理 |
| 用户未匹配 | 不适用 | `unmatched`，按下一次重试时间处理，后台可重放 |
| Identity 冲突 | 禁止购买/恢复，提示联系客服 | 409 + 审计；不自动改写身份关系 |
| entitlement 已过期 | 刷新服务端 Session 后降级界面 | Resolver 仅允许到期前的 active Production 快照 |
| 取消续费 | 保持到期日前界面权益 | 不提前撤权，等待当前 entitlement/到期状态 |

每次 Celery 重试需以 `attempt_count` 和 `next_retry_at` 控制，指数退避上限 6 小时；超过最大尝试次数进入 `failed`。人工重放不是无限循环：每次重放追加操作审计，并从尝试上限策略重新计算。

### 25.3 最低可观测性（符合“不新增专项告警”）

不新增 Pager/短信/邮件告警，但必须提供后台可查询的计数：`received`、`processing`、`retryable`、`unmatched`、`failed`，最近一次成功对账时间和最近 Provider 错误码。日志统一携带 `request_id`、`event_id`（如有）、`user_id`（内部日志）、`reason` 和 `environment`，禁止记录 Authorization 与 Secret。

## 26. 测试、验收与发布门禁

### 26.1 服务端自动化测试

- 模型：identity 一对一、alias 唯一、entitlement 环境唯一、event ID 幂等、旧 provider 时间不得覆盖新快照。
- Resolver：仅 Production `健康Pro` 生效；有效 TrialApplication 或 manual grant 可独立使 `is_pro=true`；三者均无效则 false。
- sync API：未认证 401、未传用户 ID、冷却命中、并发请求、Identity 冲突、Provider 成功/超时/429、摘要格式与现有 response wrapper 一致。
- webhook：Authorization 缺失/错误、重复 event ID、畸形 JSON、未匹配、TRANSFER 双用户排队、取消不提前失效、重放审计。
- Celery：任务幂等、`select_for_update`、退避、最大重试、增量候选集和每日异常扫描。
- 回归：`accounts/services/login_service.py` 与 `ai_config/views.py` 改为 Resolver 后，既有自动试用、申请试用和后台人工授权测试仍通过。

### 26.2 iOS 测试与人工验收

- 收到有效服务端会话后先完成 `logIn(String(accountID))`，再允许打开 Paywall；绑定失败时购买/恢复入口禁用且可重试。
- 同一个账号冷启动、前台恢复和购买回调并发时，只产生一条有效同步请求和一个 Paywall presentation。
- 年度、月度、3 天试用产品均映射 `健康Pro`；恢复购买后 Session 来自服务端摘要更新。
- 购买后服务端短暂不可用：Paywall 关闭、出现“权益同步中”、后续重试成功后更新 Session；客户端 CustomerInfo 不能越过服务端 API 鉴权。
- 账号 A 退出、账号 B 登录后，不保留 A 的 CustomerInfo、Offering 状态、isPro 快照或后台同步任务结果。
- Sandbox 购买可以在测试环境显示，但 Production Resolver 永远不授予正式权限。
- 续费、取消、到期、退款、重复 Webhook、延迟 Webhook、跨设备恢复和内部人工授权组合均符合最终 Resolver 结果。

### 26.3 发布门禁

1. RevenueCat 控制台：生产 App、`健康Pro` entitlement、`standard` Offering、月度/年度产品映射及隐私/服务条款链接已核验。
2. Sandbox Webhook：Authorization、HTTPS、Inbox 入库、异步处理、重试、重放和环境过滤均已验证。
3. Production 配置：Secret/Authorization 已注入，未进入 Git、iOS 包和日志；数据库迁移已完成且可回滚。
4. 服务端 API 和 Resolver 自动化测试通过；iOS 编译、单元测试与 Sandbox 手工验收由实施阶段执行。
5. 先灰度启用服务端同步和 Production Webhook，再发布 iOS；确认快照与现有 TrialApplication 权限一致后，才将所有 Pro API 切至 Resolver。

## 27. 实施任务拆分（可直接创建子工单）

| 顺序 | 子任务 | 范围 | 完成定义 |
|---:|---|---|---|
| 1 | SUBS-DB | 新建 subscriptions app、模型、迁移、管理员只读注册 | 迁移可前向/回滚；唯一约束与索引测试通过 |
| 2 | SUBS-SERVER-CORE | RevenueCat Client、同步服务、Resolver、替换登录/AI 权限入口 | Resolver 成为唯一服务端授权入口，旧 Trial 行为回归通过 |
| 3 | SUBS-WEBHOOK | Webhook endpoint、Inbox、Celery、重试、对账 | 重复/乱序/未匹配/TRANSFER 可恢复且有审计 |
| 4 | SUBS-ADMIN | 后台订阅状态、事件查看、重放与重新同步 | 只读和操作权限分离，不可直接改 RevenueCat 订阅 |
| 5 | SUBS-IOS | Subscription API、同步协调器、Session 原子更新、绑定门禁、Paywall 回调 | 不重叠 presentation；购买后按服务端摘要更新 Session |
| 6 | SUBS-QA-RELEASE | 自动化、Sandbox 联调、灰度、Production 核验 | 满足第 26 节门禁后才允许正式切换 |

## 28. 实施记录（2026-09-22）

- 已完成 `subscriptions` app、初始迁移、统一 `ProEntitlementResolver`、登录/会话/AI 权限入口替换。
- 已完成 RevenueCat identity 绑定、Webhook Inbox、异步重试、生产环境订阅校验、6 小时对账与后台重放。
- 已完成 iOS 订阅同步 API、身份绑定门禁、购买/恢复后的服务端同步与 Session 更新；Paywall 维持唯一 full-screen cover。
- 已完成后台“订阅与权益”页面、RBAC 菜单与重放/重新同步权限码。
- MySQL 使用 `utf8mb4` 时，参与索引和唯一约束的 App User ID / alias 字段限制为 255 字符；完整的第三方 Webhook 内容仍只保存在 `payload` JSON 中。
- 本次按实施要求未编译、未运行自动化测试，也未执行数据库迁移；第 26 节门禁必须在部署环境完成后才能视为上线完成。
