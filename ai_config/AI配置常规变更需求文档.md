# AI 配置常规变更需求文档

> 范围说明：本文按工单管理 `SparkService/ai_config` 及对应客户端 AI 设置页的常规变更需求。工单号从 `000001` 递增，新增需求追加在文档底部。本文只描述需求、实现方式、涉及文件和验收口径，不代表代码已实现。

## 工单索引

| 工单号 | 工单名 | 状态 | 范围 |
| --- | --- | --- | --- |
| `AI-CONFIG-000001` | 中国大陆用户才展示 Pro 试用申请入口 | 已实现 | 客户端 `AITrialSettingsView` 展示条件、`SparkSystemInfo` 统一国家标识判断 |
| `AI-CONFIG-000002` | 试用申请提交后请求通知权限并通过通知刷新 Pro 模型 | 已实现 | 客户端提交申请、通知权限、公共通知接收、刷新服务端 Pro 模型列表 |
| `AI-CONFIG-000003` | 服务端试用申请延迟自动审核与 APNs 通知 | 已实现 | `TrialApplication` 申请次数、延迟自动通过、通过/拒绝触发公共 APNs 通知 |
| `AI-CONFIG-000004` | 登录自动 Pro 发放仅限中国设备 | 已实现 | `TrustedDevice` 增加国家登记；登录成功后仅中国设备立即自动发放 Pro |
| `AI-CONFIG-000005` | 同一设备换用户首次登录自动 Pro 发放修复 | 已实现 | 同一安装上 A1 退出后 B1/C1 首次登录也应按用户维度发放 15 天 Pro |
| `AI-CONFIG-000006` | 场景下支持同一基座模型配置多个智能体 | 已实现 | 后台同场景允许添加多个同底模 agent；bootstrap 返回 agent 唯一名和 baseModelName |
| `AI-CONFIG-000007` | 场景模型绑定增加显示名称 | 新需求/待实现 | `AIScenarioModelBinding` 增加必填显示名称；后台表单维护；bootstrap 使用绑定显示名称 |

## 工单 `AI-CONFIG-000001`：中国大陆用户才展示 Pro 试用申请入口

### 1. 背景

### Q：为什么 Pro 试用入口需要限制展示区域？

A：`APIKeysSettingsView` 当前在列表顶部无条件展示 `AITrialSettingsView`：

客户端位置：

```text
/Users/hua/Downloads/Reference/SparkClient/SparkClient/Projects/Features/AISettings/Presentation/Providers/APIKeysSettingsView.swift:23-24
```

现状：

```swift
List {
    AITrialSettingsView(viewModel: viewModel)

    Section(...)
}
```

本需求要求：**只有中国大陆用户才展示试用入口**。非中国大陆用户不展示该入口，不影响普通 Provider API Key 配置。

### 2. 判定规则

### Q：如何判断用户是否在中国大陆？

A：本工单改为 **完全客户端判断**，不依赖服务端 IP，不改造服务端。判断逻辑统一收敛到 `SparkSystemInfo`，由客户端直接返回“应用最可能的国家标识”。

客户端需要综合以下本机信号：

1. 手机地区：系统 Locale region，例如 `CN`。
2. 使用语言：首选语言包含 `zh-Hans`、`zh-CN`、`zh-Hans-CN` 等简体中文/中国大陆倾向。
3. 当前系统语言/地区的组合：例如简体中文 + 中国大陆地区时强判为 `CN`。
4. 登录手机号国家/地区默认值：`LoginConductor.swift` 中的国家/地区归纳应迁移到 `SparkSystemInfo`，避免登录和 AI 设置各自维护国家判断。
5. `PhoneLoginView` 默认地区不能再固定为中国地区，应使用 `SparkSystemInfo.mostLikelyCountryCode` 匹配默认地区。

统一能力：

```swift
nonisolated struct SparkSystemInfo {
    /// 返回应用最可能的 ISO 3166-1 alpha-2 国家/地区标识，例如 "CN"、"US"、"HK"。
    /// 仅基于客户端本机信息推断，不依赖服务端。
    var mostLikelyCountryCode: String { ... }

    /// 是否最可能位于中国大陆。
    var isMostLikelyMainlandChina: Bool {
        mostLikelyCountryCode == "CN"
    }
}
```

| 信号 | 来源 | 可信度 | 用途 |
| --- | --- | --- | --- |
| 手机地区 | 客户端 `Locale.current.region` / `regionCode` | 高 | 主要依据 |
| 系统语言 | 客户端 `Locale.preferredLanguages` / `languageCode` | 中 | 辅助判断 |
| 登录默认国家/区号 | 客户端 `LoginConductor` 现有地区表 | 中 | 与登录页默认国家保持一致 |

建议展示条件：

```text
showTrialEntry = SparkSystemInfo().isMostLikelyMainlandChina
```

说明：

1. `SparkSystemInfo.regionCode == "CN"` 时直接返回 `CN`。
2. `Locale.preferredLanguages` 明确为中国大陆简体中文时，返回 `CN`。
3. 如果 region 为空，可根据语言和登录地区默认策略兜底。
4. 如果无法判断，返回空字符串或保守返回系统 region；Pro 试用入口默认不展示。
5. 服务端不提供 IP 地理位置，不新增 geo endpoint，不修改 bootstrap/trial status 响应。

### 3. 客户端实现建议

### Q：客户端应该在哪里控制展示？

A：在 `APIKeysSettingsView` 内把 `AITrialSettingsView` 从无条件展示改为条件展示：

```swift
if viewModel.shouldShowTrialEntry {
    AITrialSettingsView(viewModel: viewModel)
}
```

`shouldShowTrialEntry` 建议由 `AISettingsViewModel` 提供，不建议在 View 里直接散落判断逻辑。

### Q：客户端需要新增什么能力？

A：

1. 在 `SparkSystemInfo` 增加 `mostLikelyCountryCode` 方法/计算属性。
2. 在 `SparkSystemInfo` 增加 `isMostLikelyMainlandChina` 便捷判断。
3. 读取本机地区：现有 `regionCode` 可复用。
4. 读取本机语言：现有 `languageCode` 以及 `Locale.preferredLanguages` 可复用。
5. 将 `LoginConductor.swift:8-55` 里国家/地区相关公共能力归纳到 `SparkSystemInfo` 或与其配套的国家工具模型中统一处理。
6. `AISettingsViewModel` 暴露 `shouldShowTrialEntry = SparkSystemInfo().isMostLikelyMainlandChina`。

### 4. 国家标识统一处理

### Q：为什么要把 `LoginConductor` 的国家逻辑归纳到 `SparkSystemInfo`？

A：当前 `LoginConductor.swift:8-55` 定义了 `PhoneRegion` 和 `defaultRegions`，包含国家/地区名称、区号和 flag。这些信息只服务登录页，但“应用最可能国家标识”以后会被多个模块使用，例如：

1. AI Pro 试用入口展示。
2. 登录页默认国家/区号。
3. 设备注册时区域信息。
4. 后续区域化功能开关。

因此国家标识需要系统内统一处理：

1. `SparkSystemInfo` 负责输出最可能国家标识。
2. 登录页可继续保留 `PhoneRegion` UI 模型，但默认选中地区应从 `SparkSystemInfo.mostLikelyCountryCode` 推导。
3. AI 设置页不直接读取 `Locale`，只消费 `SparkSystemInfo` 的结果。
4. 不在 `AISettingsViewModel`、`APIKeysSettingsView`、`LoginConductor` 内重复实现国家判断。

### Q：`PhoneLoginView` 默认地区如何调整？

A：当前 `PhoneLoginView` 的默认地区是：

```swift
@State private var chosenRegion: PhoneRegion = defaultRegions.first ?? .init(name: L10n.text("auth.region.cn"), dial: "+86", flag: "🇨🇳")
```

由于 `defaultRegions.first` 是中国大陆，所以登录页默认永远是 `+86`。需要改为：

1. `SparkSystemInfo.mostLikelyCountryCode` 返回最可能国家标识。
2. `PhoneRegion` 增加统一国家标识字段，例如 `countryCode: String`。
3. `defaultRegions` 每个地区补充 `countryCode`，如 `CN/HK/TW/US/JP`。
4. `PhoneLoginView` 初始化默认地区时，优先匹配 `SparkSystemInfo.mostLikelyCountryCode`。
5. 匹配不到时再 fallback 到中国大陆或产品指定默认地区。

建议逻辑：

```swift
let country = SparkSystemInfo().mostLikelyCountryCode
let initialRegion = defaultRegions.first { $0.countryCode == country }
    ?? defaultRegions.first { $0.countryCode == "CN" }
    ?? defaultRegions[0]
```

验收重点：美国地区设备默认显示 `+1`，日本地区设备默认显示 `+81`，中国大陆地区设备默认显示 `+86`。

### 5. 涉及文件

