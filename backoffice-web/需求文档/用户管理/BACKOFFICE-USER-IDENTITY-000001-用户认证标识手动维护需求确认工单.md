# BACKOFFICE-USER-IDENTITY-000001 用户认证标识手动维护需求确认工单

> 工单状态：需求确认中  
> 创建日期：2026-09-04  
> 适用系统：SparkService、backoffice-web  
> 当前阶段：只维护需求和设计方案，不修改业务代码  
> 需求入口：后台管理系统 → 用户管理 → 用户详情 → 认证信息

## 1. 需求背景

后台用户详情已经展示用户绑定的认证信息，包括认证方式、脱敏身份标识、身份域、绑定时间和更新时间，但当前只能查看，无法由管理员手动维护。

本工单计划为“认证信息”模块增加受控的人工维护能力，用于处理测试账号准备、历史数据纠错、身份绑定异常和客服排障。由于 `SocialIdentity` 直接参与登录账号解析，人工修改可能造成账号无法登录、身份被绑定到错误用户或多个客户端身份域互相污染，因此不能按普通资料表单直接编辑。

## 2. 截图对应的目标位置

当前页面结构：

```text
用户详情
├─ 用户基础信息
├─ Pro 权益
├─ 认证信息                 ← 本工单范围
│  ├─ 认证方式
│  ├─ 身份标识
│  ├─ 身份域
│  ├─ 绑定时间
│  └─ 更新时间
├─ 登录设备信息
└─ 登录会话流水
```

建议在“认证信息”标题右侧增加维护入口，并在每条认证标识右侧增加行级操作。具体操作范围由问答确认后确定。

## 3. 当前代码事实

### 3.1 数据模型

关键文件：`accounts/models.py`

当前认证标识使用：

```text
SocialIdentity
├─ user             所属 User
├─ provider         apple / google / phone / email / device
├─ provider_uid     认证提供方的唯一身份标识
├─ bundle_id        账号身份域 identity_scope，不一定是真实客户端 bundle_id
├─ created_at
└─ updated_at
```

数据库唯一约束：

```text
bundle_id + provider + provider_uid 唯一
```

因此，同一身份域下的同一认证标识不能同时绑定给两个 User。

### 3.2 当前后台详情接口

关键文件：`backoffice/views.py`

当前接口：

```http
GET /api/admin/v1/users/{user_id}/detail/
```

`AdminUserDetailView` 查询 `SocialIdentity` 并返回 `auth_identities`。当前没有后台新增、修改、转移或解绑认证标识的接口。

### 3.3 当前序列化器

关键文件：`backoffice/serializers.py`

`AdminUserSocialIdentitySerializer` 当前只返回：

- `id`
- `provider`
- `provider_label`
- `provider_uid_masked`
- `bundle_id`
- `created_at`
- `updated_at`

后台详情默认不返回完整 `provider_uid`，符合现有脱敏展示规则。

### 3.4 当前后台前端

关键文件：

- `backoffice-web/src/views/UsersView.vue`
- `backoffice-web/src/api/modules/users.ts`

当前“认证信息”是只读表格，没有“新增认证标识”按钮，没有行级编辑/解绑操作，也没有对应请求方法和维护 DTO。

### 3.5 当前账号侧绑定逻辑

关键文件：`accounts/services/account_identity_service.py`

当前正式账号绑定流程要求验证码、Apple 凭证或验证 Ticket，并处理：

- 手机号和邮箱标准化；
- 身份域解析；
- 唯一绑定冲突；
- 已停用账号身份重新绑定；
- 用户邮箱同步；
- 登录与身份变更日志。

后台人工维护不能简单绕过全部规则直接 `SocialIdentity.objects.create/update/delete`，否则会与真实登录解析产生差异。

## 4. 初步业务目标

1. 管理员可在用户详情中维护认证标识。
2. 人工维护仍遵守 `identity_scope + provider + provider_uid` 唯一约束。
3. 手机号、邮箱继续复用现有标准化规则。
4. Apple、Google、设备身份不能因为表单输入而错误转换格式。
5. 管理员操作不能静默覆盖其他启用用户已有的身份绑定。
6. 保存后刷新当前用户详情中的认证信息列表。
7. 完整身份标识只在编辑所必需的受控流程中使用；普通详情列表继续脱敏。
8. 后续问答确认操作范围、冲突处理、支持 Provider、身份域来源、审计和二次确认。

## 5. 初步数据边界

### 5.1 认证标识不是普通用户资料

修改认证标识会改变登录解析结果：

```text
identity_scope + provider + provider_uid
                    │
                    └─ 定位 User
```

因此，认证标识维护不能等同于修改显示名称或邮箱展示字段。

### 5.2 `User.email` 与 Email SocialIdentity

当前系统可能同时存在：

- `User.email`：Django 用户字段；
- `SocialIdentity(provider=email).provider_uid`：用于账号身份解析的邮箱标识。

人工维护 Email 身份时，是否同步 `User.email` 必须在后续问题中明确，不能默认认为两者永远一致。

### 5.3 身份域不是客户端包名

`SocialIdentity.bundle_id` 当前语义是 `identity_scope`。后台表单应使用“身份域”命名，并由受控选项或现有映射生成，不应让管理员误以为必须填写真实 App Bundle Identifier。

## 6. 初步页面结构

```text
认证信息                                              [新增认证标识]
┌────────┬────────────────────┬────────────────┬──────────┬──────────┬────────┐
│认证方式│身份标识（脱敏）      │身份域           │绑定时间   │更新时间   │操作     │
├────────┼────────────────────┼────────────────┼──────────┼──────────┼────────┤
│Apple   │001234...ABCD       │health_shared   │...       │...       │[维护]   │
│邮箱    │hu***@example.com   │health_shared   │...       │...       │[维护]   │
└────────┴────────────────────┴────────────────┴──────────┴──────────┴────────┘
```

弹窗草案：

```text
┌──────────────────────────────────────────────┐
│ 维护认证标识                            [×] │
├──────────────────────────────────────────────┤
│ 目标用户：1162 / 夏文生                      │
│                                              │
│ 认证方式  [ 邮箱 ▼ ]                         │
│ 身份标识  [ hu@example.com              ]    │
│ 身份域    [ health_shared ▼ ]                │
│                                              │
│ 风险提示：保存后将改变该身份的登录归属。       │
│                                              │
│                         [取消] [确认保存]     │
└──────────────────────────────────────────────┘
```

以上仅为基础结构，按钮和字段是否出现以问答确认结果为准。

## 7. 当前关键文件

### 7.1 SparkService

| 文件 | 当前职责 | 预期影响 |
| --- | --- | --- |
| `accounts/models.py` | `SocialIdentity` 模型和唯一约束 | 原则上复用，不创建第二套认证标识表 |
| `accounts/services/account_identity_service.py` | 标准化、绑定、修改和冲突判断 | 后台维护服务应复用可复用规则，不直接散落写模型 |
| `accounts/services/identity_scope_service.py` | 客户端 Bundle 到身份域映射 | 设计身份域选项和校验来源 |
| `backoffice/views.py` | 用户详情和后台用户接口 | 增加认证标识维护接口 |
| `backoffice/serializers.py` | 后台请求与响应 DTO | 增加新增/修改/解绑校验器 |
| `backoffice/urls.py` | 后台路由 | 增加认证标识维护路由 |
| `backoffice/tests.py` | 后台用户接口测试 | 增加权限、冲突、标准化和更新测试 |

### 7.2 backoffice-web

| 文件 | 当前职责 | 预期影响 |
| --- | --- | --- |
| `src/views/UsersView.vue` | 用户详情弹窗和认证信息只读表格 | 增加入口、维护弹窗和操作反馈 |
| `src/api/modules/users.ts` | 用户详情 DTO 和接口 | 增加维护请求/响应类型与 API 方法 |

