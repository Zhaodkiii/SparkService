# 工单：iOS「设置 → 记忆」同步循环、隐私日志与产品语义偏差

## 工单信息

| 项目 | 内容 |
| --- | --- |
| 状态 | 待修复 |
| 优先级 | P0：隐私日志、同步循环；P1：请求收敛、状态反馈与页面语义 |
| 创建日期 | 2026-08-27 |
| 本次范围 | 仅分析与设计，不修改 iOS、服务端或 Web 代码 |
| 涉及端 | iOS、`chat_sync/ai_memory`、后续 Web 记忆看板 |

## 结论

本次日志中 `Memory.Settings.Get` 返回 HTTP 200，且设置字段与 `revision` 完整，**不是服务端设置接口失败**。

已确认两个必须优先处理的问题：

1. iOS 网络日志会输出完整请求/响应正文。日志中已经出现健康资料、病史/症状、用药信息及文件地址等敏感内容，属于 P0 隐私风险。
2. 服务端设置快照写回本地时，被误判为“本地数据变更”，触发下一轮 `localMutation` 同步，形成持续同步反馈环。日志中连续出现设置拉取、两次 Pull 和 `记忆同步结束`，均无实际新增条目。

此外，现有 iOS「记忆档案」仍是可直接新增、编辑、删除任意记忆条目的旧页面模型，与已确认的 DeepTutor 对齐规则不一致：用户只能直接维护明确偏好（`L3/preferences`）；L1、L2 以及 `recent/profile/scope` 应由证据与工作台生成、审计和维护。

## 复现范围与日志证据

### 用户操作路径

```text
App 启动 / 进入「设置」
  → 点击「记忆档案」
  → MemoryArchiveSettingsView.task 调用 load()
  → 本地读取 + 刷新列表 + Settings.Get + manualRefresh()
  → 同步引擎 Settings.Get → Pull → Push（无待发时仍执行）→ 收敛 Pull
```

### 已观察到的现象

两份提供的日志均显示：

- `Memory.Settings.Get` 成功返回 200，返回 `is_enabled`、工具权限、召回数量、敏感来源开关及 `revision=1`。
- 每轮 `localMutation` 同步都出现设置拉取，并出现两次 `Memory.Sync.Pull`；Pull 结果为空、Push 接收数为 0。
- 第二份日志中共有 10 次 `记忆同步结束`，均为 `trigger=localMutation`，伴随 30 条设置拉取日志与 58 条 Pull 日志记录（同一请求会经多个日志点记录）。
- 网络日志输出了完整 UTF-8 响应正文，其中含医疗业务敏感内容。

### 同步循环根因

```text
同步引擎获取服务端 settings
  → applySettingsSnapshot()
  → CoreDataMemoryEntityRepository.saveSettings()
  → 发布 sparkMemoryDatabaseDidChange
  → MemorySyncSupervisor 将任何变更都当作本地 mutation
  → 500ms 后执行 performSync(trigger: .localMutation)
  → 再次获取服务端 settings
  └───────────────────────────────────────────────┘
```

问题不在于单飞锁失效。单飞锁只能避免同一时刻并发执行，不能阻止同步结束后由远端快照再次排队触发新的同步。

## 问题清单、修复方向与原因