| 端 | 文件 | 改动内容 |
| --- | --- | --- |
| 客户端 | `SparkClient/.../APIKeysSettingsView.swift` | `AITrialSettingsView` 改为条件展示 |
| 客户端 | `SparkClient/.../AISettingsViewModel.swift` | 增加 `shouldShowTrialEntry` 或等价状态 |
| 客户端 | `SparkClient/Projects/Foundation/Utilities/SparkSystemInfo.swift` | 增加 `mostLikelyCountryCode`、`isMostLikelyMainlandChina`，统一国家标识推断 |
| 客户端 | `SparkClient/.../LoginConductor.swift` | `PhoneRegion` 增加 `countryCode`；`PhoneLoginView` 默认地区改为消费 `SparkSystemInfo.mostLikelyCountryCode` |
| 服务端 | 无 | 本工单不改服务端，不新增 IP 判断，不新增 geo API |

### 6. 验收标准

1. `SparkSystemInfo.regionCode == "CN"` 时能看到 Pro 试用申请入口。
2. `Locale.preferredLanguages` 明确为中国大陆简体中文时能看到 Pro 试用申请入口。
3. 非中国大陆地区/语言组合默认看不到 Pro 试用申请入口。
4. 普通 Provider 列表不受影响。
5. 切换系统语言/地区后，重新进入设置页能重新计算展示状态。
6. 登录页默认国家/区号与 `SparkSystemInfo.mostLikelyCountryCode` 保持一致，不再默认固定为中国大陆。
7. 美国地区设备首次进入手机号登录默认 `+1`，日本地区默认 `+81`，中国大陆地区默认 `+86`。
8. 服务端 `ai_config` 不因本工单发生接口或模型改造。

## 工单 `AI-CONFIG-000002`：试用申请提交后请求通知权限并通过通知刷新 Pro 模型

### 1. 背景

### Q：为什么提交申请后需要通知权限？

A：服务端不会在提交接口里直接返回最终审核结果，而是异步审核。客户端需要通过 APNs 通知用户“申请已通过”或“申请未通过”，并在收到通知后刷新 Pro 模型列表。

客户端现状：

| 文件 | 当前能力 |
| --- | --- |
| `AITrialSettingsView.swift` | 点击按钮后调用 `viewModel.submitTrialApplication()` |
| `AISettingsViewModel.swift:252-267` | `submitTrialApplication()` 当前调用 `aiConfigAPI.applyTrial()` 后直接把返回状态写入 snapshot |
| `AIConfigAPI.swift:73-97` | `applyTrial()` 当前解析 `RemoteTrialStatusPayload` |
| `PushAdapter.swift:55-78` | 已有请求通知权限与注册 APNs token 的能力 |
| `PushAdapter.swift:93-126` | 前台收到通知、点击通知都会进入 `HandleRemoteNotificationUseCase` |

### 2. 提交申请后的客户端流程

### Q：提交试用申请后客户端要做什么？

A：

1. 用户点击申请。
2. 客户端调用 `/api/v1/ai/trial/apply/`。
3. 服务端返回“提交成功”，不返回最终审核结果。
4. 客户端提示用户申请已提交。
5. 客户端检查应用通知权限。
6. 如果未授权，先展示应用内说明：“我们将统一通知你”。
7. 用户确认后触发系统通知权限请求。
8. 若授权成功，注册 APNs 并上报 device token / notifications_enabled。
9. 等待服务端审核通知。

### Q：系统通知权限文案能否直接自定义为“我们将统一通知你”？

A：iOS 系统权限弹窗文案不能由应用完全自定义。因此需要先展示应用内解释弹窗/提示，文案为：

```text
我们将统一通知你
```

用户点击继续后，再调用系统 `UNUserNotificationCenter.requestAuthorization`。

### 3. 通知接收后的刷新规则

### Q：收到通过/拒绝通知后需要刷新什么？

A：只要收到与试用申请审核相关的通知，无论 App 处于前台、后台点击进入，还是冷启动后处理通知，都需要刷新：

1. 服务端 Pro 模型列表：调用 `AIConfigCenter.refreshRemoteConfig()`。
2. 系统内通用可用模型：重新 reload 本地 AI settings snapshot / effective scenario bundles。
3. 试用状态：调用 `fetchTrialStatus()`。
4. AI 设置页 UI：如果当前在设置页，需要刷新 `AISettingsViewModel.snapshot`。
5. 对话模型选择器：后续进入对话或刷新时能看到新的 Pro 模型。

### Q：通知 payload 需要什么字段？

A：建议服务端 APNs payload 中包含：

```json
{
  "type": "ai_trial_application_result",
  "status": "active",
  "application_id": 123,
  "refresh_ai_config": true
}
```

拒绝：

```json
{
  "type": "ai_trial_application_result",
  "status": "rejected",
  "application_id": 123,
  "refresh_ai_config": true
}
```

客户端 `HandleRemoteNotificationUseCase` 识别该类型后执行刷新。

### 4. 涉及文件

| 端 | 文件 | 改动内容 |
| --- | --- | --- |
| 客户端 | `AITrialSettingsView.swift` | 提交成功后触发通知权限检查/解释弹窗 |
| 客户端 | `AISettingsViewModel.swift` | `submitTrialApplication()` 改为处理“提交成功”，不依赖最终状态；增加通知刷新入口 |
| 客户端 | `AIConfigAPI.swift` | `applyTrial()` 响应模型改为提交结果 DTO |
| 客户端 | `PushAdapter.swift` | 复用 `requestAuthorizationIfNeeded()` 或补充可等待结果的请求方法 |
| 客户端 | `HandleRemoteNotificationUseCase` | 识别 `ai_trial_application_result`，触发 AI 配置刷新 |
| 客户端 | `RegisterDeviceUseCase` / `DeviceAPI` | 授权结果与 APNs token 上报到服务端 |

### 4.1 客户端解码约束

### Q：客户端响应字段如何对齐？

A：客户端 AI 配置相关接口已经使用统一解码机制，不要在业务层手动对齐字段。

现有统一入口：

```swift
APIResponseDecoder.decodeWrappedData(...)
JSONDecoder.default
JSONEncoder.default
RemoteAIBootstrapPayload
RemoteTrialStatusPayload
AIScenarioRemoteModelRow.init(from:)
AIScenarioRemoteBundlesCollection.init(from:)
```

项目已实现默认编码策略：

```swift
nonisolated static var `default`: JSONEncoder {
    let encoder = JSONEncoder()
    // 模型驼峰命名 → JSON 下划线命名（例：userName → user_name）
    encoder.keyEncodingStrategy = .convertToSnakeCase
    // 日期编码：使用 ISO8601 标准格式
    encoder.dateEncodingStrategy = .iso8601
    return encoder
}
```

对应解码也应统一走默认策略：

```swift
JSONDecoder.default
// keyDecodingStrategy = .convertFromSnakeCase
// dateDecodingStrategy = .iso8601
```

要求：

1. 新增 `applyTrial()` 提交结果 DTO 时，只在 `AIConfigAPI.swift` 的 Remote DTO / `toModel()` 层处理字段映射。
2. 不要在 `AISettingsViewModel`、`AITrialSettingsView` 或其他 UI 层手动读取字典、手动判断 snake_case/camelCase。
3. 不要为了普通字段映射手写 `CodableKey`；驼峰转下划线、下划线转驼峰、ISO8601 日期统一依赖 `JSONEncoder.default` / `JSONDecoder.default`。
4. 如果服务端返回从 `RemoteTrialStatusPayload` 改为提交结果 payload，应新增专用 `RemoteTrialApplySubmissionPayload`，不要复用状态模型再靠业务层忽略字段。
5. UI 层只消费领域模型，例如 `AITrialApplicationSubmission` 或 `AITrialState`，不直接消费原始 JSON。
6. 只有字段存在历史兼容、多名称兜底、非标准日期、嵌套结构重塑等特殊情况，才允许在 DTO 内自定义 `init(from:)`；普通新增字段不允许手动对齐。

### 5. 验收标准

1. 提交申请后客户端只展示“提交成功/等待通知”，不直接显示最终通过。
2. 未开启通知权限时，先出现应用内说明“我们将统一通知你”。
3. 用户继续后触发系统通知权限请求。
4. 用户允许通知后，APNs token 正常上报服务端。
5. 用户拒绝通知后，服务端设备 `notifications_enabled` 更新为 false。
6. 前台收到通过通知时，不弹系统 banner，但应用内能刷新 Pro 模型。
7. 后台点击通过通知进入 App 后，刷新 Pro 模型。
8. 收到拒绝通知后，刷新试用状态并不展示 Pro 模型。

## 工单 `AI-CONFIG-000003`：服务端试用申请延迟自动审核与 APNs 通知

### 1. 背景

### Q：当前服务端试用申请逻辑是什么？

A：当前服务端位置：

| 文件 | 现状 |
| --- | --- |
| `SparkService/ai_config/services.py:61-92` | `TrialService.apply_trial()` 根据 `AI_TRIAL_AUTO_APPROVE_APPLICATIONS` 决定立即 active 或 pending |
| `SparkService/ai_config/views.py:317-339` | `TrialApplyView.post()` 返回完整 trial status |
| `SparkService/ai_config/models.py:270-309` | `TrialApplication` 使用 OneToOne 记录用户当前 trial 状态 |