## 8. 当前非目标

- 本阶段不修改客户端登录页面。
- 本阶段不修改 Apple、Google、短信或邮箱真实认证流程。
- 不创建第二套认证标识表。
- 不把 `bundle_id` 重新解释为真实客户端 Bundle Identifier。
- 不允许后台通过认证标识维护直接修改用户密码。
- 不在本工单确认完成前修改业务代码。

## 9. 一问一答确认记录

### 第 1 问：后台“手动维护认证标识”需要支持哪些操作？

为什么要问：新增、修改、解除绑定和转移身份对登录账号的影响不同。尤其是删除最后一个正式认证方式，可能让用户无法再次登录；直接转移已属于其他用户的身份，还可能造成账号接管。

请选择：

- A. 支持新增、修改和解除绑定；不支持直接转移其他用户的身份（推荐）  
  冲突时只提示该标识已被其他用户占用；管理员必须先在原用户中解除，再到目标用户新增，两个动作分别确认。

- B. 只支持新增，不支持修改和解除绑定  
  风险最低，但无法处理录入错误和历史绑定纠正。

- C. 支持新增和修改，不支持解除绑定  
  可以纠错，但错误身份会长期留在账号下，无法完成清理。

- D. 支持新增、修改、解除绑定和一键转移  
  运维效率最高，但一键转移可能导致其他启用用户立即失去登录身份，需要更强审批和审计设计。

请选择 A、B、C 或 D。

#### 第 1 问确认

**已确认选择 A：支持新增、修改和解除绑定；不支持直接转移其他用户的身份。**

落地约束：

- 管理员可以在当前用户详情内新增认证标识、修改当前用户已有标识、解除当前用户已有标识。
- 如果目标身份已属于其他用户，接口只返回“该认证标识已被其他用户占用”，不得提供一键转移、覆盖或强制抢占按钮。
- 如确需转移，必须先在原用户详情中单独解除，再回到目标用户新增；两个动作独立确认、独立失败、独立刷新。
- 不通过前端隐藏按钮代替服务端约束；服务端仍必须执行唯一约束、用户状态和身份域校验。
- 解除绑定最后一个认证标识、修改正在使用的登录标识等高风险场景，是否需要额外确认和保护将在后续问题确认。

### 第 2 问：后台手动维护首期支持哪些认证方式？

为什么要问：当前 `SocialIdentity.Provider` 包含 Apple、Google、手机、邮箱和设备五类身份，但不同 Provider 的标识格式、来源可信度和登录影响不同。后台如果允许任意输入，可能把不可伪造的第三方 subject、设备标识或内部身份误当成普通文本。

请选择：

- A. 首期支持手机和邮箱；Apple、Google、设备身份只读展示（推荐）  
  手机和邮箱可以通过现有标准化规则维护；第三方登录 subject 与设备身份继续由真实登录流程产生，后台不直接伪造。

- B. 支持 Apple、Google、手机、邮箱和设备全部新增、修改、解除绑定  
  覆盖最完整，但会把第三方凭证、设备身份和账号接管风险全部交给后台人工输入。

- C. 首期只支持邮箱，其他认证方式保持只读  
  风险较低，但无法处理手机号迁移和测试账号常见的手机身份问题。

- D. 支持手机、邮箱和设备，Apple/Google 只允许修改  
  设备身份通常与安装和设备登录流程强关联，直接维护会破坏设备账号语义。

请选择 A、B、C 或 D。

#### 第 2 问确认

**已确认选择 A：首期支持手机和邮箱；Apple、Google、设备身份只读展示。**

落地约束：

- “新增认证标识”表单首期只允许选择手机或邮箱。
- Apple、Google 和设备身份继续显示在认证信息列表中，但不显示后台编辑、修改和解除绑定操作。
- 手机和邮箱必须复用现有标准化规则：手机号转为 E.164 格式，邮箱按现有规则去除首尾空格并统一小写后再校验唯一性。
- 后台人工维护不能伪造第三方登录 subject、设备 ID 或 Apple/Google 凭证。
- 后续如要维护 Apple、Google 或设备身份，必须单独确认真实凭证校验、设备会话影响和账号接管风险。

### 第 3 问：同一用户、同一身份域下，手机和邮箱认证标识应如何维护？

为什么要问：当前业务服务对同一用户同一身份域下的同一 Provider 已有绑定关系。后台如果允许同一用户绑定多个手机号或多个邮箱，需要重新定义登录解析、默认身份和解除最后身份的规则；如果只允许一个，则修改行为应明确为替换现有标识。

请选择：

- A. 每个 Provider 在同一身份域下最多保留一个；修改就是替换该 Provider 的现有标识（推荐）  
  与当前账号身份服务的“一种 Provider 一个绑定”语义一致；新增已有 Provider 时提示改为编辑，不产生第二条手机或邮箱身份。

- B. 同一 Provider 允许绑定多个手机或邮箱，登录时全部可用  
  灵活性高，但需要新增主身份、默认身份、解除其中一条和登录展示规则。

- C. 只允许新增，不允许替换已有手机或邮箱  
  数据边界简单，但无法处理手机号/邮箱变更和测试账号纠错。

- D. 后台可以新增多个，但登录时只使用最后修改的一条  
  会造成历史身份仍留在数据库中却不再生效，容易产生冲突和排障困难。

请选择 A、B、C 或 D。

#### 第 3 问确认

**已确认选择 A：每个 Provider 在同一身份域下最多保留一个；修改就是替换该 Provider 的现有标识。**

落地约束：

- 同一用户、同一身份域下，手机最多一条、邮箱最多一条；新增时如果该 Provider 已存在，前端引导进入编辑，不创建第二条记录。
- 修改操作更新当前 `SocialIdentity.provider_uid`，保留原记录 ID 和绑定时间，更新时间由服务端生成。
- 修改手机号或邮箱前后都执行现有标准化规则，再依据 `bundle_id + provider + provider_uid` 做唯一冲突校验。
- 不新增“主手机号”“主邮箱”字段，不新增多身份排序规则；本期沿用当前账号身份服务的一种 Provider 一条绑定语义。
- 解除绑定后该 Provider 允许重新新增；解除最后一个可用认证标识的保护规则由后续问题确认。

### 第 4 问：后台手动新增或修改手机/邮箱时，是否需要验证目标标识？

为什么要问：后台管理员输入的手机号或邮箱可能存在录入错误，也可能属于其他人。是否要求目标验证码，会决定“人工数据维护”和“真实身份认证”的责任边界；同时也影响演示账号准备和客服排障效率。

请选择：

- A. 后台管理员确认后可直接保存，不要求目标手机号/邮箱验证码（推荐）  
  适合后台运营和演示数据维护；服务端仍执行格式化、唯一性、账号状态和身份域校验，并明确这是管理员人工维护的绑定。

- B. 新增和修改都必须向目标手机号/邮箱发送验证码  
  能证明目标标识可控制，但后台维护流程依赖外部收信能力，测试账号和历史数据纠错会变复杂。

- C. 新增需要验证码，修改不需要验证码  
  能降低新增冒用风险，但修改现有登录身份仍可能造成账号无法登录或身份被替换。

- D. 只有 Superuser 可以免验证码，普通管理员必须验证  
  权限边界更细，但需要建立角色矩阵、验证码流程和紧急排障授权规则。

请选择 A、B、C 或 D。

#### 第 4 问确认

**已确认选择 A：后台管理员确认后可直接保存，不要求目标手机号/邮箱验证码。**

落地约束：

- 后台新增和修改手机/邮箱不调用目标手机号/邮箱验证码流程。
- 服务端仍执行手机号 E.164 标准化、邮箱小写标准化、唯一性约束、身份域校验和目标用户状态校验。
- 保存行为明确标记为管理员人工维护，不伪装成用户完成了真实登录认证。
- 后台表单提示管理员：保存后会影响该用户后续通过该手机号/邮箱登录的身份解析。
- 管理员确认、接口保存和详情刷新必须分为明确步骤，避免输入框回车或失焦直接改变账号身份。