| 优先级 | 问题 | 为什么需要处理 | 修复方向 | 涉及内容 |
| --- | --- | --- | --- | --- |
| P0 | 完整网络正文进入日志 | 医疗数据、文件地址及记忆内容可能被控制台、持久化日志、诊断包或第三方采集系统获取；这违反最小暴露原则。 | 默认只记录方法、路径、状态码、耗时、请求 ID、响应大小和业务错误码。禁止记录正文；如确有排障需要，必须是显式、短时、开发环境受控开关，并在输出前按字段白名单、脱敏和长度上限处理。 | `SparkNetworkTransport`、`NetworkLogSanitizer`、日志配置、诊断包策略、历史日志处置。 |
| P0 | 远端 settings 快照触发本地 mutation 同步 | 会持续消耗网络、电量与服务端资源，造成日志噪声；未来有真实待同步数据时还会放大并发和冲突风险。 | 为数据变更增加来源：`localUserMutation`、`remoteSnapshot`、`syncMetadata`。同步监督器仅订阅真实本地业务 mutation，远端落库和同步游标更新不得重新入队。更理想的长期方案是由 Outbox 新增记录触发推送，而非监听全局数据库变更通知。 | `CoreDataMemoryEntityRepository`、`MemorySyncSupervisor`、通知/事件定义、Outbox。 |
| P1 | 首次进入页面存在重复设置读取；每次同步在无待发数据时仍进行两次 Pull | 当前 `load()` 先直接拉设置，再调用 `manualRefresh()`；同步引擎又拉一次设置。无待发 Outbox 时，第二次“收敛 Pull”没有收益。 | 建立单一页面加载编排：一次 `refreshFromServer` 返回 settings 与必要数据。仅在 Pull 后确实推送过 mutation 时再执行收敛 Pull；无待发数据时跳过 Push 与第二次 Pull。 | `MemoryArchiveSettingsViewModel.load`、`MemorySyncEngine.syncNowWithPull`、接口调用指标。 |
| P1 | 开关保存使用无结构 `Task`，没有保存中/失败/冲突可见状态 | 连续切换时，多个 PATCH 可能乱序返回；旧 `revision` 会导致冲突，用户无法知道哪次设置真正生效。 | 使用串行 `settingsSaveTask` 与 300–500ms 合并保存；每次携带最新 revision；页面显示 `saving/synced/failed/conflict`。冲突时以服务端快照为准，并提示“本次本地修改未保存，可重新调整”。 | `MemoryArchiveSettingsViewModel.savePreferences`、设置 DTO、错误模型、SwiftUI 状态。 |
| P1 | `refreshSettingsFromServer()` 静默吞掉异常 | 离线时可保留本地缓存，但用户和日志无法区分“使用缓存”“同步失败”“数据已过期”。 | 保留不阻断流程的原则，但返回结构化结果并更新同步状态、最近错误、最近成功时间；输出不含敏感正文的诊断日志。 | ViewModel、同步状态卡片、客户端日志、可观测性。 |
| P1 | iOS 页面允许直接“灌输新记忆”和任意编辑/清空 | 不符合已确认业务规则：普通对话与用户手动入口只可维护明确偏好；长期画像、知识范围、近期总结必须可追溯到证据，不能由任意文本绕过工作台。 | 将页面迁移为新信息架构：偏好可新增/编辑/删除；L1 仅浏览证据；L2/L3 的 `recent/profile/scope` 只读并展示来源、状态和工作台入口。删除需要软删除/墓碑、确认和撤销；批量操作使用单个批量命令，不能逐条触发同步。 | `MemoryArchiveSettingsView`、iOS 记忆模型、记忆 API、Web 看板对齐、工作台能力。 |
| P2 | 设置并发协议存在文档与实现漂移风险 | 当前服务端从 PATCH body 读取 `revision`；部分设计稿描述 `If-Match`。两个并发控制入口并存会导致客户端实现不一致。 | 明确唯一协议：推荐保留 body `revision` 或统一到 `If-Match` 其一，并在所有客户端、API 文档、错误码和测试中一致。服务端仍是冲突裁决与最终事实源。 | `MemorySettingsView`、serializer、iOS DTO、API 文档、契约测试。 |

## 推荐修复架构

### 1. 将“数据写入”与“需要上传”分离

不再以“数据库任意变化”作为上传条件。建议事件模型如下：

```text
用户创建/编辑/删除偏好或记忆实体
  → 本地事务写入业务表 + Outbox
  → 发出 localUserMutation
  → SyncSupervisor 合并调度 Push/Pull

服务端 Pull / Settings.Get 返回快照
  → 本地事务应用快照、游标和同步元数据
  → 发出 remoteSnapshot（供 UI 刷新）
  → 不产生 Outbox，不触发同步
```