新需求要求：**提交新的申请不要立即通过，统一返回提交成功，不返回最终审核结果**。

### 2. 服务端申请规则

### Q：自动审核规则是什么？

A：

| 用户申请次数 | 服务端行为 | 自动审核延迟 | 接口返回 |
| --- | --- | --- | --- |
| 第 1 次申请 | 自动通过 | 4 秒后 | 提交成功，不返回最终结果 |
| 第 2 次申请 | 自动通过 | 15 秒后 | 提交成功，不返回最终结果 |
| 第 3 次及以后 | 不自动通过，保持待审核 | 无 | 提交成功，不返回最终结果 |

说明：

1. “申请次数”按用户累计申请次数计算，不只看当前 `TrialApplication.status`。
2. 当前 `TrialApplication` 是 OneToOne，不足以完整记录多次申请历史；需要新增申请流水表，或在现有模型上增加 `application_count` 等字段。推荐新增流水表。

### 3. 数据模型建议

### Q：服务端需要新增哪些模型字段？

A：建议新增 `TrialApplicationRequest` 申请流水表：

```python
class TrialApplicationRequest(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="trial_application_requests", on_delete=models.CASCADE)
    sequence = models.PositiveIntegerField(db_index=True)
    status = models.CharField(max_length=16, choices=TrialApplication.Status.choices, default=TrialApplication.Status.PENDING, db_index=True)
    note = models.CharField(max_length=255, blank=True, default="")
    auto_approve_after_seconds = models.PositiveIntegerField(null=True, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
```

也可以在 `TrialApplication` 增加：

```python
application_count = models.PositiveIntegerField(default=0)
last_application_sequence = models.PositiveIntegerField(default=0)
```

但为了保留历史、审计和通知，推荐申请流水表。

### 4. 接口返回

### Q：`/api/v1/ai/trial/apply/` 应返回什么？

A：不再返回完整最终 trial status，而是返回提交结果：

```json
{
  "submitted": true,
  "application_id": 123,
  "sequence": 1,
  "status": "pending",
  "message": "申请已提交，请等待通知"
}
```

注意：

1. 即使 4 秒后会自动通过，提交接口也不返回 active。
2. 客户端不能根据提交响应解锁 Pro 模型。
3. Pro 模型只在后续通知/刷新状态后可用。

### 5. 延迟自动通过实现方式

### Q：4 秒/15 秒后自动通过怎么实现？

A：必须异步执行，不能阻塞 HTTP 请求。可选方案：

1. Celery / Django-Q / RQ 等任务队列：推荐。
2. 如果当前项目没有任务队列，可先使用统一后台任务机制；不要在 request thread 中 sleep。
3. 自动通过任务需要幂等：如果任务执行前已被人工拒绝，则不能再改为通过。

任务逻辑：

```text
apply_trial()
  创建申请流水 status=pending
  if sequence == 1: enqueue approve after 4s
  if sequence == 2: enqueue approve after 15s
  if sequence >= 3: 不 enqueue
  return submitted
```

自动通过任务：

```text
load application request
if request.status != pending: return
set request.status = active
update TrialApplication.status = active
set started_at / expires_at / approved_at
send APNs notification
```

### 6. 通过/拒绝通知

### Q：什么场景触发通知？

A：具体操作通过、拒绝都需要触发通知：

1. 自动通过：触发通知。
2. 后台人工通过：触发通知。
3. 后台人工拒绝：触发通知。

通知要求：

1. 使用公共通知流程。
2. 只进行 APNs 通知，不发 Email，不发 SMS。
3. 异步发送，不阻塞审核接口或任务。
4. payload 必须让客户端识别后刷新 AI Pro 模型。

建议调用：

```python
NotificationService.send_to_user_sync(
    campaign_id=None,
    user_id=user.id,
    channels=[NotificationMessage.Channel.APNS],
    title="试用申请已通过",
    body="你的 Pro 模型试用申请已通过，现在可以使用服务端模型。",
    payload={
        "type": "ai_trial_application_result",
        "status": "active",
        "application_id": application_id,
        "refresh_ai_config": True,
    },
    created_by_id=None,
)
```

拒绝通知：

```python
payload={
    "type": "ai_trial_application_result",
    "status": "rejected",
    "application_id": application_id,
    "refresh_ai_config": True,
}
```

### 7. 涉及文件

| 端 | 文件 | 改动内容 |
| --- | --- | --- |
| 服务端 | `SparkService/ai_config/models.py` | 新增申请次数/申请流水模型 |
| 服务端 | `SparkService/ai_config/services.py` | `apply_trial()` 改为创建 pending 申请并调度延迟任务 |
| 服务端 | `SparkService/ai_config/views.py` | `TrialApplyView.post()` 返回 submitted，不返回最终 status |
| 服务端 | `SparkService/ai_config/urls.py` | 如新增后台操作接口，需要补充路由 |
| 服务端 | `SparkService/accounts/services/notification_service.py` | 复用公共通知服务，仅 APNs |
| 服务端 | 后台任务模块 | 增加延迟自动审核任务 |
| 服务端 | 后台管理/运营接口 | 人工通过/拒绝时调用统一审核服务并触发通知 |

### 8. 验收标准

1. 第一次申请接口立即返回提交成功，不返回 active。
2. 第一次申请 4 秒后自动通过。
3. 第二次申请接口立即返回提交成功，不返回 active。
4. 第二次申请 15 秒后自动通过。
5. 第三次申请接口立即返回提交成功，但不会自动通过。
6. 自动通过后用户收到 APNs 通知。
7. 人工通过后用户收到 APNs 通知。
8. 人工拒绝后用户收到 APNs 通知。
9. 通知 payload 包含 `type=ai_trial_application_result` 和 `refresh_ai_config=true`。
10. 没有可用 APNs 设备时不影响审核状态更新，只记录通知 skipped/failed。

## 工单 `AI-CONFIG-000004`：登录自动 Pro 发放仅限中国设备

### 1. 背景

### Q：为什么还需要一个登录自动 Pro 工单？

A：`AI-CONFIG-000003` 处理的是“用户主动提交试用申请”的异步审核流程；本工单处理的是另一个独立入口：**登录成功后系统自动给符合条件的用户发放一次 Pro**。

当前登录流程里已经存在自动发放调用：

| 文件 | 当前调用点 |
| --- | --- |
| `SparkService/accounts/services/login_service.py:27` | `TrialService.grant_auto_trial_if_eligible(user=user)` |
| `SparkService/accounts/services/otp_service.py:292` | 邮箱 OTP 登录成功后调用 `TrialService.grant_auto_trial_if_eligible(user=user)` |
| `SparkService/accounts/services/otp_service.py:437` | 手机 OTP 登录成功后调用 `TrialService.grant_auto_trial_if_eligible(user=user)` |

后端现状已满足：登录触发的自动 Pro 发放由 `TrialService.grant_auto_trial_if_eligible(user:)` 处理，当前逻辑会直接写入 `TrialApplication(status=ACTIVE)`，不会进入 `apply_trial()` 的 4 秒/15 秒延迟申请流程。

本工单只补充国家校验：只有客户端登记为中国的设备才允许触发登录自动发放。

### 2. 设备国家登记

### Q：服务端为什么要在 `TrustedDevice` 增加国家字段？

A：客户端已经在 `SparkSystemInfo` 中统一实现“应用最可能国家标识”：

```text
SparkClient/SparkClient/Projects/Foundation/Utilities/SparkSystemInfo.swift:82-100
```

该值来自客户端本机信息，不依赖服务端 IP 或地理位置服务。登录自动发放需要以当前设备的客户端判断结果为准，因此服务端 `TrustedDevice` 需要增加一个可空国家字段，用于记录客户端上送的国家标识。

### Q：字段应该如何设计？

A：建议在 `SparkService/accounts/models.py:18-169` 的 `TrustedDevice` 增加字段：

```python
country_code = models.CharField(
    max_length=10,
    blank=True,
    default="",
    db_index=True,
    db_comment="客户端 SparkSystemInfo.mostLikelyCountryCode 推断的最可能国家/地区标识，可空",
)
```

设计说明：

1. `country_code` 使用 ISO 3166-1 alpha-2 风格，例如 `CN`、`US`、`JP`。
2. 字段允许为空字符串；空表示客户端无法判断或旧版本未上送。
3. `country_code` 与已有 `region_code` 不完全等价：
   - `region_code` 是系统地区原始信息。
   - `country_code` 是客户端统一推断后的“最可能国家标识”，用于业务开关判断。
4. 不使用服务端 IP 定位补齐该字段，避免客户端规则和服务端规则不一致。
5. 服务端需要新增 Django migration，保证历史设备记录默认空字符串。
6. 虽然当前按全新项目推进，仍需要考虑数据库迁移和历史空值：已有 `TrustedDevice` 行、旧版本客户端上报、测试环境遗留数据都应以空字符串落库，不反推、不补猜、不影响设备注册。

### Q：客户端上送什么字段？