### 第 5 问：解除绑定用户的最后一个认证标识时，应如何处理？

为什么要问：如果用户没有任何可用认证标识，可能无法通过手机号、邮箱或第三方身份登录；如果系统存在设备登录、后台账号或其他恢复方式，风险又可能不同。解除最后一条身份不能与普通解绑完全等价。

请选择：

- A. 允许解除，但必须二次确认并明确提示“用户可能无法通过认证方式登录”（推荐）  
  适合测试账号和人工纠错；服务端保存前重新统计当前身份，确认没有并发新增后再解除，并在结果中明确剩余认证标识数量。

- B. 禁止解除最后一个认证标识  
  能避免账号失联，但无法处理废弃测试身份、错误绑定和需要完全清空身份的场景。

- C. 解除最后一个认证标识时自动创建一个邮箱身份  
  会凭空生成登录入口，身份来源不真实，可能造成账号安全问题。

- D. 只有 Superuser 可以解除最后一个认证标识，普通管理员禁止  
  控制更严格，但需要额外角色权限与紧急操作流程；是否采用该权限分级还需单独设计。

请选择 A、B、C 或 D。

#### 第 5 问确认

**已确认选择 A：允许解除最后一个认证标识，但必须二次确认并明确提示用户可能无法通过认证方式登录。**

落地约束：

- 解除前重新查询该用户当前全部认证标识，并在事务内判断待解除记录仍属于目标用户。
- 页面二次确认明确显示当前 Provider、脱敏身份标识、身份域和解除后的剩余认证标识数量。
- 解除最后一个认证标识后允许保存，但结果页必须提示“当前用户可能无法通过认证方式登录”；不自动创建新身份，不自动修改 User 状态。
- 服务端使用事务和行锁/等价并发控制，避免管理员 A 判断有两条身份、管理员 B 同时解除另一条后，最终状态与提示不一致。
- 解除成功后刷新用户详情，认证信息列表显示空状态；登录失败行为沿用现有账号认证逻辑。

### 第 6 问：哪些后台角色可以新增、修改或解除用户认证标识？

为什么要问：当前用户详情由 `AdminOnlyPermission` 保护，但“查看用户”与“修改登录身份”风险不同。若只依赖现有后台访问权限，所有能查看用户详情的操作员都可能改变账号登录归属；若限制过严，又会影响演示和日常排障。

请选择：

- A. 沿用现有后台管理员访问权限，所有可进入用户详情的管理员都可以维护（推荐）  
  演示和运营流程最简单；服务端统一校验后台登录态，前端不按角色隐藏后再另行实现一套权限。

- B. 只有 Superuser 可以维护，Staff 只能查看  
  安全边界最清晰，但日常用户排障和演示账号准备都必须依赖超级管理员。

- C. Staff 可以新增和修改，只有 Superuser 可以解除绑定  
  权限分级更细，但需要维护操作级权限矩阵和不同按钮状态。

- D. 所有登录后台用户都可以维护，不区分 Staff/Superuser  
  实现简单，但会扩大认证身份修改范围，不符合现有后台权限模型。

请选择 A、B、C 或 D。

#### 第 6 问确认

**已确认选择 A：沿用现有后台管理员访问权限，所有可进入用户详情的管理员都可以维护。**

落地约束：

- 后台认证标识维护接口沿用现有后台登录态和 `AdminOnlyPermission`，不新增一套 Staff/Superuser 操作级权限。
- 能够查看用户详情的管理员默认拥有认证标识新增、修改和解除能力；前端可以根据接口返回状态展示按钮，但不能用前端隐藏代替服务端鉴权。
- 所有操作继续经过服务端用户、Provider、身份域、唯一性和并发校验。
- 如果未来需要将“查看用户”和“修改登录身份”拆分权限，另立权限治理工单，不在本期临时增加角色判断。

### 第 7 问：身份域 `bundle_id / identity_scope` 在后台表单中应如何维护？

为什么要问：`SocialIdentity.bundle_id` 实际存储的是账号身份域，不一定是真实客户端 Bundle Identifier。身份域决定认证标识的唯一范围；如果管理员自由填写，容易制造拼写不同但业务上应相同的身份域，导致用户登录解析不到原账号或产生错误绑定。

请选择：

- A. 只能从服务端提供的现有身份域选项中选择，不允许自由输入（推荐）  
  表单显示“身份域”而不是“客户端包名”；服务端复用 `IdentityScopeService` 的有效配置和规范化结果，保存时再次校验。

- B. 允许管理员自由输入 `bundle_id / identity_scope`  
  灵活性最高，但容易产生大小写、前后缀和历史别名错误，破坏账号身份解析一致性。

- C. 身份域固定为当前后台默认值，不在表单展示  
  操作最简单，但无法维护不同 App、不同业务或历史身份域下的用户身份。

- D. 允许输入真实客户端 Bundle Identifier，服务端自动当作身份域保存  
  会混淆真实包标识和账号身份域；当前系统已明确两者不一定相等。

请选择 A、B、C 或 D。

#### 第 7 问确认

**已确认选择 A：只能从服务端提供的现有身份域选项中选择，不允许自由输入。**

落地约束：

- 表单字段命名为“身份域”，不使用容易误解的“客户端包名”。
- 身份域选项由服务端基于 `IdentityScopeService` 的有效配置返回；前端不得自行维护下拉选项，也不得把任意字符串直接提交为身份域。
- 保存时服务端重新规范化并校验身份域，即使客户端提交了过期或伪造的选项值也不能写入无效 scope。
- `bundle_id` 的存储和唯一约束语义保持不变，不新增真实客户端包名字段。
- 如果现有身份域配置不可用，新增和修改操作失败并提示管理员联系系统配置维护者，不降级为自由输入。

### 第 8 问：后台维护邮箱认证标识时，是否同步更新 `User.email`？

为什么要问：当前系统同时存在 `User.email` 和 `SocialIdentity(provider=email).provider_uid`。邮箱身份用于登录解析，`User.email` 还可能被资料页、通知或业务查询使用；只更新其中一个会造成登录邮箱与用户资料邮箱不一致。

请选择：

- A. 邮箱认证标识保存成功后，同步 `User.email` 为规范化后的邮箱（推荐）  
  保持当前账号身份与用户基础资料一致；新增、修改和解除邮箱身份时都需要定义对应同步规则。

- B. 只维护 `SocialIdentity.provider_uid`，不更新 `User.email`  
  登录身份与用户资料可能长期不一致，后台排查时容易误判。

- C. 只更新 `User.email`，不维护 Email SocialIdentity  
  会绕过当前账号身份解析，邮箱可能无法用于登录或无法参与身份唯一性校验。

- D. 本期不允许后台维护邮箱，只维护手机号  
  可以规避字段同步问题，但会缩小已经确认的首期手机和邮箱维护范围。

请选择 A、B、C 或 D。

#### 第 8 问确认

**已确认选择 A：邮箱认证标识保存成功后，同步 `User.email` 为规范化后的邮箱。**

落地约束：

- 新增邮箱或修改邮箱成功后，在同一事务内将 `User.email` 更新为规范化后的 `SocialIdentity.provider_uid`。
- 邮箱唯一性以 `SocialIdentity` 的身份域、Provider 和标识约束为准；`User.email` 同步不能替代身份表唯一性校验。
- 保存响应和用户详情刷新应返回一致的邮箱值，避免认证信息模块和用户基础信息暂时显示不同邮箱。
- 邮箱保存失败时，`User.email` 不得单独更新；必须整体失败并回滚。
- 解除邮箱身份、替换邮箱身份时是否清空或保留 `User.email`，由下一题单独确认。