要求：

- 同一事务内写业务数据和 Outbox，避免“本地已改但未入队”。
- 远端应用必须不创建新的 mutation receipt / Outbox。
- UI 刷新可以观察所有变更；同步监督器只能观察本地 mutation 或 Outbox 状态。
- 为同步原因记录 `trigger` 与 `origin`，便于指标和回归测试。

### 2. 收敛设置页加载与同步请求

建议定义一个面向页面的协调入口，而非由 ViewModel 分别发请求：

```text
进入记忆页
  → 读取本地快照，立即渲染
  → 后台执行一次 refresh
      → Settings.Get
      → Pull（应用远端变化）
      → 若存在待发 Outbox：Push，再 Pull 收敛
  → 返回统一 SyncResult，更新 UI 状态
```

无待发数据时，单次进入页面的目标上限为：一次 Settings.Get、一次 Pull；不应在用户无操作后持续产生网络请求。

### 3. 设置保存状态机

```text
synced → editing → saving → synced
                    ├→ failed（保留本地界面值，允许重试）
                    └→ conflict（采用服务端快照，提示用户重新调整）
```

- 多次开关操作进入同一个串行保存器，只提交最后一个完整快照。
- PATCH 成功后，以服务端返回的 settings/revision 覆盖本地缓存，但标记为 `remoteSnapshot`，不得入同步队列。
- 失败不会影响聊天、设置页或其他业务流程；列表卡片展示“未同步/失败/已同步”及可重试入口。
- 服务端优先规则已确认：发生版本冲突时以服务端存储为准。

### 4. 记忆页面与 DeepTutor 对齐边界

| 区域 | 用户权限 | 数据来源 | 页面能力 |
| --- | --- | --- | --- |
| L1 证据 | 不直接编辑 | chat、knowledge、medical、nutrition、preference 等真实业务事件 | 查看摘要、来源、失效状态并跳转原业务。 |
| L2 领域总结 | 不直接编辑 | 工作台 `update/audit/dedup/merge` | 查看、查看引用、发起或查看任务。 |
| L3/preferences | 可编辑 | 用户明确表达或手动维护 | 新增、编辑、删除、去重、撤销。 |
| L3/recent、profile、scope | 不直接编辑 | 基于 L1/L2 的工作台整理 | 查看、查看证据、请求审计/纠错。 |

这保证 iOS、Web 和后续其他客户端均遵守同一规则：AI 的 `write_memory` 也只写明确偏好，不能绕过工作台写入画像或知识范围。

## 关键代码定位

### iOS

- 设置入口：`Projects/Features/AISettings/Presentation/Root/AISettingsView.swift`。
- 页面与开关交互：`Projects/Features/AISettings/Presentation/Personalization/MemoryArchiveSettingsView.swift`。
- 页面加载、保存和静默失败处理：`Projects/Features/Memory/Presentation/MemoryArchiveSettingsViewModel.swift`。
- 同步触发监听：`Projects/Features/Memory/Infrastructure/MemorySyncSupervisor.swift`。
- 同步固定流程（settings、Pull、Push、收敛 Pull）：`Projects/Features/Memory/Infrastructure/MemorySyncEngine.swift`。
- 远端快照复用本地保存并发送数据库变更通知的根因：`Projects/Features/Memory/Infrastructure/CoreDataMemoryEntityRepository.swift` 中 `applySettingsSnapshot → saveSettings`。
- 设置 GET/PATCH：`Projects/Features/Memory/Infrastructure/SparkMemoryRemoteAPI.swift`。
- 完整正文日志输出：`Projects/Core/Networking/SparkNetworkTransport.swift` 与 `NetworkLogSanitizer`。

### 服务端