A：客户端设备注册/刷新时，从 `SparkSystemInfo.mostLikelyCountryCode` 读取值，并随设备信息一起上送。

建议 Swift 请求模型字段命名为：

```swift
let countryCode: String
```

依赖客户端已有统一编码策略：

```swift
JSONEncoder.default
// keyEncodingStrategy = .convertToSnakeCase
```

因此请求 JSON 字段自动为：

```json
{
  "country_code": "CN"
}
```

注意：

1. 不要手写 `CodingKeys` 只为了把 `countryCode` 映射成 `country_code`。
2. 如果 `SparkSystemInfo.mostLikelyCountryCode` 返回空字符串，仍允许上送空值。
3. 服务端序列化/反序列化需要把 `country_code` 作为可选字段接收；不应因为旧客户端未传该字段导致设备注册失败。

### 3. 登录自动 Pro 发放规则

### Q：什么时候允许登录自动发放 Pro？

A：只有满足全部条件时才允许：

1. 用户登录成功。
2. 当前登录请求能定位到对应 `TrustedDevice`。
3. 该 `TrustedDevice.country_code == "CN"`。
4. 用户仍符合 `TrialService.grant_auto_trial_if_eligible` 原有资格条件，例如未领取过自动试用、未过期规则等。

如果 `country_code` 为空、缺失、不是 `CN`，都不触发自动发放。

### Q：没有国家字段时怎么办？

A：保守处理：**不自动发放**。

原因：

1. 自动发放 Pro 是权益发放，应该宁可少发，不应因无法判断而扩大范围。
2. 旧客户端未上送国家字段时，服务端无法确认用户是否属于中国设备。
3. 本需求明确要求：如果没有国家字段或为空，不进行自动发放。

### Q：是否需要服务端自己判断用户是不是中国用户？

A：不需要。本工单的国家来源是 `TrustedDevice.country_code`，也就是客户端 `SparkSystemInfo.mostLikelyCountryCode` 上送结果。

不做：

1. 不根据 IP 地址判断国家。
2. 不调用第三方 Geo 服务。
3. 不根据手机号区号替代设备国家字段。
4. 不根据 `Accept-Language` 或 User-Agent 在服务端二次推断。

### 4. 推荐实现方式

### Q：登录服务当前只有 `user`，如何拿到设备国家？

A：建议把“当前登录设备”解析为自动发放前置条件，而不是在 `TrialService` 内隐式查最新设备。

推荐流程：

```text
登录成功
  -> 根据当前请求 bundle_id + device_id 查找/关联 TrustedDevice
  -> 读取 trustedDevice.country_code
  -> country_code == "CN" 才调用 TrialService.grant_auto_trial_if_eligible(user=user)
  -> 非 CN / 空 / 找不到设备：跳过自动发放，只记录日志，不影响登录
```

推荐封装：

```python
def _try_grant_auto_trial_for_login_device(*, user, bundle_id: str, device_id: str, request_id: str):
    trusted_device = TrustedDevice.objects.filter(
        user=user,
        bundle_id=bundle_id,
        device_id=device_id,
        is_revoked=False,
    ).first()

    if not trusted_device or trusted_device.country_code != "CN":
        log skipped
        return

    TrialService.grant_auto_trial_if_eligible(user=user)
```

说明：

1. 不建议让 `TrialService.grant_auto_trial_if_eligible(user:)` 自己随意查“用户最近设备”，因为最近设备不一定是本次登录设备。
2. 更好的方式是增加显式参数，例如 `trusted_device` 或 `country_code`，让资格判断上下文明确。
3. 登录自动发放失败或跳过不能影响登录结果；只能记录 warning/info 日志。
4. 设备关联顺序需要确认：如果当前代码在自动发放后才调用 `DeviceLinkingService.try_attach_user_to_trusted_device`，应调整为先关联设备，再判断自动发放，或在自动发放判断中支持按 `bundle_id + device_id` 查匿名设备。

### Q：`TrialService` 是否需要改造？

A：建议轻量改造，不要把国家规则散落在三个登录调用点。

可选方案：

| 方案 | 做法 | 评价 |
| --- | --- | --- |
| A. 登录层判断国家后再调用原方法 | `_try_grant_auto_trial_for_login_device` 校验 `country_code == "CN"` 后调用 `grant_auto_trial_if_eligible` | 简单直接，改动少，适合当前需求 |
| B. `TrialService` 增加 `grant_auto_trial_if_eligible(user, country_code:)` | TrialService 统一处理自动发放资格，登录层只传国家 | 规则更集中，后续如果多入口复用更好 |
| C. `TrialService` 隐式查询用户设备 | 只传 user，服务内部查最新设备 | 不推荐，容易拿错设备，隐藏复杂度高 |

推荐 A 或 B。若未来“自动发放 Pro”不只发生在登录场景，优先选择 B。

### 5. Backoffice 试用管理页增强

### Q：`backoffice-web` 的 `/ai-config/trials` 当前需要解决什么？

A：当前页面已经能展示基础字段：

```text
申请人 / 状态 / 试用到期时间 / 创建时间 / 操作
```

示例数据：

```text
apple_000082 active 2026-06-12T11:01:36.623613Z 2026-05-28T11:00:38.715691Z 通过 拒绝 回收权限
```

现状问题是：状态仍展示英文 raw value，操作按钮没有完全按当前状态收敛，缺少“发放权限”和“详细”能力，也缺少操作弹窗里的用户设备国家、应用内通知权限等关键信息。

涉及现有文件：

| 端 | 文件 | 现状 |
| --- | --- | --- |
| 管理端前端 | `SparkService/backoffice-web/src/views/AITrialsView.vue` | `/ai-config/trials` 页面，当前直接展示 `status`，操作区展示通过/拒绝/回收权限 |
| 管理端前端 | `SparkService/backoffice-web/src/api/modules/ai.ts` | `TrialApplicationItem`、`fetchAITrials()`、`trialAction()` |
| 服务端 | `SparkService/backoffice/views.py:1351-1420` | `AdminAITrialListView`、`AdminAITrialActionView` |
| 服务端 | `SparkService/backoffice/serializers.py:643-669` | `AdminTrialApplicationSerializer`、`AdminTrialActionSerializer` |
| 服务端 | `SparkService/backoffice/urls.py` | `/api/admin/v1/ai/trials/` 与 `/api/admin/v1/ai/trials/{id}/{action}/` |

### Q：列表状态如何展示？

A：前端列表不直接展示 `active/pending/rejected/expired/none`，需要转换为中文标签。

建议映射：

| 后端 status | 中文展示 | 视觉建议 |
| --- | --- | --- |
| `pending` | 待审批 | 橙色/处理中 |
| `active` | 已有权限 | 绿色/成功 |
| `rejected` | 已拒绝 | 红色/失败 |
| `expired` | 已过期 | 灰色/失效 |
| `none` | 未申请 | 默认灰色 |

说明：

1. 筛选项也应使用中文文案，但请求参数仍传后端枚举值。
2. 列表中建议使用 `Tag` 或状态徽标展示，避免只显示纯文本。
3. 时间字段统一格式化为本地可读时间，例如 `YYYY-MM-DD HH:mm:ss`，不要直接展示 ISO 字符串。

### Q：操作按钮如何按状态展示？

A：操作区需要同时受“记录状态”和“当前管理员权限”控制，不能只根据权限全量展示。

按钮规则：

| 当前 status | 展示按钮 | 说明 |
| --- | --- | --- |
| `pending` | 通过、拒绝、详细 | 待审批只能审批或查看详情 |
| `active` | 回收权限、详细 | 已有权限不能再显示通过/拒绝 |
| `expired` | 发放权限、详细 | 已过期可重新手动发放 |
| `rejected` | 发放权限、详细 | 被拒绝后如运营确认可重新手动发放 |
| `none` | 发放权限、详细 | 无申请记录但运营可手动发放 |

权限规则：

1. `button:ai:trial:approve` 控制“通过”。
2. `button:ai:trial:reject` 控制“拒绝”。
3. `button:ai:trial:recycle` 控制“回收权限”。
4. 建议新增 `button:ai:trial:grant` 控制“发放权限”。
5. 建议新增 `button:ai:trial:detail` 控制“详细”；如果不新增权限，则复用列表查看权限。

### Q：“发放权限”弹窗如何设计？

A：点击“发放权限”后打开弹窗，允许运营设置试用授权时长。

弹窗内容：

1. 用户基本信息：用户 ID、用户名、邮箱、手机号/登录标识（如服务端可提供）。
2. 国家信息：展示最近/当前可信设备 `country_code`，并可辅助展示 `region_code`、`language_code`。
3. 应用内通知权限状态：展示最近/当前可信设备 `notifications_enabled`。
4. 发放时长快捷选项：`6 天`、`15 天`、`30 天`、`90 天`。
5. 自定义天数：支持手动录入正整数天数。
6. 备注：可选，用于审计。

交互要求：