### 第 9 问：解除或替换邮箱认证标识时，`User.email` 应如何同步？

为什么要问：邮箱身份解除后，`User.email` 可能仍被通知、资料和后台查询使用。若清空过度，可能影响业务联系；若继续保留已解除的邮箱，又会让管理员误以为该邮箱仍可登录。

请选择：

- A. 解除邮箱身份时清空 `User.email`；替换时直接更新为新邮箱（推荐）  
  保持用户资料邮箱与可登录邮箱一致；解除后用户详情显示邮箱为空，后续通知能力由其他业务字段或重新绑定邮箱决定。

- B. 解除邮箱身份时保留 `User.email`；替换时更新为新邮箱  
  可以保留联系信息，但 `User.email` 会继续显示一个已不能用于当前账号身份登录的邮箱。

- C. 解除邮箱身份时保留 `User.email`，并额外增加“是否可登录”字段  
  信息最完整，但需要新增字段、展示和同步状态，超出本期最小落地范围。

- D. 解除或替换 Email SocialIdentity 时不再同步 `User.email`  
  会使认证信息与用户基础资料长期不一致。

请选择 A、B、C 或 D。

#### 第 9 问确认

**已确认选择 A：解除邮箱身份时清空 `User.email`；替换时直接更新为新邮箱。**

落地约束：

- 解除 Email `SocialIdentity` 时，在同一事务内将 `User.email` 清空。
- 替换 Email `SocialIdentity` 时，在同一事务内将 `User.email` 更新为新的规范化邮箱。
- 解除后用户详情中的基础邮箱和认证信息均为空；不把已解除邮箱继续作为可登录或默认联系邮箱展示。
- 新邮箱保存失败时不得修改 `User.email`；同步失败时整体回滚。
- 通知业务如果需要历史联系邮箱，必须使用独立的通知记录或业务字段，不从已解除身份反推。

### 第 10 问：认证标识新增、修改和解除是否需要记录后台操作审计？

为什么要问：认证标识直接决定登录账号归属，人工维护后必须能够回答“谁在什么时间对哪个用户做了什么修改”。但审计内容不能保存手机号、邮箱或第三方身份的明文，避免后台操作日志变成新的敏感数据泄露源。

请选择：

- A. 复用现有后台审计日志，记录新增/修改/解除、操作员、目标用户、Provider、身份域、脱敏前后标识和结果（推荐）  
  不新增第二套审计表；敏感标识只记录脱敏值或不可逆摘要，保留 request ID、失败原因和时间，便于排查。

- B. 不记录认证标识维护审计，只在用户详情显示更新时间  
  实现简单，但无法确认操作员和修改前后内容，不适合登录身份维护。

- C. 新增专用认证标识审计表，保存手机号和邮箱明文  
  追溯性强，但会复制高敏感身份数据并增加泄露面。

- D. 只记录成功操作，不记录失败和冲突尝试  
  可以减少日志量，但无法排查误操作、重复占用和恶意尝试。

请选择 A、B、C 或 D。

#### 第 10 问确认

**已确认选择 A：复用现有后台审计日志，记录新增/修改/解除、操作员、目标用户、Provider、身份域、脱敏前后标识和结果。**

落地约束：

- 不新增第二套认证标识审计表，复用现有后台操作审计日志写入机制。
- 成功、失败、唯一性冲突、权限失败和并发失败都记录审计结果。
- 审计至少包含操作员 ID、目标用户 ID、操作类型、Provider、身份域、脱敏前标识、脱敏后标识、结果、错误业务码、request ID 和时间。
- 手机号和邮箱只记录现有脱敏形式或不可逆摘要，不记录明文；认证凭证、验证码和完整请求体禁止进入审计 payload。
- 审计日志只用于追溯，不作为用户认证标识的事实来源；当前绑定仍以 `SocialIdentity` 为准。

### 第 11 问：维护表单中的手机/邮箱身份标识应如何显示和输入？

为什么要问：用户详情列表已经采用脱敏标识，但新增和修改需要管理员准确输入目标值。若始终只显示脱敏值，编辑时无法确认原值；若详情、日志和接口都返回明文，又会扩大敏感身份信息暴露范围。

请选择：

- A. 列表和详情表格继续脱敏；新增时输入完整值；编辑时默认不回填原值，管理员重新输入后替换（推荐）  
  避免明文身份值进入页面初始化数据、浏览器缓存和前端状态；修改时明确这是“替换标识”，不是基于原值的局部编辑。

- B. 编辑弹窗回填完整手机号或邮箱，管理员直接修改字符  
  操作方便，但完整身份标识会进入 DOM、前端状态、浏览器缓存和可能的错误上报。

- C. 列表和详情都展示完整手机号或邮箱，编辑时正常回填  
  排障直观，但会扩大后台敏感数据可见范围，不符合现有脱敏设计。

- D. 新增和编辑都只允许填写脱敏值  
  数据安全较好，但脱敏值无法作为可登录的真实身份标识保存。

请选择 A、B、C 或 D。

#### 第 11 问确认

**已确认选择 C：列表和详情都展示完整手机号或邮箱，编辑时正常回填。**

落地约束：

- 用户详情中的认证信息表格直接展示完整手机号或邮箱；新增和编辑弹窗正常回填已有值。
- Apple、Google 和设备身份仍只读展示，且继续遵守其现有脱敏规则；本选择只适用于首期允许维护的手机和邮箱。
- 前端不得把完整身份标识写入普通日志、埋点、错误上报、URL 查询参数或本地持久化缓存。
- 浏览器页面关闭、用户详情切换和退出后台时应清理维护弹窗状态；接口响应仍需避免返回不必要的其他用户身份明文。
- 审计日志继续按第 10 问只记录脱敏值或不可逆摘要，不因后台页面展示明文而改变审计存储规则。
- 该方案扩大后台敏感信息可见范围，正式上线前需要在产品验收中明确告知管理员，并由安全评审确认。

### 第 12 问：完整手机号/邮箱应通过什么接口返回给后台前端？

为什么要问：第 11 问允许详情和编辑回填完整标识，但现有 `GET /users/{user_id}/detail/` 使用脱敏 `AdminUserSocialIdentitySerializer`。如果直接改为全量返回，所有打开用户详情的页面都会获取明文；如果完全不返回，编辑无法回填，需要明确单独的数据获取边界。

请选择：

- A. 用户详情接口直接增加明文字段，打开详情即返回完整手机号/邮箱（推荐）  
  改造最少，页面展示和编辑回填共用一次请求；但用户详情响应会扩大明文身份数据暴露范围。

- B. 详情接口继续只返回脱敏值；点击“编辑/维护”后再调用专用接口获取完整标识  
  明文只在确实维护时返回，安全边界更小，但需要新增专用查询接口和加载状态。

- C. 前端根据脱敏值反推完整手机号/邮箱  
  无法恢复真实值，不可行。

- D. 编辑时管理员重新输入，不返回完整旧值；详情仍展示脱敏值  
  不满足“编辑时正常回填”，但可以避免接口返回旧明文。

请选择 A、B、C 或 D。

#### 第 12 问确认

**已确认选择 A：用户详情接口直接增加明文字段，打开详情即返回完整手机号/邮箱。**

落地约束：

- `GET /api/admin/v1/users/{user_id}/detail/` 继续作为用户详情唯一入口，认证信息表格和编辑弹窗共用该次响应。
- 手机和邮箱返回完整标识，Apple、Google、设备身份不新增明文返回，继续使用现有脱敏字段。
- 该接口响应中的明文字段只面向已通过现有后台管理员权限的请求；普通用户接口、列表接口和非后台接口不复用该字段。
- 前端页面可以展示和回填，但不得把明文放入 URL、浏览器 localStorage、普通缓存、日志、埋点或错误上报。
- 接口文档和 TypeScript DTO 必须明确明文字段的敏感等级，避免后续开发者误将其复制到通用列表模型。