- 设置 API：`chat_sync/ai_memory/api/views.py` 的 `MemorySettingsView`。
- 设置并发/版本规则：`chat_sync/ai_memory/services/memory_settings_service.py`。
- 路由：`chat_sync/ai_memory/urls.py`。

## 实施顺序

1. **P0-A：阻断敏感正文日志。** 默认关闭 request/response body；补充敏感字段、文件 URL 和大正文回归测试；评估并清理可控范围内已有本地诊断日志。
2. **P0-B：修复同步反馈环。** 引入事件来源或 Outbox 驱动；确保远端 settings 快照、Pull 应用和同步元数据不触发 `localMutation`。
3. **P1-A：收敛请求与同步状态。** 合并页面加载流程；无 Outbox 时跳过 Push 和第二次 Pull；展示非阻塞同步状态。
4. **P1-B：改造设置保存并发控制。** 串行/合并 PATCH、版本冲突展示、重试与服务端优先处理。
5. **P1-C：将旧档案页迁移到三层记忆信息架构。** 先落地偏好与只读概览，再接入工作台与证据追溯。
6. **P2：统一设置 revision 契约。** 完成 API、各客户端和契约测试同步。

## 验收标准

### 同步循环

- 在无用户改动、无待发 Outbox 的情况下，进入记忆页后不再出现持续的 `trigger=localMutation`。
- 对一次远端 settings 快照应用进行集成测试：本地缓存更新、UI 可刷新、Outbox 数量不增加、不会调用同步调度器。
- 无待发数据的单次页面刷新最多执行一次 Settings.Get 和一次 Pull；2 秒观察窗口内无额外记忆同步请求。
- 一次本地偏好修改只创建一条可幂等的 Outbox mutation；服务端确认后不会因回包再次创建 mutation。

### 设置保存与状态

- 快速连续切换多个开关时，最终仅提交最后一个完整设置快照，页面最终值与服务端 revision 一致。
- 离线、超时和冲突不阻断页面或聊天；卡片能明确显示缓存、同步中、失败、已同步状态，并支持重试。
- 409/版本冲突时以服务端快照展示，并保留可理解的用户提示与诊断日志。

### 隐私日志

- 在 release 与常规 debug 配置中，任何网络日志均不包含医疗正文、记忆正文、认证信息、文件 URL/对象键或完整 JSON body。
- 日志测试使用含敏感字段的模拟响应，断言只输出允许的元数据和已脱敏标识。
- 诊断导出与第三方日志采集策略经过复核；明确历史本地日志的保留、轮转和清理策略。

### 产品规则

- iOS 端用户只能直接创建和编辑 `L3/preferences` 明确偏好。
- L1/L2/L3 其他内容展示来源、层级和状态，不能通过通用文本入口绕过证据和工作台。
- 删除与批量操作具备确认、软删除/墓碑、同步幂等和撤销策略。

## 待产品与安全确认项

| 问题 | 建议 |
| --- | --- |
| 是否保留“清空全部偏好”？ | 可保留，但限定为 `L3/preferences`，二次确认并提供短期撤销；服务端使用批量墓碑语义。 |
| 是否允许用户手动创建非偏好记忆？ | 不允许。用户可提交“纠错/补充证据”请求，由工作台审计后更新 L2/L3。 |
| 诊断日志是否允许在内部测试环境查看正文？ | 原则上也不应查看健康与记忆正文；如存在法律/排障必要性，必须经安全审批、显式用户授权、字段白名单、短时失效和审计。 |
| `revision` 放在 body 还是 `If-Match`？ | 选择一种并形成跨端契约；当前服务端实现使用 body `revision`，短期保持兼容，后续统一迁移。 |

## 本工单不包含

- 不在本工单中直接实现 iOS、服务端或 Web 改动。
- 不改变既有“异步失败不影响其他业务流程、服务端为冲突最终事实源”的产品原则。
- 不将健康原始业务数据复制进入记忆日志或通用客户端调试日志。