1. 默认选中 `15 天`，与当前 `AI_TRIAL_DURATION_DAYS` 默认策略保持一致。
2. 切换快捷选项时同步自定义天数输入。
3. 手动录入时取消快捷选中或显示“自定义”。
4. 提交前二次确认，文案包含用户、国家、发放天数和到期时间。
5. 提交后刷新列表，并重新拉取该行详情。

服务端动作建议：

```text
POST /api/admin/v1/ai/trials/{trial_id}/grant/
body: { "days": 15, "note": "manual grant" }
```

或沿用现有 action endpoint：

```text
POST /api/admin/v1/ai/trials/{trial_id}/grant/
```

要求：

1. `days` 必填，必须为正整数，建议限制最大值，例如不超过 365 天。
2. 设置 `TrialApplication.status = active`。
3. 设置 `grant_source = manual`。
4. `started_at = now`。
5. `expires_at = now + days`。
6. `approved_at = now`，`rejected_at = None`。
7. 记录一条 `TrialApplicationRequest(source=manual, status=active)` 或等价审计流水，避免只有最终状态没有操作历史。

### Q：“详细”弹窗展示什么？

A：操作区增加“详细”，点击后弹窗打开试用详情页，不离开当前列表。

详情弹窗建议分三块：

1. 申请信息：
   - `TrialApplication.id`
   - 用户 ID、用户名、邮箱
   - `status` 中文状态
   - `grant_source`
   - `started_at`
   - `expires_at`
   - `applied_at`
   - `approved_at`
   - `rejected_at`
   - `note`
   - `created_at`
   - `updated_at`
2. 用户/设备信息：
   - 最新可信设备 ID
   - `country_code`
   - `region_code`
   - `language_code`
   - `platform`
   - `app_version`
   - `build_version`
   - `notifications_enabled`
   - `last_seen`
3. 申请流水 `TrialApplicationRequest`：
   - `id`
   - `source`
   - `sequence`
   - `status` 中文状态
   - `auto_approve_after_seconds`
   - `scheduled_at`
   - `approved_at`
   - `rejected_at`
   - `note`
   - `created_at`

服务端建议新增详情接口：

```text
GET /api/admin/v1/ai/trials/{trial_id}/
```

返回当前 `TrialApplication`、关联用户基础信息、最近可信设备信息、以及该用户的 `TrialApplicationRequest` 列表。列表接口保持轻量，不在表格页一次性返回全部流水，避免后续数据量上来后拖慢列表。

### Q：回收权限和发放权限后是否需要通知用户？

A：本工单先按 backoffice 权限管理能力补齐。通知可以复用 `AI-CONFIG-000003` 的公共 APNs 流程：

1. 发放权限成功：建议通知用户 Pro 权限已开通。
2. 回收权限成功：建议通知用户 Pro 权限已回收或已到期。
3. 如果当前阶段不做通知，也必须在接口和审计日志中记录操作人、操作时间、原因。

### 6. 涉及文件

| 端 | 文件 | 改动内容 |
| --- | --- | --- |
| 客户端 | `SparkClient/SparkClient/Projects/Foundation/Utilities/SparkSystemInfo.swift` | 使用 `mostLikelyCountryCode` 作为设备国家来源 |
| 客户端 | 设备注册/刷新请求模型 | 增加 `countryCode` 字段；由统一 encoder 自动编码为 `country_code` |
| 客户端 | 设备注册/刷新调用点 | 上送 `SparkSystemInfo().mostLikelyCountryCode`，允许空字符串 |
| 服务端 | `SparkService/accounts/models.py` | `TrustedDevice` 增加 `country_code` 可空字段与 migration |
| 服务端 | 设备注册 serializer / view / service | 接收并保存 `country_code`，旧客户端未传时默认为空 |
| 服务端 | `SparkService/accounts/services/login_service.py` | 登录成功后按当前设备国家判断，只有 `CN` 才立即自动发放 Pro |
| 服务端 | `SparkService/accounts/services/otp_service.py` | 邮箱 OTP、手机 OTP 登录成功后同样按当前设备国家判断 |
| 服务端 | `SparkService/ai_config/services.py` | 如选择方案 B，则 `TrialService` 增加显式国家/设备上下文参数 |
| 服务端 | `SparkService/backoffice/serializers.py` | 试用列表/详情 serializer 补充中文状态所需字段、用户信息、设备国家、通知权限、申请流水 |
| 服务端 | `SparkService/backoffice/views.py` | 试用列表补充详情数据来源；操作接口支持 `grant`、自定义天数、状态约束和审计 |
| 服务端 | `SparkService/backoffice/urls.py` | 新增 `GET /api/admin/v1/ai/trials/{trial_id}/` 或等价详情路由；确认 `grant` action 路由 |
| 管理端前端 | `SparkService/backoffice-web/src/api/modules/ai.ts` | Trial 类型补充状态标签、详情响应、设备信息、`grant` 请求参数 |
| 管理端前端 | `SparkService/backoffice-web/src/views/AITrialsView.vue` | 状态中文化；按状态展示操作按钮；新增发放权限弹窗和详细弹窗 |

### 7. 验收标准

1. 客户端设备注册请求包含 `country_code`，值来自 `SparkSystemInfo.mostLikelyCountryCode`。
2. `TrustedDevice.country_code` 能保存 `CN/US/JP` 等国家标识。
3. 旧客户端不传 `country_code` 时，设备注册仍成功，服务端保存为空字符串。
4. `country_code == "CN"` 的设备登录成功后，如果用户符合资格，立即生成或更新 `TrialApplication(status=ACTIVE)`。
5. `country_code == ""` 的设备登录成功后，不触发自动 Pro 发放。
6. `country_code != "CN"` 的设备登录成功后，不触发自动 Pro 发放。
7. 登录自动发放跳过或失败时，不影响 access token / refresh token 正常返回。
8. 服务端不使用 IP、手机号区号或服务端语言推断替代 `TrustedDevice.country_code`。
9. 邮箱 OTP、手机 OTP、Apple/密码等登录路径的自动发放规则保持一致，不出现某个登录入口绕过国家校验。
10. `/ai-config/trials` 列表状态展示为中文，不再裸露 `active/pending/rejected/expired`。
11. `pending` 状态只展示“通过、拒绝、详细”。
12. `active` 状态只展示“回收权限、详细”。
13. `expired/rejected/none` 状态展示“发放权限、详细”。
14. 点击“发放权限”弹窗可选择 `6/15/30/90 天`，也可手动录入天数。
15. 发放权限弹窗展示用户基本信息、国家、应用内通知权限状态。
16. 发放权限成功后，列表状态变为“已有权限”，到期时间按所选天数更新。
17. 点击“详细”弹窗能看到 `TrialApplication` 申请信息和 `TrialApplicationRequest` 流水。
18. `TrustedDevice.country_code` 新增 migration 后，历史/旧客户端数据为空值，不影响列表、详情、登录和设备注册。

## 工单 `AI-CONFIG-000005`：同一设备换用户首次登录自动 Pro 发放修复

### 1. 背景

### Q：当前发现了什么问题？

A：同一台设备 `0001` 上存在如下场景：

1. 首次下载 App。
2. 用户 A1 首次注册并登录设备 `0001`。
3. A1 没有 Pro 发放记录，系统正常自动发放 15 天 Pro。
4. A1 主动退出登录。
5. 用户 B1 在同一设备 `0001` 首次注册/登录。
6. B1 没有 Pro 发放记录，但 Pro 没有正常自动发放。
7. 用户 C1 在同一设备 `0001` 首次注册/登录，同样没有正常自动发放。

原始业务规则是：**用户登录时，只要该用户没有 Pro 发放记录，并且当前设备符合中国设备条件，就应自动发放 15 天 Pro。**

本问题不是“一个设备只能领一次 Pro”，而是同一设备换用户后，新的用户设备行缺少国家画像，导致用户维度的首次自动发放被误跳过。

### 2. 问题原因

### Q：为什么 A1 正常，B1/C1 不正常？

A：A1 首次下载后，未登录冷启动会先执行匿名设备登记：

```text
TrustedDevice(user=NULL, bundle_id=..., device_id=0001, country_code=CN)
```

A1 登录时，登录链路会把匿名设备行升级为 A1 用户设备行，因此 A1 的 `TrustedDevice.country_code` 仍然是 `CN`，自动发放判断通过：

```text
TrustedDevice(user=A1, device_id=0001, country_code=CN, is_revoked=false)
```

A1 退出后，设备行会保留为历史用户设备行：

```text
TrustedDevice(user=A1, device_id=0001, country_code=CN, is_revoked=true)
```

B1/C1 在同一设备直接登录时，已经没有 `user=NULL` 匿名设备行可升级。当前登录链路会为 B1/C1 创建一条新的用户设备行，但只写入 `bundle_id/device_id/user/is_revoked/request_id`，这条新设备行暂时没有 `country_code`：

```text
TrustedDevice(user=B1, device_id=0001, country_code="", is_revoked=false)
```

随后 `TrialService.try_grant_auto_trial_for_login_device(...)` 读取当前设备国家，发现 `country_code != CN`，于是跳过自动 Pro 发放。

### Q：问题发生在什么时机？