### 第 13 问：用户详情接口中，手机/邮箱明文字段应如何命名？

为什么要问：现有接口已有 `provider_uid_masked`，它明确表示脱敏值。若直接把 `provider_uid` 改为明文，会改变已有字段语义并可能影响其他调用方；新增明确字段可以让前端知道哪些字段可展示、哪些字段仍然脱敏。

请选择：

- A. 保留 `provider_uid_masked`，新增 `provider_uid_plain`，仅对 phone/email 返回（推荐）  
  兼容现有表格字段；明文用途和适用 Provider 清晰，Apple/Google/device 返回 `null` 或不返回该字段。

- B. 将现有 `provider_uid_masked` 改为完整 `provider_uid`  
  前端改动少，但会破坏字段语义和现有依赖脱敏值的调用方。

- C. 统一使用 `provider_uid`，由前端根据 Provider 自行判断是否脱敏  
  数据契约不清晰，容易在其他页面误展示第三方身份明文。

- D. 新增 `provider_uid_full`，同时移除 `provider_uid_masked`  
  命名可以表达明文，但会破坏现有前端和其他客户端的兼容性。

请选择 A、B、C 或 D。

#### 第 13 问确认

**已确认选择 A：保留 `provider_uid_masked`，新增 `provider_uid_plain`，仅对 phone/email 返回。**

落地约束：

- 现有 `provider_uid_masked` 字段继续保留，保持认证信息列表兼容。
- 新增 `provider_uid_plain` 仅对 `provider=phone` 或 `provider=email` 返回完整值；Apple、Google、device 返回 `null` 或省略该字段。
- 明文字段只出现在后台用户详情接口，不加入用户列表、普通用户接口、登录响应或其他通用身份 DTO。
- 前端详情表格和维护表单使用 `provider_uid_plain`；审计日志、列表摘要和错误信息继续使用脱敏值或不可逆摘要。
- 服务端序列化器必须依据 Provider 再次限制明文字段，不能只依赖前端判断。

### 第 14 问：认证标识新增、修改和解除是否使用独立后台接口？

为什么要问：新增、修改和解除的校验条件、幂等性和审计内容不同。把三种动作塞进一个“保存详情”接口，容易出现误覆盖、误解除或前端把整行数据回传导致字段被重置。

请选择：

- A. 新增、修改、解除分别使用独立接口，明确表达动作（推荐）  
  建议使用 `POST /users/{user_id}/auth-identities/`、`PATCH /users/{user_id}/auth-identities/{identity_id}/` 和 `DELETE /users/{user_id}/auth-identities/{identity_id}/`；每个接口单独校验、单独审计和单独返回结果。

- B. 统一使用一个 `POST /users/{user_id}/auth-identities/maintain/` 接口，由 action 字段区分  
  请求集中，但需要服务端维护复杂分支，容易把新增、修改和解除的字段混在一起。

- C. 复用账号侧用户绑定接口，让后台模拟用户绑定流程  
  会混合用户自助认证和管理员人工维护，后台操作员、审计和无验证码规则难以表达。

- D. 直接通过用户详情 `PUT` 整体覆盖 `auth_identities` 数组  
  容易误删未展示的身份，也难以处理唯一冲突和并发修改。

请选择 A、B、C 或 D。

#### 第 14 问确认

**已确认选择 A：新增、修改、解除分别使用独立接口，明确表达动作。**

落地约束：

- 新增：`POST /api/admin/v1/users/{user_id}/auth-identities/`。
- 修改：`PATCH /api/admin/v1/users/{user_id}/auth-identities/{identity_id}/`。
- 解除：`DELETE /api/admin/v1/users/{user_id}/auth-identities/{identity_id}/`。
- 每个接口独立执行用户、Provider、身份域、格式化、唯一性、并发和审计校验。
- 不通过用户详情 `PUT` 整体覆盖 `auth_identities` 数组，避免未展示身份被误删。
- 修改和解除必须校验路径 `user_id` 与 `identity_id` 的归属关系；不允许借助身份 ID 操作其他用户记录。
- 新增、修改、解除成功后返回当前用户认证信息摘要，前端据此刷新详情；失败只返回稳定业务码和安全错误信息。

### 第 15 问：修改认证标识时，Provider 和身份域是否允许一起改变？

为什么要问：修改手机号/邮箱的本质是替换同一 Provider 的 `provider_uid`。如果允许把 Email 改成 Phone，或把身份从一个 scope 移到另一个 scope，实际是跨身份类型/身份域迁移，应该与普通修改分开处理。

请选择：

- A. 修改接口只允许修改 `provider_uid`；Provider 和身份域不可变，变更它们必须解除后重新新增（推荐）  
  保持单条身份记录语义稳定；跨 Provider 或跨身份域操作被拆为明确的解除与新增动作。

- B. 修改接口允许同时修改 Provider、身份域和 `provider_uid`  
  表单灵活，但可能把设备/第三方身份改造成手机或邮箱，且会改变唯一约束范围。

- C. Provider 不可变，但允许直接修改身份域和 `provider_uid`  
  仍然可能把用户身份从一个登录空间迁移到另一个空间，影响登录解析。

- D. 只允许修改身份域，Provider 和标识值保持不变  
  无法处理手机号、邮箱变更，且身份域迁移风险更高。

请选择 A、B、C 或 D。

#### 第 15 问确认

**已确认选择 A：修改接口只允许修改 `provider_uid`；Provider 和身份域不可变，变更它们必须解除后重新新增。**

落地约束：

- `PATCH` 请求体只允许提交当前 Provider 对应的 `provider_uid`；不接受 `provider`、`bundle_id` 或 `identity_scope` 作为可变字段。
- Provider 和身份域以数据库当前记录为准，服务端忽略或拒绝客户端提交的修改值，不能让前端通过隐藏字段完成跨类型/跨域迁移。
- 需要跨 Provider 或跨身份域时，必须先调用 `DELETE` 解除原身份，再调用 `POST` 新增目标身份；两个动作互不隐式合并。
- Provider、身份域和身份记录 ID 在修改前后保持稳定，审计中记录旧值和新值的脱敏结果/摘要。
- Apple、Google、device 继续只读；即使调用方绕过前端提交这些 Provider，服务端也必须拒绝修改。

## 10. 最终确认结论汇总

| 编号 | 已确认结论 | 落地约束 |
| --- | --- | --- |
| C-001 | 支持新增、修改、解除；不支持直接转移其他用户身份 | 冲突时拒绝；转移必须先原用户解除再目标用户新增 |
| C-002 | 首期只维护手机和邮箱 | Apple、Google、device 只读展示 |
| C-003 | 同一 Provider/身份域最多一条 | 修改替换 `provider_uid`，不产生第二条 |
| C-004 | 后台管理员可直接保存，不要求目标验证码 | 服务端仍做标准化、唯一性和状态校验 |
| C-005 | 允许解除最后一个认证标识 | 必须二次确认并提示可能无法登录 |
| C-006 | 沿用现有后台管理员访问权限 | 可进入用户详情的管理员都可维护 |
| C-007 | 身份域只从服务端有效选项选择 | 不允许自由输入，不把真实包名当身份域 |
| C-008 | 邮箱保存成功同步 `User.email` | 新增/修改同事务更新 |
| C-009 | 解除邮箱身份清空 `User.email` | 替换时更新为新邮箱 |
| C-010 | 复用现有后台审计日志 | 记录操作员、目标、Provider、域、脱敏值/摘要、结果和 request ID |
| C-011 | 手机/邮箱详情展示明文并编辑回填 | Apple/Google/device 仍脱敏；前端不得持久化明文 |
| C-012 | 用户详情接口直接返回明文 | 新增 `provider_uid_plain`，仅 phone/email 返回 |
| C-013 | 新增、修改、解除使用独立接口 | 不用整表覆盖 `auth_identities` |
| C-014 | 修改只允许改 `provider_uid` | Provider 与身份域不可变，迁移拆成解除+新增 |