A：发生在登录流程中“创建/关联当前用户可信设备”之后、“计算并返回 `is_pro`”之前。

关键时序：

```text
登录成功创建/找到 User
  -> DeviceLinkingService.try_attach_user_to_trusted_device(...)
  -> DeviceService.ensure_user_device_profile_from_anonymous(...)
       没有匿名行时，创建当前用户 TrustedDevice，country_code 为空
  -> TrialService.try_grant_auto_trial_for_login_device(...)
       只读取当前用户设备行 country_code，空值时跳过自动发放
  -> TrialService.is_pro_user(user)
  -> 登录响应 is_pro=false
```

涉及位置：

| 文件 | 位置/职责 | 当前问题 |
| --- | --- | --- |
| `SparkService/accounts/services/login_service.py` | `_prepare_login_entitlements(...)` | Apple/密码等登录入口先关联设备，再自动发放 Pro |
| `SparkService/accounts/services/otp_service.py` | OTP 登录成功后设备关联与自动发放 | 邮箱/手机号 OTP 路径同样存在该时序 |
| `SparkService/accounts/services/device_linking_service.py` | 登录后设备画像关联入口 | 委托 `DeviceService.ensure_user_device_profile_from_anonymous(...)` |
| `SparkService/accounts/services/device_service.py` | `ensure_user_device_profile_from_anonymous(...)` | 无匿名行时直接创建空画像用户设备行，当前用户设备行可能没有国家 |
| `SparkService/ai_config/services.py` | `try_grant_auto_trial_for_login_device(...)` | 只依赖当前用户设备行 `country_code == CN`，空值时没有按同安装历史设备行兜底 |

### 3. 修复目标

### Q：这个工单要达成什么？

A：

1. 自动 Pro 发放仍然是**用户维度**，不能变成设备维度。
2. 同一设备上 A1 已经领取过 Pro，不影响 B1/C1 作为新用户首次登录领取 Pro。
3. 只有当前设备国家为 `CN` 时才自动发放。
4. 如果 B1/C1 没有 `TrialApplication` 或状态为 `none` 且从未开始过试用，应立即发放 15 天 Pro。
5. 登录响应里的 `is_pro` 必须反映发放后的真实状态，不能登录返回 `false` 后再依赖后续设备登记补发。

### 4. 推荐实现方案

### Q：应该怎么修？

A：推荐在自动 Pro 发放的国家判断阶段修复，不复制历史设备画像。

原因：

1. 登录响应需要立即返回正确 `is_pro`。
2. `/device/register/` 是登录后的启动引导请求，不能作为登录授权结果的前置依赖。
3. 最小改动是把同一 `bundle_id + device_id` 下 `last_seen` 最新的历史用户设备行作为国家判断兜底，不改写 B1/C1 的设备画像。

建议调整 `TrialService.try_grant_auto_trial_for_login_device(...)`：

1. 先查询当前登录用户自己的非失效设备行。
2. 如果当前用户设备行 `country_code == "CN"`，直接允许自动发放。
3. 如果当前用户设备行不存在或 `country_code` 为空，则查询同一 `bundle_id + device_id` 下历史用户设备行：
   - `user__isnull=False`
   - 按 `last_seen` 倒序，其次按 `id` 倒序
   - 取最新一条记录的 `country_code` 作为本次登录国家判断依据
4. 如果最新历史设备行 `country_code == "CN"`，允许自动发放。
5. 如果历史设备行也不存在，或 `country_code` 为空/非 `CN`，跳过自动发放。
6. 不把历史设备行的 `country_code` 复制到当前用户设备行，避免额外写入和归属混淆。

伪代码：

```python
current = TrustedDevice.objects.filter(
    user=user,
    bundle_id=bundle_id,
    device_id=device_id,
    is_revoked=False,
).first()

country_code = current.country_code if current else ""

if not country_code:
    latest = (
        TrustedDevice.objects
        .filter(bundle_id=bundle_id, device_id=device_id, user__isnull=False)
        .order_by("-last_seen", "-id")
        .first()
    )
    country_code = latest.country_code if latest else ""

if country_code == "CN":
    TrialService.grant_auto_trial_if_eligible(user=user)
```

### Q：是否应该改 `TrialService.try_grant_auto_trial_for_login_device(...)`？

A：需要改。该函数应负责完整国家判断，不要求 `DeviceService` 复制设备画像。

当前用户设备行查询应定位到当前登录用户自己的设备行：

```python
TrustedDevice.objects.filter(
    user=user,
    bundle_id=bundle_id,
    device_id=device_id,
    is_revoked=False,
).first()
```

如果当前用户设备行没有国家，再按同一 `bundle_id + device_id` 查 `last_seen` 最新历史用户设备行做兜底。注意兜底只用于国家判断，不用于选择发放对象；发放对象始终是当前登录用户 `user`。

### 5. 涉及文件

| 文件 | 改动内容 |
| --- | --- |
| `SparkService/ai_config/services.py` | `try_grant_auto_trial_for_login_device(...)` 先查当前用户设备行；国家为空时按同一 `bundle_id + device_id` 的历史用户设备行 `last_seen` 最新记录兜底判断国家 |
| `SparkService/accounts/services/login_service.py` | 保持时序：设备关联后自动发放 Pro，再计算 `is_pro` |
| `SparkService/accounts/services/otp_service.py` | 邮箱 OTP、手机号 OTP 路径保持同样时序 |
| `SparkService/accounts/tests_auto_trial_on_registration.py` 或新增测试文件 | 增加同设备 A1 退出后 B1/C1 首次登录自动发放测试 |
| `SparkService/accounts/tests_login_is_pro_after_auto_grant.py` | 补充同安装多用户场景，验证登录响应 `is_pro=true` |

### 6. 验收标准

1. 设备 `0001` 首次下载，匿名登记 `country_code=CN`。
2. A1 首次注册/登录后，A1 自动获得 15 天 Pro，登录响应 `is_pro=true`。
3. A1 退出后，A1 的 `TrustedDevice(user=A1, device_id=0001).is_revoked=true`。
4. B1 在同一设备 `0001` 首次注册/登录，没有历史 Pro 发放记录时，自动获得 15 天 Pro，登录响应 `is_pro=true`。
5. B1 的 `TrustedDevice(user=B1, device_id=0001)` 不要求复制 `country_code`；自动发放判断可使用同安装 `last_seen` 最新历史用户设备行的 `country_code=CN`。
6. B1 退出后，C1 在同一设备 `0001` 首次注册/登录，同样自动获得 15 天 Pro，登录响应 `is_pro=true`。
7. 如果同一设备历史国家不是 `CN`，B1/C1 登录仍不自动发放。
8. 如果当前用户已经存在 `TrialApplication(status=active)`，重复登录不重复生成新的自动发放周期。
9. 如果当前用户已有过期、拒绝或已开始过的试用记录，仍遵守现有“一次性自动发放”规则，不静默重新发放。
10. 自动发放流水 `TrialApplicationRequest(source=auto)` 按用户维度记录，A1/B1/C1 各自有自己的流水。
11. 登录后再执行 `/device/register/` 只更新设备画像，不作为自动发放成功的必要条件。
12. Apple/密码/邮箱 OTP/手机号 OTP 登录路径表现一致。

## 工单 `AI-CONFIG-000006`：场景下支持同一基座模型配置多个智能体

### 1. 背景

### Q：当前有什么问题？

A：当前服务端场景绑定模型 `AIScenarioModelBinding` 以 `scenario + model + identity` 做唯一约束：

```python
models.UniqueConstraint(
    fields=["scenario", "model", "identity"],
    name="uniq_scenario_model_identity_binding",
)
```

服务端位置：

```text
SparkService/ai_config/models.py:103-143
```

因此在同一个场景下，后台管理系统无法为同一款模型创建多个 `identity=agent` 的智能体。后台请求：

```text
POST /api/admin/v1/ai/scenarios/chat/models/
body.model = doubao-seed-2-0-pro-260215
body.identity = agent
```

如果该场景下已经存在同模型同 `agent` 绑定，会返回：

```json
{
  "code": -1,
  "msg": {
    "model": ["model_already_bound_to_this_scenario_with_same_identity"]
  }
}
```

但客户端本地能力已经支持“同一基座模型下多个智能体”。客户端 `AIScenarioRemoteModelRow` 有：

```swift
var baseModelName: String?
var localFilename: String?
```

客户端位置：

```text
SparkClient/SparkClient/Projects/Core/AI/AIConfigModels.swift:238-239
```

本地创建智能体时，智能体有自己的唯一 `name`，同时用 `baseModelName` 指向真实调用的底层模型。运行时调用厂商模型时会用 `baseModelName` 替换智能体名，因此多个智能体可以共享同一基座模型。

### 2. 目标

### Q：服务端要支持什么能力？

A：服务端需要支持：

1. 同一个场景下，可以添加多个 `identity=agent` 的智能体。
2. 多个智能体可以指向同一个基座模型 `AIModelCatalog`。
3. 每个智能体在 bootstrap 返回时必须有自己的唯一实例名，但不新增数据库字段，直接由绑定行派生：

```text
agent-ai_config_aiscenariomodelbinding_id-model_id-model_name
```

4. bootstrap 返回给客户端时：
   - `name` 使用派生智能体实例名。
   - `baseModelName` 使用基座模型名，例如 `deepseek-v4-pro`。
   - `identity` 为 `agent`。
5. 普通模型 `identity=model` 的行为保持稳定，仍可继续以模型目录 `model.name` 作为 `name`。
6. 后台管理系统支持在同一场景下重复选择同一模型并添加多个智能体。

示例 bootstrap 返回：

```json
{
  "name": "agent-18-7-deepseek-v4-pro",
  "identity": "agent",
  "baseModelName": "deepseek-v4-pro",
  "display_name": "报告解读智能体",
  "systemProvision": "...",
  "briefDescription": "..."
}
```

### 3. 设计原则

### Q：为什么不能只是删除唯一约束？

A：不能只删除 `scenario + model + identity` 唯一约束，否则会出现多个绑定行在客户端 bootstrap 中都返回同一个 `name=model.name`。客户端 `AIScenarioRemoteModelRow.id` 等于 `name`，如果多行同名，会导致：

1. 客户端模型列表无法稳定区分多个智能体。
2. 会话内选择某个智能体后，重启/刷新可能匹配到另一条配置。
3. `is_default`、排序、偏好存储、Core Data upsert 都可能被同名覆盖。
4. 运行时无法知道当前 agent 应该使用哪套 systemProvision / toolScenarios。

因此必须同时满足：

1. 数据库存储层：一个 agent 绑定行用自身 `id` 作为实例唯一性的来源。
2. API 返回层：agent 的 `name` 返回实例标识，而不是基座模型名。
3. API 返回层：agent 的 `baseModelName` 返回基座模型名，供客户端实际调用底层模型。

### 4. 数据模型设计

### Q：`AIScenarioModelBinding` 是否需要增加字段？

A：不需要新增 `agent_name` 字段。

智能体唯一名在 bootstrap 组装时由现有字段派生：

```text
agent-{binding.id}-{model.id}-{model.name}
```

按用户要求，说明中的完整语义为：

```text
agent-ai_config_aiscenariomodelbinding_id-model_id-model_name
```

示例：

```text
agent-18-7-deepseek-v4-pro
```

其中：

1. `18` 是 `AIScenarioModelBinding.id`。
2. `7` 是 `AIModelCatalog.id`。
3. `deepseek-v4-pro` 是 `AIModelCatalog.name`。

字段语义：

| 字段 | identity=model | identity=agent |
| --- | --- | --- |
| `model` | 真实模型目录行 | 基座模型目录行 |
| API `name` | `model.name` | `agent-{binding.id}-{model.id}-{model.name}` |
| API `baseModelName` | 空或不返回 | `model.name` |
| `display_name` | `model.display_name` | 可沿用 `model.display_name`，或后续增加独立 agent 展示名 |

### Q：唯一约束如何调整？

A：建议从“模型绑定唯一”改成“返回模型名唯一”。

当前约束：

```python
UniqueConstraint(fields=["scenario", "model", "identity"])
```

需要改为：

1. 删除 `uniq_scenario_model_identity_binding`。
2. 不新增替代数据库唯一字段。
3. `identity=model` 仍建议在 serializer 层保留 `scenario + model + identity=model` 唯一校验，避免普通模型重复。
4. `identity=agent` 不再限制 `scenario + model` 唯一；多个 agent 的 bootstrap `name` 由绑定行 `id` 天然区分。

说明：

1. `AIScenarioModelBinding.id` 是数据库主键，已具备全局唯一性。
2. agent 派生名包含 `binding.id`，因此同场景同模型多个 agent 不会同名。
3. 不新增字段可避免 migration、后台表单字段、手动唯一校验和历史数据回填。

### 5. 后台管理设计

### Q：后台创建智能体时如何传参？

A：后台 `/api/admin/v1/ai/scenarios/{scenario}/models/` 不需要传 `agent_name`。

推荐最小方案：

1. 前端创建 `identity=agent` 时，仍选择基座模型 `model`。
2. 后端 serializer 对 `identity=agent` 放开 `scenario + model + identity` 唯一校验。
3. 后台创建多个同基座模型 agent 时，不再报 `model_already_bound_to_this_scenario_with_same_identity`。
4. 后台列表可用派生规则展示“智能体实例名”，但该值不是数据库字段。

后续增强方案：

1. 增加 `agent_display_name`，用于后台和客户端展示“医生智能体 / 报告解读智能体 / 用药顾问”等名称。
2. 当前阶段可先用 `brief_description` 或 `model.display_name` 展示，避免一次性扩太多字段。

### Q：后台列表需要展示什么？

A：`AIScenarioModelsView.vue` 当前只展示 `模型 / 类型 / 默认 / 厂商 / 温度 / 最大 Token / 排序 / 激活`。支持多 agent 后建议补充：

1. 智能体名：按 `agent-{id}-{model_id}-{model}` 规则派生展示，仅 agent 展示。
2. 基座模型：`model`，agent 场景显示“基座模型”语义。
3. 类型：继续展示“模型/智能体”。
4. 默认：仍然整个场景只能有一个默认项，不区分 model/agent。

### 6. Bootstrap 返回设计

### Q：`/api/v1/ai/config/bootstrap` 如何返回？

A：当前服务端在 `_build_pro_scenarios(...)` 中构造每行：

```python
model_data = {
    "name": model.name,
    "display_name": model.display_name,
    "identity": row.identity,
    ...
}
```

服务端位置：

```text
SparkService/ai_config/views.py:190-217
```

需要调整为：

```python
is_agent = row.identity == IdentityKind.AGENT
row_name = f"agent-{row.id}-{model.id}-{model.name}" if is_agent else model.name

model_data = {
    "name": row_name,
    "display_name": model.display_name,
    "identity": row.identity,
    "baseModelName": model.name if is_agent else None,
    ...
}
```

注意：

1. agent 的 `name` 必须按 `agent-{binding.id}-{model.id}-{model.name}` 组装，不能再是基座模型名。
2. agent 的 `baseModelName` 必须是基座模型名。
3. 普通 model 可以不返回 `baseModelName`，或返回 `null`。
4. `default_model` 如果默认项是 agent，应使用 agent 的 `name`，否则客户端默认模型无法选中对应 agent。
5. `models[]` 中同一基座模型的多个 agent 必须都保留，不能按 `name/model` 去重。

### 7. 客户端兼容性

### Q：客户端是否需要大改？

A：客户端本地模型已经具备兼容基础：

1. `AIScenarioRemoteModelRow.name` 作为行唯一 ID。
2. `baseModelName` 已存在。
3. 运行时对 `identity=agent` 且存在 `baseModelName` 的行，会用 `baseModelName` 调用底层模型。

因此服务端只要按契约返回：

```json
{
  "name": "agent-18-7-deepseek-v4-pro",
  "identity": "agent",
  "baseModelName": "deepseek-v4-pro"
}
```

客户端就能区分多个同基座 agent。

需要注意：

1. 后端 JSON 字段应使用 `baseModelName`，因为客户端 `AIScenarioRemoteModelRow` 当前按该 key 解码。
2. 不要返回 `base_model_name`，除非客户端也增加兼容解码。
3. 不新增 `agent_name` 字段；后台如需展示智能体实例名，应按同一派生规则计算。

### 8. 涉及文件

| 端 | 文件 | 改动内容 |
| --- | --- | --- |
| 服务端 | `SparkService/ai_config/models.py` | 删除/调整 `scenario + model + identity` 数据库唯一约束；不新增 `agent_name` 字段 |
| 服务端 | `SparkService/ai_config/migrations/*` | 仅调整唯一约束；新项目可同步 initial migration |
| 服务端 | `SparkService/backoffice/serializers.py` | `AdminAIScenarioModelBindingSerializer` 对 `identity=agent` 放开同场景同模型校验；普通 model 仍保持唯一 |
| 服务端 | `SparkService/backoffice/views.py` | 创建/更新场景绑定时沿用 serializer；审计日志继续记录绑定行 id/model/identity |
| 服务端 | `SparkService/ai_config/views.py` | bootstrap 中 agent 返回 `name=agent-{binding.id}-{model.id}-{model.name}`、`baseModelName=model.name`；默认项使用返回名 |
| 服务端 | `SparkService/ai_config/tests.py` | 增加 bootstrap 多 agent 返回测试 |
| 服务端 | `SparkService/backoffice/tests.py` | 增加同场景同模型创建多个 agent 的后台 API 测试 |
| 管理端前端 | `SparkService/backoffice-web/src/api/modules/ai.ts` | 不新增 `agent_name` 字段；如接口返回 `model_id` 可补充用于展示派生名 |
| 管理端前端 | `SparkService/backoffice-web/src/views/AIScenarioModelsView.vue` | agent 行可按 `id/model_id/model` 展示派生智能体名；创建 agent 时允许同模型重复提交 |

### 9. 验收标准