## 11. 最终业务流程

### 11.1 打开用户详情

```text
管理员进入用户管理
    │
    └─ 点击“详情”
          │
          └─ GET /api/admin/v1/users/{user_id}/detail/
                │
                ├─ 基础信息
                ├─ Pro 权益
                ├─ 认证信息
                │    ├─ phone/email：provider_uid_plain + provider_uid_masked
                │    └─ apple/google/device：provider_uid_masked
                ├─ 登录设备信息
                └─ 登录会话流水
```

页面打开时直接取得手机/邮箱明文，认证信息模块展示完整值；不需要再次请求专用明文接口。

### 11.2 新增认证标识

```text
点击“新增认证标识”
    │
    ├─ Provider 选择：手机 / 邮箱
    ├─ 身份域从服务端选项选择
    ├─ 输入完整手机号或邮箱
    ├─ 前端基础格式提示
    ├─ 管理员点击确认保存
    │
    └─ POST /users/{user_id}/auth-identities/
          ├─ 服务端标准化 provider_uid
          ├─ 校验 User 存在且状态符合规则
          ├─ 校验身份域有效
          ├─ 校验 Provider/身份域/标识未被其他用户占用
          ├─ 创建 SocialIdentity
          ├─ Email 同步 User.email
          ├─ 写入后台审计
          └─ 返回当前认证信息 → 刷新详情
```

### 11.3 修改认证标识

```text
点击手机/邮箱行“编辑”
    │
    ├─ 回填 provider_uid_plain
    ├─ Provider 和身份域只读
    ├─ 修改完整 provider_uid
    ├─ 点击确认保存
    │
    └─ PATCH /users/{user_id}/auth-identities/{identity_id}/
          ├─ 锁定当前身份记录
          ├─ 校验记录属于 user_id
          ├─ 校验 Provider 为 phone/email
          ├─ 只读取请求体 provider_uid
          ├─ 标准化并检查唯一冲突
          ├─ 更新 provider_uid
          ├─ Email 同步 User.email
          ├─ 写入后台审计
          └─ 返回当前认证信息 → 刷新详情
```

### 11.4 解除认证标识

```text
点击手机/邮箱行“解除”
    │
    ├─ 显示 Provider、完整标识、身份域和解除后剩余数量
    ├─ 管理员二次确认
    │
    └─ DELETE /users/{user_id}/auth-identities/{identity_id}/
          ├─ 锁定 User 和 SocialIdentity
          ├─ 重新统计当前认证标识数量
          ├─ 删除目标 SocialIdentity
          ├─ 若为 Email：清空 User.email
          ├─ 写入后台审计
          └─ 返回当前认证信息 → 刷新详情
```

### 11.5 身份冲突

```text
目标身份已属于其他用户
    │
    ├─ 不覆盖
    ├─ 不转移
    ├─ 不删除原用户身份
    ├─ 写入失败审计
    └─ 返回 identity_already_bound
```

管理员必须先打开原用户详情解除，再到目标用户新增；本期不提供跨用户转移按钮。

## 12. 服务端落地方案

### 12.1 数据模型策略

继续复用：

```text
accounts.models.SocialIdentity
```

不新增 `AdminSocialIdentity` 或第二套认证身份表。现有字段仍为事实来源：

| 字段 | 新增 | 修改 | 解除 |
| --- | --- | --- | --- |
| `user` | 从 URL 目标用户确定 | 不变 | 不变 |
| `provider` | phone/email | 不可变 | 不变 |
| `provider_uid` | 规范化输入 | 只允许修改 | 删除记录 |
| `bundle_id` | 服务端选项 | 不可变 | 不变 |
| `created_at` | 自动生成 | 保留 | 记录在审计 |
| `updated_at` | 自动生成 | 自动更新 | 记录在审计 |

### 12.2 标准化规则

后台人工维护应复用 `AccountIdentityService` 的可复用方法，避免在 `backoffice/views.py` 重新实现：

- Provider 转小写并限制为 `phone/email`；
- 手机号规范化为 E.164；
- 邮箱去除首尾空格并转小写；
- 空字符串拒绝；
- 身份域通过 `IdentityScopeService` 解析并校验；
- 唯一性由服务端 QuerySet 和数据库约束双重保证。

如果当前服务层方法把“用户验证码 Ticket”与“管理员人工维护”强绑定，应抽取纯校验/标准化方法，不应让后台伪造验证码流程，也不应复制一套标准化代码。

### 12.3 后台接口契约

#### 新增

```http
POST /api/admin/v1/users/{user_id}/auth-identities/
Authorization: Bearer <admin-token>
Content-Type: application/json
```

请求：

```json
{
  "provider": "email",
  "provider_uid": "admin@example.com",
  "bundle_id": "cn.Zhaodk.Health"
}
```

服务端不接受验证码、登录 Token、设备密钥或转移参数。

#### 修改

```http
PATCH /api/admin/v1/users/{user_id}/auth-identities/{identity_id}/
Authorization: Bearer <admin-token>
Content-Type: application/json
```

请求：

```json
{
  "provider_uid": "new@example.com"
}
```

不允许提交：

```json
{
  "provider": "phone",
  "bundle_id": "another-scope",
  "user_id": 999,
  "transfer": true
}
```

这些字段应被拒绝或判定为只读字段，不能改变当前身份记录的 Provider、身份域和用户归属。

#### 解除

```http
DELETE /api/admin/v1/users/{user_id}/auth-identities/{identity_id}/
Authorization: Bearer <admin-token>
```

删除接口不接受“强制转移”“跳过确认”或目标用户参数。二次确认属于前端交互，服务端仍按请求执行最终校验和审计。

### 12.4 成功响应

建议新增、修改、解除接口统一返回：

```json
{
  "user_id": 1162,
  "auth_identities": [
    {
      "id": 301,
      "provider": "email",
      "provider_label": "邮箱",
      "provider_uid_masked": "hu***@example.com",
      "provider_uid_plain": "hua@example.com",
      "bundle_id": "cn.Zhaodk.Health",
      "created_at": "2026-09-04T11:50:00Z",
      "updated_at": "2026-09-04T12:01:00Z"
    }
  ],
  "remaining_count": 1
}
```

对于 Apple、Google、device，`provider_uid_plain` 必须为 `null` 或不返回。

### 12.5 错误码建议

| 业务码 | HTTP | 场景 | 前端处理 |
| --- | ---: | --- | --- |
| `ADMIN_AUTH_REQUIRED` | 401 | 后台未登录/失效 | 走后台登录恢复 |
| `USER_NOT_FOUND` | 404 | 用户不存在 | 关闭弹窗并刷新列表 |
| `AUTH_IDENTITY_NOT_FOUND` | 404 | 身份记录不存在或不属于用户 | 刷新详情 |
| `UNSUPPORTED_MANUAL_PROVIDER` | 400 | Apple/Google/device 被提交维护 | 保持只读 |
| `PROVIDER_REQUIRED` | 400 | 新增缺少 Provider | 表单定位字段 |
| `PROVIDER_UID_REQUIRED` | 400 | 标识为空 | 表单定位字段 |
| `IDENTITY_SCOPE_REQUIRED` | 400 | 未选择身份域 | 表单定位字段 |
| `IDENTITY_SCOPE_INVALID` | 400 | 身份域已失效/伪造 | 刷新选项 |
| `IDENTITY_FORMAT_INVALID` | 400 | 手机/邮箱格式错误 | 表单展示格式提示 |
| `IDENTITY_ALREADY_BOUND` | 409 | 已被其他用户占用 | 提示先解除原绑定 |
| `IDENTITY_PROVIDER_IMMUTABLE` | 400 | 修改 Provider | 拒绝请求 |
| `IDENTITY_SCOPE_IMMUTABLE` | 400 | 修改身份域 | 拒绝请求 |
| `IDENTITY_LAST_UNBIND_CONFIRM_REQUIRED` | 409 | 服务端要求确认但缺少确认标识 | 前端二次确认后重试 |
| `IDENTITY_CONCURRENT_MODIFICATION` | 409 | 记录已被其他操作改变 | 刷新详情后重试 |
| `USER_EMAIL_SYNC_FAILED` | 500 | Email 与 User.email 同步失败 | 整体回滚并提示失败 |