1. 后台在 `chat` 场景下可连续创建多个 `identity=agent + model=doubao-seed-2-0-pro-260215` 的绑定。
2. 创建第二个同基座 agent 不再返回 `model_already_bound_to_this_scenario_with_same_identity`。
3. 不新增 `agent_name` 数据库字段。
4. 每个 agent 的 bootstrap `name` 都按 `agent-{binding.id}-{model.id}-{model.name}` 派生，且互不相同。
5. 普通 `identity=model` 仍不允许同场景重复绑定同一个模型，除非后续明确要支持普通模型重复。
6. bootstrap 返回 agent 时，`name` 为派生智能体名。
7. bootstrap 返回 agent 时，`baseModelName` 为基座模型 `model.name`。
8. 同一场景同一基座模型的多个 agent 在 `models[]` 中都存在，不被覆盖或去重。
9. 如果默认项是 agent，`default_model` 等于该 agent 的 `name`，客户端能默认选中该智能体。
10. 客户端收到多个同基座 agent 后，模型选择列表可区分多行，运行时实际请求使用 `baseModelName`。
11. agent 的 `systemProvision`、`briefDescription`、`aiToolScenarios`、`relatedTaskCodes` 按绑定行分别生效。
12. 删除某个 agent 不影响同场景同基座模型的其他 agent。
13. 修改某个 agent 的 prompt/工具/排序，只影响该 agent 绑定行。

## 工单 `AI-CONFIG-000007`：场景模型绑定增加显示名称

### 1. 背景

### Q：为什么 `AI-CONFIG-000006` 之后还需要显示名称字段？

A：`AI-CONFIG-000006` 解决的是“同场景同基座模型可以创建多个智能体，并且每个 agent 在客户端有唯一技术标识”的问题。当前 agent 的 bootstrap `name` 使用：

```text
agent-{binding.id}-{model.id}-{model.name}
```

这个值适合作为客户端行 ID、偏好存储 ID 和运行时选择 ID，但不适合直接给用户看。后台和客户端仍需要一个稳定、可运营配置的展示名，例如：

1. 报告解读助手
2. 用药建议助手
3. 慢病随访助手
4. 儿科问诊助手

因此需要在 `AIScenarioModelBinding` 绑定行上增加“显示名称”，让同一个基座模型在同一个场景下可以被配置成多个业务语义不同的智能体。

### 2. 需求目标

### Q：显示名称属于模型目录还是场景绑定？

A：属于 `AIScenarioModelBinding`，不属于 `AIModelCatalog`。

原因：

1. `AIModelCatalog.display_name` 表示模型目录名，例如“Doubao Seed 2.0 Pro”，是底层模型展示名。
2. `AIScenarioModelBinding.display_name` 表示场景绑定名，例如“报告解读助手”，是业务使用名。
3. 同一个 `AIModelCatalog` 可以在同一个场景下绑定多个 agent，每个 agent 需要不同展示名。
4. 普通 `identity=model` 也可以使用绑定显示名，方便在不同场景下展示不同文案。

### 3. 数据模型设计

### Q：服务端需要增加什么字段？

A：在 `AIScenarioModelBinding` 增加必填显示名称字段：

```python
class AIScenarioModelBinding(TimeStampedModel):
    display_name = models.CharField(
        max_length=128,
        verbose_name="显示名称",
        help_text="场景内展示名称；agent 可配置为报告解读助手、用药建议助手等业务名称",
    )
```

字段规则：

1. 必填，不允许空字符串。
2. 建议 `max_length=128`，避免后台配置过长影响客户端列表。
3. 不作为唯一约束字段；允许不同 agent 使用相同展示名，但后台可提示运营人员避免重复。
4. 迁移已有数据时，可用 `AIModelCatalog.display_name` 回填，避免历史绑定行为空。

### 4. Bootstrap 返回设计

### Q：bootstrap 中 `name`、`baseModelName`、`display_name` 分别是什么？

A：三者职责必须拆开：

| 字段 | 作用 | identity=model | identity=agent |
| --- | --- | --- | --- |
| `name` | 客户端唯一 ID / 选择 ID | `model.name` | `agent-{binding.id}-{model.id}-{model.name}` |
| `baseModelName` | agent 调用的真实底层模型名 | `null` | `model.name` |
| `display_name` | 客户端和后台展示名 | `binding.display_name` | `binding.display_name` |

服务端 bootstrap 组装时不能再使用 `model.display_name` 作为返回展示名，应统一使用 `AIScenarioModelBinding.display_name`：

```python
model_data = {
    "name": row.bootstrap_name(),
    "display_name": row.display_name,
    "identity": row.identity,
    "baseModelName": model.name if is_agent else None,
    ...
}
```

### 5. 后台管理设计

### Q：后台创建/编辑场景绑定需要如何调整？

A：`AIScenarioModelsView.vue` 的创建/编辑弹窗需要增加“显示名称”字段，并设为必填。

页面位置：

```text
SparkService/backoffice-web/src/views/AIScenarioModelsView.vue:45-130
```

交互规则：

1. 新建绑定时必须填写显示名称。
2. 编辑绑定时可修改显示名称。
3. 列表建议展示“显示名称 / 类型 / 基座模型 / 智能体名 / 默认 / 排序 / 激活”等信息。
4. 当选择基座模型后，前端可以把输入框 placeholder 设为模型目录展示名，但不能静默替用户提交空值。
5. agent 行的“智能体名”仍展示派生唯一名；“显示名称”展示运营配置名。

### 6. API 与序列化设计

### Q：后台 API 需要如何调整？

A：`AdminAIScenarioModelBindingSerializer` 需要纳入 `display_name`：

1. `fields` 增加 `display_name`。
2. create/update 校验 `display_name` 非空。
3. 返回列表时带出 `display_name`，供后台表格展示。
4. 不要用 `display_name` 参与 agent 唯一性判断。
5. 普通 `identity=model` 的重复校验仍按 `scenario + model + identity=model` 保持。

### 7. 涉及文件

| 端 | 文件 | 改动内容 |
| --- | --- | --- |
| 服务端 | `SparkService/ai_config/models.py` | `AIScenarioModelBinding` 增加 `display_name` 必填字段 |
| 服务端 | `SparkService/ai_config/migrations/*` | 增加字段并回填已有绑定行显示名称 |
| 服务端 | `SparkService/ai_config/views.py` | bootstrap 返回 `display_name=row.display_name` |
| 服务端 | `SparkService/backoffice/serializers.py` | 后台场景绑定 serializer 增加 `display_name` 字段与非空校验 |
| 服务端 | `SparkService/backoffice/views.py` | 创建/编辑场景绑定沿用 serializer；审计日志建议记录显示名称 |
| 服务端 | `SparkService/ai_config/tests.py` | 增加 bootstrap 使用绑定显示名称的测试 |
| 服务端 | `SparkService/backoffice/tests.py` | 增加后台创建/编辑绑定显示名称必填测试 |
| 管理端前端 | `SparkService/backoffice-web/src/api/modules/ai.ts` | `AIScenarioModelBinding` 类型增加 `display_name` |
| 管理端前端 | `SparkService/backoffice-web/src/views/AIScenarioModelsView.vue` | 表格与弹窗增加显示名称；提交时必填 |

### 8. 验收标准

1. 后台创建场景模型绑定时，“显示名称”为空不能提交。
2. 后台编辑场景模型绑定时，可以修改显示名称。
3. 后台列表能看到绑定显示名称。
4. 同场景同基座模型创建多个 agent 时，可以分别配置不同显示名称。
5. bootstrap 返回的 `display_name` 使用 `AIScenarioModelBinding.display_name`，不再使用 `AIModelCatalog.display_name`。
6. agent 的 `name` 仍保持 `agent-{binding.id}-{model.id}-{model.name}`，不能被显示名称替代。
7. agent 的 `baseModelName` 仍返回基座模型 `model.name`。
8. 普通 model 绑定也返回绑定行显示名称。
9. 已有绑定行迁移后显示名称不为空。
10. 客户端无需新增解码字段；继续使用现有 `display_name` 展示即可。

## 全局注意事项

1. 申请接口返回“提交成功”后，客户端不能立即解锁 Pro 模型。
2. Pro 模型可用性以服务端 bootstrap / trial status 刷新后的结果为准。
3. 通知权限请求必须由客户端用户行为触发，避免在启动时无上下文弹权限。
4. APNs 通知只负责提醒和触发刷新，不能把 API key 或敏感模型配置放进 payload。
5. 申请次数和审核结果需要可审计，避免只靠当前状态覆盖历史。
6. 客户端已经使用统一编解码体系，新增接口或字段时不要在业务层手动对齐字段；普通 snake_case/camelCase 与 ISO8601 日期统一依赖 `JSONEncoder.default` / `JSONDecoder.default`，不要手写 `CodableKey`。只有历史兼容或非标准结构才允许在 Remote DTO 内自定义 `init(from:)`。
7. 登录自动 Pro 发放需要增加国家限制：仅 `TrustedDevice.country_code == "CN"` 时允许触发；主动申请试用仍按申请次数进入异步审核。