实际错误码编号应遵循现有后台错误码区间；上表是业务语义，不要求直接照抄编号。

### 12.6 服务层伪代码

```python
@transaction.atomic
def admin_create_identity(*, operator, user_id, provider, provider_uid, bundle_id, request):
    user = User.objects.select_for_update().get(pk=user_id)
    provider = normalize_manual_provider(provider)  # 只允许 phone/email
    scope = IdentityScopeService.resolve_admin_scope(bundle_id)
    normalized_uid = AccountIdentityService.normalize_provider_uid(provider, provider_uid)

    if SocialIdentity.objects.filter(
        bundle_id=scope,
        provider=provider,
        provider_uid=normalized_uid,
    ).exists():
        raise APIError("identity_already_bound", code=40922, status_code=409)

    identity = SocialIdentity.objects.create(
        user=user,
        provider=provider,
        provider_uid=normalized_uid,
        bundle_id=scope,
    )

    if provider == SocialIdentity.Provider.EMAIL:
        user.email = normalized_uid
        user.save(update_fields=["email"])

    write_admin_identity_audit(
        request=request,
        operator=operator,
        action="create",
        user=user,
        identity=identity,
        old_uid="",
        new_uid=normalized_uid,
        result="success",
    )
    return build_admin_identity_payload(user)
```

### 12.7 修改服务层伪代码

```python
@transaction.atomic
def admin_update_identity(*, operator, user_id, identity_id, provider_uid, request):
    user = User.objects.select_for_update().get(pk=user_id)
    identity = (
        SocialIdentity.objects
        .select_for_update()
        .get(pk=identity_id, user=user)
    )

    if identity.provider not in {SocialIdentity.Provider.PHONE, SocialIdentity.Provider.EMAIL}:
        raise APIError("unsupported_manual_provider", code=40091, status_code=400)

    old_uid = identity.provider_uid
    new_uid = AccountIdentityService.normalize_provider_uid(identity.provider, provider_uid)

    conflict = SocialIdentity.objects.filter(
        bundle_id=identity.bundle_id,
        provider=identity.provider,
        provider_uid=new_uid,
    ).exclude(pk=identity.pk).exists()
    if conflict:
        raise APIError("identity_already_bound", code=40922, status_code=409)

    identity.provider_uid = new_uid
    identity.save(update_fields=["provider_uid", "updated_at"])

    if identity.provider == SocialIdentity.Provider.EMAIL:
        user.email = new_uid
        user.save(update_fields=["email"])

    write_admin_identity_audit(
        request=request,
        operator=operator,
        action="update",
        user=user,
        identity=identity,
        old_uid=old_uid,
        new_uid=new_uid,
        result="success",
    )
    return build_admin_identity_payload(user)
```

### 12.8 解除服务层伪代码

```python
@transaction.atomic
def admin_delete_identity(*, operator, user_id, identity_id, request):
    user = User.objects.select_for_update().get(pk=user_id)
    identity = (
        SocialIdentity.objects
        .select_for_update()
        .get(pk=identity_id, user=user)
    )
    old_uid = identity.provider_uid
    provider = identity.provider
    scope = identity.bundle_id

    remaining_before = SocialIdentity.objects.filter(user=user).count()
    identity.delete()

    if provider == SocialIdentity.Provider.EMAIL:
        user.email = ""
        user.save(update_fields=["email"])

    write_admin_identity_audit(
        request=request,
        operator=operator,
        action="delete",
        user=user,
        identity=None,
        provider=provider,
        bundle_id=scope,
        old_uid=old_uid,
        new_uid="",
        remaining_count=max(remaining_before - 1, 0),
        result="success",
    )
    return build_admin_identity_payload(user)
```

说明：以上示例是服务层设计示例，不是对当前代码的直接修改。实际实现需要接入现有 `APIError`、`success_response`、`write_audit_log` 和项目的异常处理中间件。

## 13. 后台前端落地方案

### 13.1 TypeScript DTO

关键文件：`backoffice-web/src/api/modules/users.ts`

```ts
export interface AdminUserAuthIdentity {
  id: number;
  provider: string;
  provider_label: string;
  provider_uid_masked: string;
  provider_uid_plain: string | null;
  bundle_id: string;
  created_at: string;
  updated_at: string;
}

export interface AdminIdentityMutationPayload {
  provider?: 'phone' | 'email';
  provider_uid: string;
  bundle_id?: string;
}

export interface AdminIdentityMutationResponse {
  user_id: number;
  auth_identities: AdminUserAuthIdentity[];
  remaining_count: number;
}
```

建议 API 方法：

```ts
export function createUserAuthIdentity(
  userId: number,
  payload: { provider: 'phone' | 'email'; provider_uid: string; bundle_id: string },
) {
  return http.post<unknown, AdminIdentityMutationResponse>(
    `/api/admin/v1/users/${userId}/auth-identities/`,
    payload,
  );
}

export function updateUserAuthIdentity(
  userId: number,
  identityId: number,
  payload: { provider_uid: string },
) {
  return http.patch<unknown, AdminIdentityMutationResponse>(
    `/api/admin/v1/users/${userId}/auth-identities/${identityId}/`,
    payload,
  );
}

export function deleteUserAuthIdentity(userId: number, identityId: number) {
  return http.delete<unknown, AdminIdentityMutationResponse>(
    `/api/admin/v1/users/${userId}/auth-identities/${identityId}/`,
  );
}
```

具体 HTTP 方法需与项目 `http` 客户端已支持的封装保持一致；若当前封装没有 `patch/delete` 泛型重载，应补齐类型而不是改成 POST 伪装动作。

### 13.2 用户详情认证信息表格

关键文件：`backoffice-web/src/views/UsersView.vue`

页面结构：

```text
认证信息                                             [新增认证标识]
┌────────┬────────────────────┬──────────────┬──────────┬──────────┬────────┐
│方式    │完整身份标识         │身份域         │绑定时间   │更新时间   │操作     │
├────────┼────────────────────┼──────────────┼──────────┼──────────┼────────┤
│邮箱    │hua@example.com     │Health         │...       │...       │编辑 解除│
│Apple   │apple_000...         │Health         │...       │...       │只读     │
└────────┴────────────────────┴──────────────┴──────────┴──────────┴────────┘
```

行级操作规则：

- phone/email：显示编辑、解除；
- apple/google/device：显示“系统绑定，只读”；
- Provider 和身份域在编辑弹窗中不可编辑；
- 新增弹窗只展示 phone/email；
- 详情无认证信息时保留空状态和“新增认证标识”入口。

### 13.3 新增/编辑弹窗

新增：

```text
维护认证标识
目标用户：1162 · 夏文生

认证方式  [邮箱 ▼]
身份域    [cn.Zhaodk.Health ▼]
身份标识  [hua@example.com                         ]

说明：保存后该标识将成为该用户在所选身份域下的登录身份。

                                      [取消] [确认保存]
```

编辑：

```text
编辑认证标识
认证方式  邮箱（不可修改）
身份域    cn.Zhaodk.Health（不可修改）
身份标识  [hua@example.com                         ]

                                      [取消] [确认修改]
```

解除确认：

```text
解除认证标识？
认证方式：邮箱
身份标识：hua@example.com
身份域：cn.Zhaodk.Health
解除后剩余认证标识：0 条

警告：解除后用户可能无法通过认证方式登录。

                                      [取消] [确认解除]
```

### 13.4 前端状态示例

```ts
type IdentityModalMode =
  | { type: 'create' }
  | { type: 'edit'; identityId: number }
  | { type: 'delete'; identityId: number };

const editableProviders = new Set(['phone', 'email']);

function canEditIdentity(identity: AdminUserAuthIdentity) {
  return editableProviders.has(identity.provider);
}

async function saveIdentity() {
  if (modal.mode.type === 'create') {
    await createUserAuthIdentity(detail.user.id, {
      provider: form.provider,
      provider_uid: form.providerUid,
      bundle_id: form.bundleId,
    });
  } else if (modal.mode.type === 'edit') {
    await updateUserAuthIdentity(detail.user.id, modal.mode.identityId, {
      provider_uid: form.providerUid,
    });
  }

  await reloadUserDetail();
  closeModal();
}
```

前端校验只用于改善输入体验，最终校验必须由服务端完成。

## 14. 审计设计

复用现有后台审计日志，不新建表。建议操作名：

```text
admin.user.auth_identity.create
admin.user.auth_identity.update
admin.user.auth_identity.delete
```

审计 payload 示例：

```json
{
  "operator_user_id": 1,
  "target_user_id": 1162,
  "provider": "email",
  "identity_scope": "cn.Zhaodk.Health",
  "old_uid_masked": "ol***@example.com",
  "new_uid_masked": "ne***@example.com",
  "old_uid_sha256": "...",
  "new_uid_sha256": "...",
  "remaining_count": 1,
  "result": "success",
  "error_code": null,
  "request_id": "req-..."
}
```

要求：

- 明文手机号、邮箱不得写入审计；
- 失败和冲突也要审计；
- 审计不能被前端传入的 operator ID 覆盖；
- operator 从后台登录态取得；
- `request_id` 从当前请求上下文取得；
- 审计失败是否阻断业务保存，应沿用现有后台审计机制；若现有规则为异步/容错，需在实现说明中明确。

## 15. 并发与事务要求

### 15.1 新增冲突

两个管理员同时新增同一手机号/邮箱时：

1. 两个请求都执行规范化；
2. 数据库唯一约束只允许一个成功；
3. 失败请求转换为稳定的 `IDENTITY_ALREADY_BOUND`；
4. 失败也写入审计；
5. 前端刷新详情后展示最终状态。

### 15.2 修改冲突

修改前锁定当前 `SocialIdentity`；冲突 QuerySet 排除自身记录。若目标标识已被其他用户占用，不能覆盖。

### 15.3 解除最后一个身份

解除接口在同一事务中锁定 User 与目标身份，重新统计当前绑定数量，再删除并同步 `User.email`。事务失败时不得出现“身份已删但邮箱仍旧”或“邮箱已清空但身份仍在”的半完成状态。

### 15.4 Email 同步失败

Email 新增、修改、解除与 `User.email` 的同步必须在同一事务中完成。任何同步异常都回滚 `SocialIdentity` 变化，并记录失败审计结果。

## 16. 安全边界

本期确认后台详情展示完整手机号/邮箱，因此需要明确风险控制：

- 完整值只返回给已通过后台管理员鉴权的用户详情接口；
- 用户列表接口仍不返回明文；
- Apple/Google/device 不返回明文；
- 前端不写入 URL、localStorage、sessionStorage 或普通持久化缓存；
- 不进入 console、网络调试日志、埋点、异常上报和审计 payload；
- 请求失败信息只展示脱敏标识；
- 页面关闭、用户详情切换和后台退出时清理表单状态；
- 不接受客户端传入 operator、target user override、transfer 或 force 参数；
- 不允许通过接口直接修改第三方 subject 和 device identity；
- 后台操作员身份从服务端登录态确定；
- 全部新增、修改、解除动作都必须可通过 request ID 追踪。

## 17. 测试与验收标准

### 17.1 数据模型和服务端

- 可新增合法手机号；
- 可新增合法邮箱；
- 手机号标准化后唯一；
- 邮箱标准化后唯一；
- 无效身份域被拒绝；
- 自由输入身份域被拒绝；
- Apple/Google/device 被手动维护接口拒绝；
- 修改只能改变 `provider_uid`；
- 修改 Provider 被拒绝；
- 修改身份域被拒绝；
- 目标身份已属于其他用户时不覆盖；
- 不存在的用户返回稳定错误；
- 不属于用户的 identity ID 不能操作；
- 解除最后一个身份成功并正确提示；
- Email 新增/修改同步 `User.email`；
- Email 解除清空 `User.email`；
- 同步失败整体回滚；
- 并发新增只有一个成功。

### 17.2 详情响应

- phone/email 返回 `provider_uid_plain`；
- Apple/Google/device 不返回明文；
- 继续返回 `provider_uid_masked`；
- 无认证信息返回空数组；
- 不影响设备和会话模块；
- 用户列表不泄露 `provider_uid_plain`。

### 17.3 后台 UI

- 认证信息标题右侧显示新增入口；
- 手机/邮箱显示编辑和解除；
- Apple/Google/device 显示只读；
- 新增 Provider 只能选择手机/邮箱；
- 身份域只能选择服务端选项；
- 编辑正确回填明文；
- 编辑时 Provider 和身份域不可修改；
- 解除最后一个身份有二次确认；
- 成功后不刷新整个用户列表，只刷新详情数据；
- 冲突提示清晰且不关闭用户详情；
- 网络失败保留输入，允许重试；
- 用户切换时清理上一个用户的明文表单值。

### 17.4 审计

- 新增成功/失败有审计；
- 修改成功/失败有审计；
- 解除成功/失败有审计；
- 冲突和权限失败有审计；
- 审计包含操作员、目标用户、Provider、身份域、脱敏前后值、结果、错误码、request ID；
- 审计不含手机号/邮箱明文、验证码和完整请求体。

## 18. 实施顺序

### 阶段一：服务端规则复用

1. 抽取/复用手机号、邮箱标准化方法；
2. 抽取身份域服务端选项和校验；
3. 增加后台新增/修改/解除服务层；
4. 增加 Provider 和身份域不可变校验；
5. 实现 Email 与 `User.email` 同事务同步；
6. 接入现有后台审计日志；
7. 增加业务错误码和接口测试。

### 阶段二：后台 API

1. 增加三个独立路由；
2. 增加请求 Serializer；
3. 扩展用户详情响应 `provider_uid_plain`；
4. 确认用户列表不会返回明文字段；
5. 增加权限、冲突、并发、回滚测试。

### 阶段三：backoffice-web

1. 更新 `AdminUserAuthIdentity` DTO；
2. 增加 API 方法；
3. 在 `UsersView.vue` 增加新增入口；
4. 增加手机/邮箱编辑入口；
5. 增加解除二次确认；
6. 接入身份域选项接口；
7. 增加成功、失败、冲突和加载状态；
8. 切换用户时清理明文表单状态。

### 阶段四：联调验收

1. 使用测试用户验证新增手机/邮箱；
2. 验证详情完整值展示与编辑回填；
3. 验证 User.email 同步；
4. 验证最后身份解除；
5. 验证跨用户冲突；
6. 验证 Apple/Google/device 只读；
7. 验证普通列表与日志不泄露明文；
8. 验证管理员操作审计；
9. 通过全部验收标准后再进入代码实现。

## 19. 本工单交付边界

本工单已经完成认证标识手动维护的需求确认和详细落地设计，但当前只维护文档，没有修改 SparkService 或 backoffice-web 业务代码。实际开发时必须以本工单最终确认结论、现有账号身份服务和后台权限约定为准。
