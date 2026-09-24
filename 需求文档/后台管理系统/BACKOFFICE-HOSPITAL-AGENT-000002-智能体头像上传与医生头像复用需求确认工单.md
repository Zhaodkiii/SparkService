# BACKOFFICE-HOSPITAL-AGENT-000002 智能体头像上传与医生头像复用需求确认工单

> 状态：需求确认完成，待开发  
> 创建时间：2026-09-04  
> 适用系统：SparkService 后台管理系统、医院智能体服务、chat-web 医生工作台  
> 关联工单：BACKOFFICE-HOSPITAL-AGENT-000001、DOCTOR-WORKSPACE-000002  
> 工作方式：22 个问题已逐题确认，本稿已收口为开发实施基线  
> 当前阶段：只确认需求与落地方案，不实施代码

## 1. 工单目标

后台管理系统的新建智能体和编辑智能体表单需要支持智能体头像配置，提供两种来源：

1. 上传智能体专属头像。
2. 复用智能体关联医生的头像。

自定义头像文件必须上传至阿里云 OSS。业务模型只保存受管理的文件引用，不直接保存图片二进制、Base64 或任意外部 URL。

头像需要被统一输出到后台智能体列表、智能体详情、医生工作台当前服务智能体头部，以及后续患者端医生智能体展示场景。

## 2. 已确认需求

| 编号 | 已确认事项 | 状态 |
| --- | --- | --- |
| C-001 | 后台管理系统的新建智能体表单支持配置头像 | 已确认 |
| C-002 | 后台管理系统的编辑智能体表单支持配置头像 | 已确认 |
| C-003 | 支持上传智能体专属头像 | 已确认 |
| C-004 | 支持复用关联医生头像 | 已确认 |
| C-005 | 自定义图片上传至阿里云 OSS | 已确认 |
| C-006 | 在合适的后台管理系统需求目录建立独立工单 | 已确认 |
| C-007 | 后续通过逐题问答确认详细规则 | 已确认 |
| C-008 | 新建智能体默认复用关联医生头像 | 已确认 |
| C-009 | 编辑时头像来源可以自由切换；生效时机以后续 C-028、C-029 的“立即生效”为准 | 已确认并被后续规则覆盖 |
| C-010 | 支持 JPG、JPEG、PNG、WEBP，单张不超过 5 MB，最长边不超过 2048 px，建议正方形 | 已确认 |
| C-011 | 新增 SparkService 服务端公共 OSS 上传能力，后台文件先传 SparkService，再由服务端上传 OSS | 已确认 |
| C-012 | OSS 凭证复用 SparkService .env 中现有通用配置，不新增或暴露密钥 | 已确认 |
| C-013 | 使用现有 ALIYUN_OSS_BUCKET，zhaodkdream 作为公共 Object Key 根目录 | 已确认 |
| C-014 | 智能体头像路径采用 zhaodkdream/spark_service/hospital/avatar/{hospital_id}/{uuid}.webp | 已确认 |
| C-015 | 后台提供可调整的 1:1 裁剪框，服务端生成 1024×1024 WebP | 已确认 |
| C-016 | 头像文件永久保留，任何人都不能删除 | 已确认 |
| C-017 | 上传成功但未保存智能体时，文件永久保留并标记为未绑定 | 已确认 |
| C-018 | 历史文件只归属原智能体，不允许跨智能体复用；后台展示范围以后续 C-026 为准 | 已确认并被后续规则收敛 |
| C-019 | 智能体停用后不在线上展示头像，但保留头像历史；重新启用恢复最后一次有效头像配置 | 已确认 |
| C-020 | 头像读取失败时使用统一 AI 默认头像，最终使用智能体名称首字，不阻塞页面和对话 | 已确认 |
| C-021 | 技术上采用“上传文件 + 更新头像引用”两阶段调用；编辑已有智能体时第二阶段紧随上传自动执行，不等待整张表单保存 | 已确认并被后续规则细化 |
| C-022 | 公共头像上传 URL 不要求登录，依赖服务端生成的随机 object_key；OSS 密钥仍由 SparkService 保管 | 已确认 |
| C-023 | 公开上传接口当前只接受图片，视频需求暂不落地 | 已确认 |
| C-024 | 服务端保留 1024×1024 WebP，avatar_url 带版本标识，前端按展示尺寸处理并在头像操作成功后刷新 | 已确认 |
| C-025 | 历史会话消息不展示头像，只展示智能体名称 | 已确认 |
| C-026 | 后台只展示当前正在使用的头像，不展示头像历史列表 | 已确认 |
| C-027 | 不保留头像上传和来源变更审计记录；上传结果可直接用于后续头像使用 | 已确认 |
| C-028 | 上传专属头像成功后立即成为线上智能体头像，不等待智能体表单保存 | 已确认 |
| C-029 | 切回复用医生头像后立即生效，旧专属头像文件永久保留 | 已确认 |
| C-030 | 复用医生头像但医生无头像时，使用统一 AI 默认头像，再以智能体名称首字兜底 | 已确认 |
| C-031 | 服务端返回新的带版本 avatar_url；客户端下次请求或页面刷新时更新缓存，不新增实时推送 | 已确认 |

## 3. 当前代码事实

| 能力 | 当前实现 | 对本工单的影响 |
| --- | --- | --- |
| 医生头像 | DoctorProfile.avatar_file 外键关联 file_manager.ManagedFile | 可直接作为“复用医生头像”的来源，不复制文件 |
| 医生后台维护 | DoctorUpdateSerializer 已支持 avatar_file_id | 医生头像上传和绑定方式可作为参考 |
| 智能体模型 | ClinicalAgentProfile 当前没有独立头像字段和头像来源字段 | 需要补充智能体头像配置模型 |
| 智能体展示接口 | agent_public 当前通过 doctor_public 输出 doctor.avatar_url | 当前只能间接显示医生头像，无法表达智能体自定义头像 |
| 文件存储 | ManagedFile 已支持 object_key、storage_type、OSS 元数据 | 不新建第二套图片文件表 |
| OSS 授权 | 已有 /api/v1/oss/sts/credentials/，用于客户端直传场景 | 本工单新增服务端上传路径，不要求后台浏览器取得 STS |
| 上传登记 | 当前主要流程为客户端直传 OSS 后登记 ManagedFile | 需要补充“服务端上传 OSS + 原子登记 ManagedFile”的公共能力 |
| 文件业务关联 | ManagedFileBusinessRelation 已存在 | 可记录文件与 clinical_agent 的业务用途 |
| 医生工作台 | CurrentAgentHeader 已展示 agent.doctor.avatar_url | 后续应改为使用服务端计算后的 agent.avatar_url |

## 4. 初步领域设计

### 4.1 头像来源

建议为 ClinicalAgentProfile 增加明确的头像来源，而不是仅靠 avatar_file 是否为空进行推断：

~~~text
avatar_source
├── doctor：动态复用关联医生头像
└── custom：使用智能体专属 OSS 文件
~~~

建议新增字段：

~~~text
avatar_source     CharField，doctor/custom
avatar_file       ForeignKey(file_manager.ManagedFile)，允许为空
~~~

约束建议：

- avatar_source=doctor 时，avatar_file 必须为空，展示时动态读取 doctor.avatar_file。
- avatar_source=custom 时，avatar_file 必须存在且通过图片文件校验。
- 不复制医生头像对应的 ManagedFile。
- 不把医生头像 URL 固化到智能体记录中。
- 医生更换头像后，所有选择“复用医生头像”的智能体自动展示新头像。
- 使用专属头像的智能体不受医生头像变更影响。

### 4.2 第 1 问落地结论：新建默认复用医生头像

新建智能体时，表单默认选中“复用医生头像”，保存后默认写入：

~~~text
avatar_source = doctor
avatar_file = null
~~~

该规则表示智能体引用关联医生当前头像，不复制医生的 ManagedFile，也不创建新的 OSS 对象。医生后续更换头像后，所有 avatar_source=doctor 的智能体在下一次读取或刷新时自动展示新头像。

如果关联医生没有头像：

- 仍允许保存智能体。
- 头像来源保持 doctor，不自动改写成 custom。
- 展示层使用系统默认 AI 图标或智能体名称首字。
- 表单提示“当前医生暂无头像，可上传智能体专属头像”。
- 管理员后续可在编辑表单中切换为上传专属头像。

新建表单不默认触发 OSS 上传；只有管理员主动选择“上传专属头像”并选择图片时，才启动 OSS 上传链路。

### 4.3 第 2 问历史结论：头像来源保存后生效（已被第 19、20 问覆盖）

本节保留第 2 问当时的决策背景，不作为最终开发规则。编辑智能体时，管理员可以在“复用医生头像”和“上传专属头像”之间自由切换；最终生效时机以第 19、20 问为准：

- 已有智能体上传专属头像并完成“上传 + 头像引用更新”后立即生效。
- 已有智能体选择复用医生头像并完成头像引用更新后立即生效。
- 关闭或取消编辑时，不回滚已经成功生效的头像操作。
- 新建智能体尚无 agent_id，头像配置随创建智能体请求生效。
- 从 custom 切回 doctor 时，将 avatar_source 改为 doctor、avatar_file 清空。
- 切回 doctor 时不删除旧专属 ManagedFile 或 OSS 对象，保留其历史文件，便于后续再次切换。
- 从 doctor 切换为 custom 时，必须完成图片上传并取得有效 file_id 后才能保存该选择。
- 上传或头像引用更新失败时，继续保留当前已生效头像。

对于“上传后但尚未保存”的专属图片，文件先作为待绑定 ManagedFile 存在，不绑定到智能体线上配置；其永久保留规则已由第 6 问确认。

第 7 问确认后，补充以下业务状态：

- 文件上传到 OSS 成功后立即登记 ManagedFile。
- 未保存到智能体时，ManagedFile 标记为“未绑定”。
- “未绑定”只表示当前没有智能体引用，不表示文件无效或可删除。
- 当前表单在上传请求成功后持有 file_id，可以继续点击保存完成绑定。
- 关闭表单、保存失败或浏览器中断都不触发删除。
- 未绑定文件是否可在头像历史列表中再次选择，由第 8 问确认。

第 8 问确认后，头像历史的复用范围确定为：

- 当前智能体可以查看自己曾经使用过的专属头像文件。
- 当前智能体可以将自己的历史头像恢复为当前专属头像。
- 未绑定文件不进入默认头像选择列表。
- 其他智能体不能直接复用当前智能体的专属头像。
- 文件仍然永久保留，但“永久保留”不等于“全院可见”。

第 17 问对后台展示范围作最新收敛：头像文件和历史记录仍永久保留，但后台智能体表单只展示当前正在使用的头像，不提供历史头像列表和历史头像恢复入口。第 8 问中关于“界面可恢复旧头像”的展示结论以本次最新确认覆盖；后续如需恢复历史文件，需另立需求。

第 18 问确认后，头像上传不增加独立的审计确认步骤。上传成功返回的 file_id 和 avatar_url 可以直接供当前表单预览和后续头像配置使用；具体是否直接成为线上头像，继续由第 19 问确认。

第 19 问确认后，上传专属头像的生效时机确定为立即生效：

- SparkService 完成 WebP 生成、OSS 上传和 ManagedFile 登记成功后，立即更新当前智能体的专属头像引用。
- 头像更新不等待智能体表单其他字段保存。
- 取消编辑只能取消其他未保存字段，不能回滚已经生效的头像。
- 上传失败时保持当前线上头像不变。
- 该结论覆盖第 2 问中“头像来源切换统一保存后生效”的规则，仅针对“上传专属头像成功”场景；复用医生头像的切换时机由第 20 问确认。

第 20 问确认后，切回复用医生头像同样立即生效：

- 管理员选择“复用医生头像”后，立即将 avatar_source 切换为 doctor。
- 当前智能体的 avatar_file 引用立即解除。
- 线上展示立即读取关联医生当前头像。
- 原专属头像文件和 OSS Object 永久保留，但不再是当前智能体线上头像。
- 不等待智能体其他字段保存，也不要求额外审计确认。
- 医生没有头像时的展示降级由第 21 问确认。

第 21 问确认后，复用医生头像的无头像场景规则确定为：

- avatar_source 仍保持 doctor。
- 医生头像为空时使用统一 AI 默认头像。
- 默认 AI 头像加载失败时使用智能体名称首字。
- 医生以后补充头像后，智能体在下一次读取或刷新时自动展示医生头像。
- 不恢复旧专属头像，不改变 avatar_source，也不产生新的 OSS 文件。

第 9 问确认后，智能体状态变化与头像处理规则确定为：

- 智能体停用后，不在患者端、医生工作台当前服务区域和其他线上入口展示该智能体头像。
- 停用不删除头像文件、ManagedFile、OSS Object 或头像历史。
- 后台仍可在该智能体详情中查看头像历史。
- 智能体重新启用时，恢复最后一次有效的头像来源和头像引用。
- 若最后一次有效来源是复用医生头像，则恢复动态复用医生头像；若是专属头像，则恢复对应历史文件。
- 停用期间不允许通过其他智能体复用该头像历史。

### 4.11 第 10 问落地结论：头像展示降级

所有头像展示入口统一采用以下降级顺序：

~~~text
服务端返回 agent.avatar_url
  → 图片加载失败 / URL 无效
  → 系统统一 AI 默认头像
  → 默认头像资源不可用
  → 智能体名称首字头像
~~~

降级只替换图片展示，不改变智能体名称、医生信息、发布状态、会话绑定或对话请求。客户端可以对同一 URL 做一次失败标记，避免在当前页面持续重复请求；下一次正常刷新仍允许重新读取服务端头像地址。

前台患者端、医生工作台和后台管理系统必须使用同一套降级语义，不能在一个页面回退医生头像、另一个页面回退 AI 默认头像。

### 4.12 第 11 问落地结论：两阶段上传与智能体保存

头像自定义配置采用两个明确阶段：

~~~text
阶段一：POST 公共头像上传接口
  → 服务端校验图片
  → 服务端生成 WebP 并上传 OSS
  → 创建 ManagedFile
  → 返回 file_id、预览 avatar_url、上传结果元数据

阶段二：PATCH 智能体接口
  → avatar_source=custom
  → avatar_file_id=file_id
  → version=当前智能体版本
  → 服务端校验文件和医院归属
  → 事务内更新 ClinicalAgentProfile 头像引用
~~~

接口边界：

- 客户端不能直接提交 OSS object_key 作为智能体头像。
- 智能体保存失败时，当前线上头像不变，上传文件按“未绑定”永久保留。
- 智能体保存成功后，旧头像只解除业务引用，不删除 OSS Object。
- `avatar_source=doctor` 时不需要 `avatar_file_id`，服务端应清空当前智能体专属头像引用。
- `avatar_source=custom` 时必须提供有效 `avatar_file_id`，否则拒绝保存。
- 保存请求必须携带智能体 `version`，继续沿用现有版本冲突语义。
- 上传接口返回的预览地址仅用于当前表单预览，最终展示地址以智能体保存成功后的 `agent.avatar_url` 为准。
- 上传结果需要返回 request_id、object_key、file_id、文件大小、MIME、ETag 或校验信息，便于审计和问题排查；不返回任何 OSS 密钥。

第 6 问确认后，该规则调整为：无论头像是否已绑定、是否被替换、智能体是否停用，已上传成功的头像文件和 OSS Object 均永久保留，任何后台操作都不能删除。业务层只允许改变当前头像引用和文件状态标记。

### 4.4 第 3 问落地结论：图片格式与尺寸

智能体专属头像采用以下统一校验规则：

| 校验项 | 规则 |
| --- | --- |
| 文件扩展名 | .jpg、.jpeg、.png、.webp |
| MIME 类型 | image/jpeg、image/png、image/webp |
| 最大文件大小 | 5 MB |
| 最大像素 | 图片最长边不超过 2048 px |
| 宽高比 | 建议 1:1，当前不强制正方形 |
| 校验位置 | 后台前端预检 + SparkService 服务端强制校验 |

服务端不能只相信扩展名和浏览器提供的 Content-Type，必须解析图片头和真实像素尺寸。扩展名、MIME 与实际图片格式不一致时拒绝上传。

图片小于限制时保留原图，不因为上传而放大；具体裁剪和缩略图规则在后续问题确认。

### 4.5 展示字段

agent_public 建议统一输出：

~~~text
avatar_source
avatar_file_id        仅内部管理接口需要
avatar_url            服务端按来源解析后的最终展示地址
doctor.avatar_url     继续保留医生本人的头像地址
~~~

客户端只使用 agent.avatar_url 展示智能体头像，不自行判断 custom 或 doctor，也不自行拼接 OSS 地址。

### 4.6 服务端公共 OSS 上传链路基线

~~~text
后台选择图片
  → 前端校验文件类型与基础尺寸
  → 以 multipart/form-data 上传至 SparkService 公共上传接口
  → SparkService 再次校验文件大小、真实格式和像素
  → SparkService 使用服务端 OSS 凭证上传 Object
  → 上传成功后由服务端创建 ManagedFile
  → 得到 file_id
  → 保存智能体时提交 avatar_source=custom + avatar_file_id
  → 服务端校验文件归属、类型和可用状态
  → 建立智能体与 ManagedFile 的引用/业务关系
  → agent_public 返回最终 avatar_url
~~~

长期 OSS AccessKey 不下发到浏览器。后台管理系统只与 SparkService 通信，由 SparkService 完成 OSS SDK 调用。

### 4.7 公共上传服务边界

公共能力应放在 file_manager 或独立 OSS 基础设施服务中，不写死在智能体业务 Service 内。它需要支持服务端内部按不同数据源上传：

- 本地完整文件路径。
- 字符串内容。
- bytes 字节数组。
- 二进制文件流。
- 网络响应流。
- 上传进度回调。
- 上传完成或失败回调。

对外 HTTP API 首版只需要承载后台头像上传的 multipart 文件。字符串、字节数组、文件路径和网络流属于 Python 服务内部调用能力，不向普通后台调用者暴露任意服务器路径或任意网络 URL，避免本地文件读取和 SSRF 风险。

公共上传服务负责：

1. 从 Django settings 读取 OSS Bucket、Region、Endpoint 和凭证配置。
2. 生成不可预测且禁止覆盖的 Object Key。
3. 使用官方 OSS Python SDK 执行 PutObject。
4. 设置正确 Content-Type。
5. 开启禁止覆盖同名 Object 的请求条件，或通过随机 Key 从设计上避免碰撞。
6. 返回 object_key、ETag、CRC64、版本 ID、请求 ID等上传结果。
7. 上传成功后创建 ManagedFile；数据库失败时记录待清理 Object。
8. 输出必要的基础设施运行日志，但不创建头像业务审计记录，且绝不记录 AccessKey、Secret、文件正文或图片字节。

### 4.8 OSS 配置约束

复用 SparkService/.env 现有通用变量：

~~~text
ALIYUN_ACCESS_KEY_ID
ALIYUN_ACCESS_KEY_SECRET
ALIYUN_STS_ROLE_ARN
ALIYUN_OSS_BUCKET
ALIYUN_OSS_REGION
ALIYUN_OSS_ENDPOINT
ALIYUN_STS_DURATION_SECONDS
~~~

工单、日志、接口响应和前端代码中不得出现这些变量的真实值。生产环境优先使用最小权限 RAM 角色或子账号，只授予目标 Bucket/前缀所需的 PutObject、GetObject 和必要删除权限。

本工单最终确认的公开图片上传 URL 不要求登录；它只负责接收和处理图片、上传 OSS、登记未绑定 ManagedFile，不允许匿名调用者更新 ClinicalAgentProfile。将头像应用到已有智能体仍必须调用经过后台登录与 agent:update 权限校验的头像接口。

### 4.9 第 5 问落地结论：服务端裁剪与 WebP 转换

头像上传界面提供可调整的 1:1 裁剪框，管理员可以移动图片和缩放图片，确认最终头像区域。客户端提交原图与裁剪参数，SparkService 服务端负责生成最终文件：

~~~text
原图 JPG / JPEG / PNG / WEBP
  → 服务端读取并校验真实图片
  → 根据 crop_x、crop_y、crop_width、crop_height 执行 1:1 裁剪
  → 生成 1024 × 1024 WebP
  → 上传 zhaodkdream/spark_service/hospital/avatar/{hospital_id}/{uuid}.webp
  → 创建 ManagedFile
~~~

落地约束：

- 客户端裁剪框只负责交互预览，服务端必须重新校验裁剪参数，不能信任客户端直接传来的结果。
- 裁剪区域不得越出原图边界；面积为零、负数、NaN 或超出范围时拒绝。
- 原图最长边仍受 2048 px 和 5 MB 限制。
- 最终对象统一为 1024×1024 WebP，Object Key 后缀固定为 .webp。
- 服务端生成的 WebP 才是 ManagedFile 的有效对象，客户端临时预览图不登记为最终头像。
- 转换失败时不创建 custom 智能体头像引用，不影响当前已生效头像。

### 4.10 第 4 问落地结论：Bucket 与 Object Key

智能体头像继续使用当前环境配置的 ALIYUN_OSS_BUCKET，不创建新的 zhaodkdream Bucket。zhaodkdream 是该 Bucket 内的公共 Object Key 根目录。

智能体头像的对象路径固定为：

~~~text
zhaodkdream/spark_service/hospital/avatar/{hospital_id}/{uuid}.webp
~~~

路径规则：

- hospital_id 使用智能体所属医院 UUID，由服务端从权限上下文和业务对象取得，不接受前端任意指定。
- uuid 由服务端为每次上传生成 UUID，不能使用原始文件名、医生姓名、智能体名称或顺序时间戳。
- 每次上传创建新 Object Key，不覆盖旧对象。
- OSS 请求启用禁止覆盖语义；即使 UUID 极低概率冲突，也必须返回冲突并重新生成。
- 路径中不包含患者信息、手机号、证件号或其他个人敏感信息。
- .webp 表示最终存储对象统一使用 WebP；裁剪方式和输出尺寸已在第 5 问确认。
- 不同医院通过 hospital_id 目录隔离，服务端同时执行医院权限校验，不能仅依赖路径隔离。
- ManagedFile.object_key 保存完整对象路径，file_path 不作为客户端自行拼接 URL 的依据。
- API 对外返回由服务端生成的 avatar_url，客户端不拼接 Bucket、Endpoint 或 Object Key。

### 4.16 第 15 问落地结论：版本化头像 URL 与缩略显示

服务端永久保留最终生成的 1024×1024 WebP，展示端使用带版本标识的 avatar_url，并在不同展示尺寸下通过 OSS 图片处理参数获取合适的响应尺寸。

~~~text
原始对象：1024×1024 WebP，永久保留
  → 服务端返回带 file_id / revision / object version 的 avatar_url
  → 前端按头像展示尺寸请求 OSS 图片处理结果
  → 头像操作成功后以新 avatar_url 替换内存和页面缓存
~~~

约束：

- 不使用不带版本的固定 URL 作为唯一缓存键。
- 头像操作成功前不刷新线上智能体头像缓存。
- 头像操作成功后只刷新当前智能体相关缓存，不清理患者、会话或其他智能体缓存。
- 历史头像对象不删除，旧 URL 仍可用于审计和当前智能体头像历史。
- 客户端不自行拼接 Bucket、Endpoint 或图片处理参数的安全签名。
- OSS 图片处理参数必须由服务端允许的尺寸白名单生成，避免通过公开 URL 执行任意图片处理。

### 4.17 第 16 问落地结论：历史会话不展示头像

历史会话的消息流中不展示智能体头像，只展示智能体名称和现有消息身份信息。头像变化不会影响历史消息的视觉内容，也不需要给每条历史消息增加头像快照字段。

- 历史消息不请求头像 URL。
- 历史会话不依赖头像文件是否仍可访问。
- 当前智能体头部、后台列表和会话列表仍按最新有效头像展示。
- 患者端历史消息同样遵循“不展示头像、展示智能体名称”的规则。

### 4.11 第 9 问落地结论：停用后的头像生命周期

智能体停用后不再作为线上智能体头像展示，但头像文件、ManagedFile、OSS Object 和该智能体的头像历史均永久保留。智能体重新启用时，恢复最后一次有效的头像来源和头像引用。

### 4.12 第 10 问落地结论：头像展示降级

头像展示统一按照以下顺序降级：

~~~text
agent.avatar_url
  → 系统统一 AI 默认头像
  → 智能体名称首字头像
~~~

头像加载失败只影响图片，不影响智能体名称、医生信息、会话绑定、患者咨询和医生工作台使用；不回退到医生头像，避免 custom 专属头像失败时造成身份误导。

### 4.13 第 11 问落地结论：两阶段上传与智能体保存

头像采用“上传”和“更新智能体头像引用”两阶段接口：先由 SparkService 接收图片、生成 WebP、上传 OSS 并登记 ManagedFile，返回 file_id；再通过头像专用接口提交 avatar_source、avatar_file_id 和 version。编辑已有智能体时，前端在上传后自动执行第二阶段，不等待整张表单保存；只有第二阶段成功后，线上智能体头像才切换。

上传成功但智能体保存失败时，当前线上头像保持不变，新文件标记为未绑定并永久保留；客户端不能直接提交 OSS object_key。

### 4.14 第 12 问落地结论：公开头像上传 URL

按本次选择，头像上传 URL 不要求调用方登录，SparkService 仍负责接收文件、执行格式与像素校验、生成 WebP 并上传 OSS。客户端不能获得任何 OSS 长期密钥。

安全边界：

- 公开 URL 只能用于智能体头像上传，不得成为通用任意文件上传接口。
- object_key 必须由服务端随机生成，客户端不可指定医院、用户、智能体或任意目录。
- 服务端固定 Object Key 根目录为 zhaodkdream/spark_service/hospital/avatar/。
- 接口限制请求体大小、请求频率、并发数和单 IP 上传速率。
- 接口必须执行真实图片解析、5 MB、格式和最长边校验。
- 不在响应中返回 Bucket 凭证、服务器路径或内部异常。
- 公开 URL 无法可靠建立医院和操作员责任链，该风险按演示方案接受并记录。

### 4.15 第 13/14 问落地结论：公共接口当前只处理图片

根据最新确认，公开上传接口当前只接受图片，视频需求暂不落地。服务端根据真实图片 MIME 选择允许的图片处理分支，但智能体头像业务仍使用独立的头像目录和 WebP 处理：

~~~text
智能体头像：
zhaodkdream/spark_service/hospital/avatar/{hospital_id}/{uuid}.webp

其他图片：
zhaodkdream/spark_service/hospital/image/{hospital_id}/{uuid}.{ext}
~~~

落地约束：

- 头像接口和通用图片接口应在 URL、业务类型和序列化契约上明确区分。
- 智能体头像仍必须执行裁剪并生成 1024×1024 WebP，不能上传视频作为 avatar_file。
- 服务端不能只信任请求头 MIME，必须读取文件头并校验真实格式。
- 图片的大小、格式、缩略图和恶意内容检测由后续问题确认。
- 视频不进入当前公开上传接口的允许类型列表、目录规则或 ManagedFile 业务流程。
- 不允许调用方通过 MIME 伪造结果写入 avatar、image 或 video 之外的任意目录。
- 未绑定的图片同样按永久保留规则处理；具体 ManagedFile 业务状态仍需记录。

## 5. 后台表单初步结构

新建和编辑智能体使用同一头像控件：

~~~text
智能体头像

(●) 复用医生头像
    [医生头像预览] 张医生
    医生更新头像后，智能体头像同步更新

( ) 上传专属头像
    [上传区域 / 当前图片预览]
    [重新上传] [移除]

说明：已有智能体以头像专用接口成功为生效点，不等待整张表单保存；新建智能体以创建接口成功为生效点。
~~~

## 6. 问答议题总览（已完成）

22 个问题已全部确认；以下列表保留为决策主题索引：

1. 新建智能体的默认头像来源。
2. 自定义头像与医生头像之间的切换规则。
3. 图片格式、大小、像素和宽高比。
4. 是否提供裁剪、旋转和缩放。
5. OSS object_key 目录与文件命名。
6. 文件归属、跨管理员访问和删除规则。
7. 表单取消、上传成功但未保存时的临时文件处理。
8. 替换头像后旧文件的保留和回收策略。
9. 智能体下架、删除后的头像生命周期。
10. 前台展示失败时的降级头像。
11. API 字段、并发版本和审计记录。
12. 权限、越权防护和文件安全校验。
13. 列表缩略图、详情预览与缓存刷新。
14. 历史会话中的头像是否快照化。
15. 验收测试和演示数据准备。

## 7. 问答确认记录

### Q1：新建智能体时，默认头像来源是什么？

为什么要问：新建表单需要稳定默认值。默认复用医生头像可以减少操作并保持医生身份一致；默认要求上传专属头像则能强化智能体品牌，但会增加创建成本。该选择还会决定 avatar_source 的数据库默认值、空值校验和批量迁移规则。

用户选择：A。  
结论：新建智能体默认复用关联医生头像。  
状态：已确认。

### Q2：编辑智能体时，头像来源切换如何处理？

为什么要问：复用医生头像和上传专属头像是两种不同的引用关系。切换时需要明确是否立即替换展示、是否保留旧的专属文件，以及取消编辑时是否影响当前线上头像，避免误删 OSS 文件或出现头像短暂丢失。

请选择：

- A. 可以在“复用医生头像”和“上传专属头像”之间自由切换；保存后才生效（推荐）  
  编辑期间只修改表单草稿；点击保存后才更新智能体头像来源。切换回医生头像时保留旧专属文件，便于再次切换。

- B. 切换到上传专属头像后立即生效  
  操作反馈快，但用户取消编辑时需要回滚智能体引用，状态处理更复杂。

- C. 一旦上传专属头像就不能切回复用医生头像  
  规则简单，但后续维护不灵活，也无法适应医生头像统一更新。

- D. 编辑时只能替换图片，不能切换头像来源  
  始终使用当前来源，无法满足医生头像与智能体专属头像之间的运营切换。

用户选择：A。  
结论：头像来源可以自由切换，但必须保存后才生效；切回医生头像时保留旧专属文件。  
状态：已确认。

### Q3：上传的智能体头像支持哪些图片格式和尺寸？

为什么要问：格式、文件大小和像素限制会直接影响 OSS 存储成本、后台预览加载速度、医生工作台和 iOS 客户端的兼容性。规则越早固定，前端校验、服务端校验和缩略图策略越容易保持一致。

请选择：

- A. 支持 JPG、JPEG、PNG、WEBP；单张不超过 5 MB，建议正方形，服务端限制最长边 2048 px（推荐）  
  兼容常见头像来源，并保留足够清晰度；前端和服务端都执行同一套限制。

- B. 只支持 JPG、PNG；单张不超过 2 MB，必须正方形 1024×1024 以内  
  文件更小、规则更严格，但会拒绝部分 WEBP 图片和高分辨率原图。

- C. 支持所有常见图片格式；单张不超过 20 MB，不限制尺寸  
  上传最宽松，但会增加解析、存储、加载和恶意图片风险。

- D. 只支持 PNG；单张不超过 1 MB，固定 512×512  
  展示稳定、体积小，但图片兼容性和清晰度有限。

用户选择：A。  
结论：支持 JPG、JPEG、PNG、WEBP；单张不超过 5 MB；建议正方形；最长边不超过 2048 px。  
状态：已确认。

补充确认：头像文件由后台上传到 SparkService，再由 SparkService 使用通用 OSS 配置上传并登记 ManagedFile，不采用后台浏览器直传 OSS。

### Q4：你提到的 zhaodkdream 在 OSS 中具体作为什么？

为什么要问：OSS 的 Bucket 名和 Object Key 目录前缀是两种不同资源。Bucket 需要提前创建、配置地域和 RAM 权限；目录前缀只是在现有 Bucket 内组织对象。若定义不清，开发环境、生产环境和权限策略会产生不同实现。

请选择：

- A. 使用现有 ALIYUN_OSS_BUCKET，zhaodkdream 作为公共 Object Key 根目录（推荐）  
  例如 zhaodkdream/hospital-agent/avatar/{hospital_id}/{uuid}.webp；继续复用现有 Bucket 配置和权限体系。

- B. 新建名称为 zhaodkdream 的独立 Bucket  
  智能体头像全部存入独立 Bucket，需要单独配置地域、Endpoint、跨域、域名和 RAM Policy。

- C. zhaodkdream 是业务仓库名称，不进入 OSS 路径  
  OSS 仍使用现有 Bucket，并采用 hospital-agent/avatar 作为对象目录。

- D. 每家医院创建独立 Bucket，zhaodkdream 只作为演示医院 Bucket  
  隔离最强，但运维、配置和跨医院扩展成本最高。

用户选择：A，并指定路径。  
结论：使用现有 ALIYUN_OSS_BUCKET；zhaodkdream 作为公共根目录；智能体头像路径为 zhaodkdream/spark_service/hospital/avatar/{hospital_id}/{uuid}.webp。  
状态：已确认。

### Q5：上传图片后如何裁剪和转换为最终的 WebP 头像？

为什么要问：输入可以是 JPG、PNG 或 WEBP，且只要求“建议正方形”，但最终 Object Key 已固定为 .webp。必须确定由谁裁剪、是否保留透明背景以及输出尺寸，否则不同客户端可能出现拉伸、黑边或显示结果不一致。

请选择：

- A. 后台提供可调整的 1:1 裁剪框；SparkService 按裁剪参数生成 1024×1024 WebP（推荐）  
  管理员可移动、缩放图片确认头像范围；服务端重新执行裁剪和编码，最终结果一致。

- B. 后台只预览，不提供裁剪；SparkService 自动从中心裁成 1:1 并生成 1024×1024 WebP  
  开发简单，但人物不居中时可能裁掉脸部或重要内容。

- C. 不裁剪，保持原始宽高比，仅转换为 WebP  
  最尊重原图，但圆形头像中可能出现留白，不同页面裁切范围也可能不同。

- D. 后台强制用户上传正方形图片，SparkService 只转换为 WebP  
  服务端处理简单，但上传体验较差，用户需要自行准备图片。

用户选择：A。  
结论：后台提供可调整的 1:1 裁剪框；SparkService 按裁剪参数生成 1024×1024 WebP。  
状态：已确认。

### Q6：智能体头像文件的归属、访问和删除如何处理？

为什么要问：文件实际由 SparkService 服务账号上传 OSS，但业务上属于医院智能体。如果仍按上传管理员个人归属，会导致管理员离职或账号停用后头像失效；如果允许管理员删除，又可能破坏历史记录和仍在使用的智能体头像。

请选择：

- A. 业务归属医院和智能体，上传人只记录为创建人；同医院后台管理员可查看和维护，已被智能体引用的文件不可直接删除
- B. 文件归属上传管理员个人，只有上传人可以删除
- C. 所有后台管理员都可以直接删除 OSS 文件，不检查智能体引用
- D. 文件永久保留，任何人都不能删除

用户选择：D。  
结论：已成功上传的头像文件和 OSS Object 永久保留，任何人都不能删除；替换、取消、解除引用和智能体停用只更新业务状态，不删除文件。  
状态：已确认。

### Q7：头像上传成功但智能体表单未保存时，临时文件如何处理？

为什么要问：本方案采用“上传文件”和“保存智能体引用”两个步骤。管理员可能上传后取消编辑、关闭页面或保存失败，如果没有明确处理方式，就会产生未绑定文件；既然文件永久保留，需要决定这些文件如何标记、是否可再次复用以及是否展示给管理员。

请选择：

- A. 文件永久保留并标记为“未绑定”，当前表单可继续使用；后续不提供独立文件清理功能（推荐）  
  最符合已确认的永久保留规则，数据可追溯，但会积累未绑定文件。

- B. 上传成功后自动绑定当前智能体草稿，取消编辑时保留草稿引用  
  便于继续编辑，但需要增加草稿状态和草稿头像读取逻辑。

- C. 上传成功后立即绑定当前智能体线上配置  
  能避免未绑定文件，但违反“头像来源保存后才生效”的已确认规则。

- D. 未保存的文件不登记 ManagedFile，只保留 OSS Object  
  可以减少数据库记录，但会产生无法追踪的永久 OSS 文件，不建议使用。

用户选择：A。  
结论：上传成功但未保存的文件永久保留，并标记为“未绑定”；当前表单可以继续使用该文件完成保存，不提供文件清理功能。  
状态：已确认。

### Q8：替换头像后，旧的专属头像文件是否允许再次复用？

为什么要问：已确认所有文件永久保留。如果旧文件只能永久留在 OSS 中却无法被业务再次找到，会形成不可管理的数据；如果直接展示所有医院历史文件，又可能造成跨智能体误用。需要明确历史头像的展示范围和复用方式。

请选择：

- A. 仅展示当前智能体自己的头像历史，允许重新选择；未绑定文件不进入默认列表（推荐）  
  旧头像可在同一智能体编辑时恢复，其他智能体不能直接复用，未绑定文件仍永久保留但不干扰日常操作。

- B. 同医院所有智能体的专属头像都可以互相复用  
  能减少重复上传，但需要额外处理头像授权、误用和跨科室展示问题。

- C. 旧头像永久保留但不允许任何界面再次选择  
  实现简单，但历史文件无法产生业务价值，只能作为审计留存。

- D. 所有已上传和未绑定文件都进入头像选择列表  
  复用范围最大，但列表会持续膨胀，且容易误选其他智能体或医院的头像。

用户选择：A。  
结论：仅当前智能体可以查看和复用自己的头像历史；未绑定文件不进入默认列表；其他智能体不能直接复用。  
状态：已确认。

### Q9：智能体停用或删除后，头像文件和历史记录如何处理？

为什么要问：头像文件已确定永久保留，智能体状态变化不能通过删除 OSS 文件来处理。仍需明确停用/删除后的当前头像是否继续可访问、历史头像是否继续展示，以及未来重新启用时是否恢复原配置。

请选择：

- A. 文件永久保留；停用后不再作为线上头像展示，但保留智能体头像历史；重新启用时恢复最后一次有效头像配置（推荐）  
  既满足永久留存，也避免停用智能体继续出现在患者端或医生工作台线上展示中。

- B. 停用后仍继续展示最后一次头像，但不允许编辑
  历史页面一致，但可能让患者误以为智能体仍可用。

- C. 停用或删除后头像历史对后台也隐藏，只保留 OSS 和数据库记录
  外部不可见，但重新启用和问题追溯时无法直接恢复。

- D. 停用或删除后允许其他智能体使用其头像历史
  能提高文件复用率，但违反“其他智能体不能直接复用”的已确认规则。

用户选择：A。  
结论：头像文件永久保留；智能体停用后不作为线上头像展示，但保留头像历史；重新启用时恢复最后一次有效头像配置。  
状态：已确认。

### Q10：前台或后台读取智能体头像失败时，如何降级显示？

为什么要问：OSS 网络异常、临时 URL 过期、文件记录异常或图片加载失败时，不能让智能体列表出现破图，也不能阻塞患者咨询和医生工作台。需要统一降级顺序，保证不同客户端显示一致。

请选择：

- A. 优先使用系统统一 AI 默认头像；同时保留智能体名称首字作为最终兜底，不阻塞页面和对话（推荐）  
  头像加载失败只影响图片，不影响智能体名称、医生信息、会话和在线咨询。

- B. 头像加载失败时回退到关联医生头像
  可以保持人物形象，但 custom 专属头像失败时可能误导用户。

- C. 头像加载失败时隐藏整个智能体卡片
  可以避免展示不完整数据，但会影响智能体发现和患者咨询入口。

- D. 头像加载失败时持续重试，直到图片成功
  可能造成请求循环、页面卡顿和弱网环境下的性能问题。

用户选择：A。  
结论：头像加载失败时优先使用系统统一 AI 默认头像，最终使用智能体名称首字；头像失败不阻塞页面和对话。  
状态：已确认。

### Q11：头像上传接口和智能体保存接口如何组合？

为什么要问：头像上传到 OSS 与智能体更新是两个可能失败的动作。需要明确接口返回 file_id、智能体保存时如何引用、是否携带 agent version，以及如何记录上传成功但保存失败的文件，避免客户端直接提交 OSS 路径或出现线上头像半更新状态。

请选择：

- A. 两阶段接口：先上传并返回 file_id，再通过智能体保存接口提交 avatar_source、avatar_file_id 和 version（推荐）  
  上传结果可复用；智能体只有保存成功后才切换头像，继续沿用现有智能体版本并发控制。

- B. 一个 multipart 接口同时上传图片并创建/更新智能体
  表单体验集中，但需要重构现有智能体更新接口和事务边界。

- C. 客户端直接提交 OSS object_key，服务端只保存路径
  接口简单，但绕过 ManagedFile 归属、文件校验和业务关联，不符合当前文件管理设计。

- D. 上传后异步生成头像，智能体先保存临时状态
  适合大文件，但头像仅 5 MB 且需要立即预览，会增加状态和回调复杂度。

用户选择：A。  
结论：采用两阶段接口；先上传并返回 file_id，再通过智能体保存接口提交 avatar_source、avatar_file_id 和 version。智能体只有保存成功后才切换头像。  
状态：已确认。

### Q12：公共头像上传接口的权限和文件安全校验如何设置？

为什么要问：公共上传能力属于 SparkService 基础能力，但智能体头像仍是医院业务数据。必须避免未登录用户、其他医院管理员或普通患者利用接口写入任意 OSS 文件，也要防止伪造图片、超大文件和恶意内容进入存储。

请选择：

- A. 仅允许已登录且属于当前医院的后台工作人员调用；服务端校验医院上下文、业务用途、文件类型、大小、真实图片内容和像素，并记录审计日志（推荐）  
  公共表示服务能力可复用，不表示接口匿名公开；具体角色范围沿用医院后台现有管理权限。

- B. 任何登录用户都可以调用，保存智能体时再校验
  上传入口开放更大，但会产生大量无法绑定的文件和跨医院上传风险。

- C. 使用公开上传 URL，不要求登录，只依赖随机 object_key
  接入简单，但无法建立医院责任边界，不适用于医疗后台。

- D. 仅允许系统超级管理员上传，医生和医院管理员不能使用
  安全边界严格，但无法满足医院后台日常维护智能体的需求。

用户选择：C。  
结论：公共上传 URL 不要求登录，仅依赖服务端生成的随机 object_key；SparkService 仍负责图片校验、WebP 转换和 OSS 上传，OSS 密钥不下发客户端。接口扩展为受 MIME 和目录约束的图片/视频上传能力，不开放任意文件上传。  
状态：已确认。

### Q13：公开头像上传 URL 的业务范围如何限制？

为什么要问：已经允许公开调用上传 URL，如果接口支持任意文件或任意 Object Key，可能被滥用为公共文件中转站。必须固定上传用途、路径、输入类型和返回结果，才能在不登录的情况下控制风险。

请选择：

- A. 只提供头像专用上传接口；固定处理图片并固定写入 avatar 路径，不能传业务类型、Bucket 或 object_key（推荐）  
  调用方只提交头像文件和裁剪参数，服务端自动生成完整路径和 ManagedFile 记录。

- B. 提供通用公开文件上传接口，由调用方传入 business_type 和 object_key
  复用范围大，但会放大任意文件上传、路径穿越和跨业务写入风险。

- C. 公开接口允许上传图片和视频，服务端按 MIME 自动选择目录
  便于扩展媒体能力，但超出当前头像需求并增加内容安全成本。

- D. 公开接口允许调用方指定 zhaodkdream 下的任意子目录
  灵活性高，但会破坏医院头像目录约束和后续权限治理。

用户选择：C。  
结论：公开上传接口支持图片和视频，服务端根据真实 MIME 自动选择 image 或 video 目录；智能体头像仍固定使用 avatar 目录和 WebP 专用处理。该扩展随后由第 14 问收敛，当前演示版本最终只接受图片。  
状态：已确认。

### Q14：公开接口中的视频支持规则如何设置？

为什么要问：选择支持视频后，原有 5 MB、最长边 2048 px 和 WebP 规则只适用于智能体头像，不能直接套用到视频。必须明确视频格式、大小、时长和是否转码，否则接口容易被大文件滥用并造成 OSS 高额存储与带宽成本。

请选择：

- A. 首版只支持 MP4（H.264/AAC），单个视频不超过 50 MB、时长不超过 60 秒；服务端只做格式校验和原文件保存，不自动转码（推荐）  
  规则清晰、实现成本可控；视频对象写入 video 目录，后续再扩展转码和多清晰度。

- B. 支持 MP4、MOV、AVI、MKV；单个不超过 500 MB、不限制时长
  兼容性较好，但存储、解析、播放和安全风险明显增加。

- C. 支持常见视频格式；上传后服务端异步转码为 MP4，并生成封面和多清晰度版本
  播放体验更好，但需要任务队列、转码服务、失败重试和额外 OSS 文件。

- D. 公共接口只接受图片，视频需求暂不落地
  可以控制演示范围，视频能力后续单独设计。

用户选择：D。  
结论：公共上传接口当前只接受图片；视频需求暂不落地，不进入当前 MIME 白名单、OSS 目录和 ManagedFile 业务流程。  
状态：已确认。

### Q15：图片预览、缩略图和缓存刷新如何处理？

为什么要问：头像上传成功后会出现在后台列表、智能体详情、医生工作台和客户端。如果直接使用原图，加载成本较高；如果使用长期缓存，替换头像后可能继续显示旧图片。需要统一预览地址、缩略图和刷新策略。

请选择：

- A. 服务端保留原始生成的 1024×1024 WebP，并返回带版本标识的 avatar_url；前端按展示尺寸使用 OSS 图片处理参数，头像保存成功后刷新 URL（推荐）  
  原文件永久保留，展示端按需缩放；通过文件 ID、版本或新 Object Key 避免旧头像缓存污染。

- B. 每次页面加载都请求原始 1024×1024 WebP，不做缩略图和缓存
  实现简单，但会增加带宽和页面加载成本。

- C. 服务端为每个头像生成多份固定缩略图，并由客户端分别缓存
  加载更快，但会增加永久保留的 OSS 文件数量和维护复杂度。

- D. 使用不带版本的固定 URL，依靠客户端强制清缓存
  地址稳定，但不同客户端和 CDN 可能继续展示旧头像。

用户选择：A。  
结论：服务端保留 1024×1024 WebP，并返回带版本标识的 avatar_url；前端按展示尺寸使用 OSS 图片处理参数，头像保存成功后刷新 URL。  
状态：已确认。

### Q16：历史会话中的智能体头像如何展示？

为什么要问：智能体头像可能在患者咨询期间发生替换或医生头像发生变化。如果历史会话始终读取当前头像，旧消息的视觉身份会被改写；如果所有消息都永久快照，又会增加消息数据和文件引用维护成本。

请选择：

- A. 历史会话消息使用发送时的头像快照；会话列表和当前智能体头部使用最新头像（推荐）  
  历史消息保持当时的身份可解释性，当前入口继续反映最新智能体配置。

- B. 历史会话和当前入口全部使用最新头像
  数据结构简单，但头像替换后历史消息的身份展示会变化。

- C. 历史会话不展示头像，只展示智能体名称
  可以避免快照问题，但会降低消息流中的身份辨识度。

- D. 每条历史消息都重新请求当时的 OSS 原图
  历史还原精确，但请求、缓存和永久文件引用复杂度较高。

用户选择：C。  
结论：历史会话消息不展示头像，只展示智能体名称；当前智能体头部和会话列表使用最新有效头像。  
状态：已确认。

### Q17：后台智能体头像历史列表展示哪些文件？

为什么要问：已确认当前智能体可以恢复自己的历史头像，但未绑定文件不进入默认列表。还需要明确历史列表是否包含当前头像、已替换头像和未绑定文件，以及管理员通过哪些信息判断要恢复哪一张。

请选择：

- A. 展示当前智能体曾经成功绑定过的专属头像；标记当前使用项，显示预览、上传时间、来源状态和恢复操作；未绑定文件不展示（推荐）  
  历史列表只保留可用于该智能体恢复的文件，避免未绑定文件无限出现在日常选择界面。

- B. 只展示当前正在使用的头像，不展示历史
  页面最简单，但无法实现已确认的历史头像恢复。

- C. 展示当前智能体所有上传过的文件，包括未绑定文件
  可追溯性更强，但会使列表膨胀，并增加误选临时文件的风险。

- D. 展示同医院所有智能体的头像历史
  便于集中管理，但违反其他智能体不能直接复用的边界。

用户选择：B。  
结论：后台只展示当前正在使用的头像，不展示头像历史列表；头像历史文件仍按永久保留规则留存，但本期不提供恢复入口。该结论覆盖第 8 问中关于后台可恢复历史头像的展示约定。  
状态：已确认。

### Q18：头像来源和文件变更是否需要保留审计记录？

为什么要问：头像文件永久保留且后台不展示历史列表，后续只能通过审计记录解释某个头像何时上传、何时被哪个智能体引用或解除引用。还需要区分上传事件和智能体配置变更，避免只保留最终状态而无法追踪过程。

请选择：

- A. 保留上传和智能体头像配置变更审计；记录操作时间、操作人（如有）、医院、智能体、旧值、新值、file_id 和 request_id；不记录图片正文或 OSS 密钥（推荐）  
  即使公开上传没有登录人，也保留 request_id 和可用的来源元数据。

- B. 只保留最终头像配置，不保留上传和切换过程
  数据简单，但无法解释历史文件和线上头像变更。

- C. 只记录 OSS 上传日志，不记录智能体何时引用或解除引用
  能追踪文件创建，但无法还原业务配置变化。

- D. 不保留任何头像审计记录
  存储最少，但不适合医院后台和永久保留文件的方案。

用户选择：D。  
结论：不保留头像上传、头像来源切换和文件引用变更的审计记录；上传成功结果可以直接用于后续头像使用，不增加额外审计确认步骤。  
状态：已确认。

### Q19：“上传就可以直接使用”是否表示上传成功后立即成为线上智能体头像？

为什么要问：此前已确认头像来源切换保存后才生效、上传和智能体保存是两阶段。若上传成功立即生效，取消编辑或保存失败也会改变线上头像；若仍需点击保存，上传结果只能直接用于当前表单预览和保存，线上生效边界更清晰。

请选择：

- A. 上传成功后立即成为线上智能体头像，不再等待智能体表单保存（推荐）  
  上传成功即更新当前智能体头像；取消编辑只取消其他字段，不能回滚已经生效的头像。

- B. 上传成功后立即可在当前表单使用，但仍需点击“保存智能体”才更新线上头像  
  上传不需要审计或额外确认，但继续保留智能体配置的保存边界。

- C. 上传成功后只作为临时预览，必须再次确认头像后才能使用  
  需要额外确认步骤，与“上传就可以直接使用”不一致。

- D. 上传成功后直接替换医生头像，所有复用医生头像的智能体同步更新
  会改变医生头像业务，超出本工单范围。

用户选择：A。  
结论：上传专属头像成功后立即成为线上智能体头像，不再等待智能体表单保存；取消编辑不能回滚已经生效的头像。  
状态：已确认。

### Q20：从专属头像切回复用医生头像时，是否也立即生效？

为什么要问：上传专属头像已经确定为上传成功立即生效，但切回复用医生头像不涉及新的图片上传，而是清除智能体专属头像引用并恢复医生头像。两种动作的生效时机需要统一，否则表单操作会出现难以预期的线上状态。

请选择：

- A. 选择“复用医生头像”后立即生效，线上头像立即切换为当前医生头像（推荐）  
  与上传专属头像立即生效保持一致；切换后不再等待智能体表单保存，旧专属文件永久保留。

- B. 选择后只更新表单预览，点击“保存智能体”后才生效
  可以统一表单保存边界，但与上传专属头像立即生效的规则不同。

- C. 选择复用医生头像时弹出确认，确认后立即生效
  线上状态明确，但会增加一次操作步骤。

- D. 只能通过重新编辑并上传新头像切换，不能复用医生头像
  会取消已确认的医生头像复用能力。

用户选择：A。  
结论：选择“复用医生头像”后立即生效，线上头像立即切换为当前医生头像；旧专属头像文件永久保留。  
状态：已确认。

### Q21：选择复用医生头像时，如果关联医生没有头像，线上如何展示？

为什么要问：复用医生头像是动态引用。医生头像为空时，如果立即清空智能体头像，患者端和后台可能出现破图或空白；需要明确切换后的可见结果，同时保持“复用医生头像”来源状态的一致性。

请选择：

- A. 保持 avatar_source=doctor，使用统一 AI 默认头像，默认头像失败时使用智能体名称首字（推荐）  
  来源语义保持不变；医生以后补充头像后，智能体自动展示医生新头像。

- B. 没有医生头像时保留原专属头像继续展示
  展示稳定，但会让“复用医生头像”实际显示专属头像，来源语义不一致。

- C. 没有医生头像时禁止切换，继续使用原专属头像
  可以避免空头像，但无法立即完成管理员选择的来源切换。

- D. 没有医生头像时隐藏智能体头像区域
  页面可能出现布局跳动，也会降低智能体身份辨识度。

用户选择：A。  
结论：保持 avatar_source=doctor；关联医生没有头像时使用统一 AI 默认头像，默认头像失败时使用智能体名称首字。  
状态：已确认。

### Q22：头像来源变化后，客户端缓存如何更新？

为什么要问：专属头像上传和切回复用医生头像都已确定立即生效，但后台列表、医生工作台、患者端和 iOS 可能持有旧的 avatar_url 缓存。需要明确是否需要实时推送、如何避免旧图继续展示，以及弱网下的刷新方式。

请选择：

- A. 服务端返回新的带版本 avatar_url；各客户端在下一次请求或页面刷新时读取并更新本地缓存，不新增实时推送（推荐）  
  实现稳定，依靠新 Object Key 或版本参数避免旧图缓存污染。

- B. 头像变化后通过 WebSocket 实时推送到所有在线客户端
  更新及时，但需要新增事件契约、订阅范围和断线补偿。

- C. 客户端固定等待缓存 TTL 到期后再更新
  实现简单，但头像变化后可能长时间显示旧图。

- D. 头像变化后要求管理员手动刷新所有客户端
  运维成本高，不适合患者端和多设备场景。

用户选择：A。  
结论：服务端在头像来源或实际文件变化后返回新的带版本 avatar_url；后台、医生工作台和患者端在下一次接口请求或页面刷新时更新内存与图片缓存，不新增 WebSocket 实时推送。  
状态：已确认，问答结束。

## 8. 最终规则与覆盖关系

本节是开发实现时的最高优先级规则。前文逐题记录用于保留决策过程；若早期答案与本节冲突，以本节为准。

### 8.1 最终业务规则

| 场景 | 最终规则 |
| --- | --- |
| 新建智能体默认头像 | 默认 avatar_source=doctor，动态复用所选医生头像 |
| 新建时上传专属头像 | 先上传并取得 file_id；创建智能体时一并写入 custom 引用。智能体创建前不存在“线上头像” |
| 编辑已有智能体上传专属头像 | 上传成功后立即调用头像切换接口；两步都成功才向用户显示“头像已更新” |
| 编辑已有智能体切回复用医生头像 | 立即调用头像切换接口，不等待其他表单字段保存 |
| 取消编辑弹窗 | 仅放弃名称、简介等未保存字段；已成功切换的头像不回滚 |
| 上传成功、头像切换失败 | 新文件永久保留为未绑定文件；线上继续展示旧头像 |
| 医生无头像 | 保持 avatar_source=doctor，显示统一 AI 默认头像，再以名称首字兜底 |
| 智能体停用 | 患者侧和医生服务入口不展示；后台详情仍可预览当前头像配置 |
| 智能体重新启用 | 恢复停用前最后一次有效来源和引用 |
| 历史会话消息 | 不展示头像，只显示智能体名称 |
| 历史头像 | 文件永久保留；本期后台不提供历史列表和恢复入口 |
| 删除文件 | 智能体头像文件包括未绑定文件均禁止删除 |
| 审计 | 不创建头像业务审计记录；保留基础设施必要的访问日志和错误日志 |
| 客户端刷新 | 使用带版本 avatar_url；下次请求或页面刷新更新，不做实时推送 |

### 8.2 被覆盖的早期结论

1. Q2 的“保存后才生效”被 Q19、Q20 覆盖。已有智能体的上传专属头像和切回复用医生头像均立即生效。
2. Q8 的“后台可恢复历史头像”被 Q17 覆盖。本期不展示历史头像列表，也不提供恢复入口。
3. Q11 的“两阶段后由整张智能体表单保存生效”被 Q19 细化。技术上仍为两阶段，但编辑已有智能体时前端自动执行第二阶段。
4. Q15 的“保存成功后刷新”应解释为“头像操作成功后刷新”，不要求保存名称、简介、AI 配置等其他字段。
5. Q12 的“公开上传”只适用于接收图片二进制并生成 ManagedFile，不赋予匿名调用者修改 ClinicalAgentProfile 的能力。

## 9. 业务流程

### 9.1 新建智能体并复用医生头像

~~~text
管理员打开“新建智能体”
  → 选择医生
  → 表单默认 avatar_source=doctor
  → 前端展示医生当前头像
  → 医生无头像则展示统一 AI 默认头像
  → 管理员填写智能体与 AI 配置
  → POST 创建智能体
  → 服务端创建 AIScenarioModelBinding
  → 服务端创建 ClinicalAgentProfile
  → avatar_source=doctor，avatar_file=null
  → 返回带版本 avatar_url
  → 列表刷新并展示新智能体
~~~

关键边界：

- 新建页面尚无 agent_id，因此“立即切换线上头像”不适用。
- 医生更换头像后，不批量更新 ClinicalAgentProfile；下一次读取智能体时动态解析医生最新头像。
- 医生无头像不阻止智能体创建、发布或对话。

### 9.2 新建智能体并上传专属头像

~~~text
管理员选择“上传专属头像”
  → 浏览器预检格式和 5 MB 上限
  → 打开 1:1 裁剪器
  → 提交原图、归一化裁剪参数、hospital_id
  → SparkService 验证真实图片
  → 纠正 EXIF 方向、裁剪、转为 1024×1024 WebP
  → 上传 OSS
  → 创建 ManagedFile
  → 建立 clinical_agent_avatar_upload 业务关系，business_id 暂为空
  → 返回 file_id 与 avatar_url
  → 前端仅显示预览
  → 管理员提交新建智能体
  → POST 创建请求携带 avatar_source=custom、avatar_file_id、其他字段
  → 同一数据库事务创建 AIScenarioModelBinding、ClinicalAgentProfile 并绑定文件
  → 返回智能体完整数据
~~~

失败处理：

- 图片处理或 OSS 上传失败：不创建 ManagedFile，不允许提交 custom。
- OSS 成功但 ManagedFile 创建失败：记录基础设施错误并返回失败；Object 按永久保留规则不删除。
- 文件成功、创建智能体失败：文件保留为未绑定，不能删除，也不进入历史头像 UI。
- 创建智能体成功：更新业务关系的 business_id 为 agent_id；不复制文件。

### 9.3 编辑已有智能体并上传专属头像

~~~text
管理员打开编辑表单
  → 读取 agent.version 和当前头像
  → 选择图片并完成裁剪
  → 调用公开图片上传接口
  → 获得 file_id、avatar_url
  → 前端立即调用受保护的“设置智能体头像”接口
       agent_id
       avatar_source=custom
       avatar_file_id=file_id
       version=当前 agent.version
  → 服务端锁定智能体并校验版本
  → 校验 ManagedFile 为合法头像文件
  → 更新 avatar_source、avatar_file、version
  → 不改变 publication_status
  → 返回新 version 和新 avatar_url
  → 前端更新本地 detail.version 与头像
  → 显示“头像已更新”
~~~

“上传成功”的产品口径：

- UI 只有在“OSS/ManagedFile 阶段”和“智能体头像引用阶段”都成功后，才显示头像更新成功。
- 第一阶段成功、第二阶段失败时，提示“图片已上传，但头像切换失败；当前头像未变化”。
- 此时文件永久保留为未绑定文件。

### 9.4 编辑已有智能体并切回复用医生头像

~~~text
管理员选择“复用医生头像”
  → 前端立即调用设置头像接口
       avatar_source=doctor
       avatar_file_id=null
       version=当前 agent.version
  → 服务端锁定智能体并校验版本
  → 清空 avatar_file
  → avatar_source=doctor
  → agent.version + 1
  → 不删除旧 ManagedFile 和 OSS Object
  → 返回医生头像或默认 AI 头像的版本化 URL
  → 前端立即替换预览并更新 version
~~~

### 9.5 同一编辑弹窗继续保存其他字段

头像立即更新会增加 agent.version。前端必须把头像接口响应中的新 version 写回当前表单状态；否则随后保存名称或 AI 配置会错误触发 AGENT_VERSION_CONFLICT。

~~~text
打开表单 version=7
  → 上传并切换头像成功
  → 响应 version=8
  → 前端 detail.version 更新为 8
  → 管理员修改简介并保存
  → PATCH 智能体携带 version=8
~~~

如果头像更新后，其他用户又修改了智能体，常规保存仍应返回版本冲突并要求重新加载，不能自动覆盖。

### 9.6 停用、启用与头像

- 停用只改变 publication_status，不清空 avatar_source 或 avatar_file。
- 患者公开目录不会返回已停用智能体；即使某接口返回内部数据，也不应把停用智能体作为在线服务头像展示。
- 后台详情使用 include_internal=true，可以继续预览当前头像。
- 重新发布或启用后继续按原 avatar_source 解析，不创建新文件。

## 10. 数据模型落地

### 10.1 ClinicalAgentProfile

在 hospital_care/models/agent_profiles.py 的 ClinicalAgentProfile 中增加：

~~~python
class AvatarSource(models.TextChoices):
    DOCTOR = "doctor", "复用医生头像"
    CUSTOM = "custom", "专属头像"

avatar_source = models.CharField(
    max_length=16,
    choices=AvatarSource.choices,
    default=AvatarSource.DOCTOR,
)
avatar_file = models.ForeignKey(
    "file_manager.ManagedFile",
    null=True,
    blank=True,
    related_name="clinical_agent_avatars",
    on_delete=models.PROTECT,
)
~~~

模型约束：

~~~python
models.CheckConstraint(
    condition=(
        models.Q(avatar_source="doctor", avatar_file__isnull=True)
        | models.Q(avatar_source="custom", avatar_file__isnull=False)
    ),
    name="chk_agent_avatar_source_file",
)
~~~

说明：

- default=doctor 保证旧数据迁移后继续显示医生头像。
- on_delete=PROTECT 与永久保留要求一致。
- 不在模型中保存 avatar_url；URL 是读取时由服务端解析的派生字段。
- 不新增二进制图片表。
- 不新增头像审计表。

### 10.2 ManagedFile 与业务关系

复用现有 file_manager.ManagedFile 保存 OSS 元数据，复用 ManagedFileBusinessRelation 表达业务归属。

建议固定：

~~~text
business_type = clinical_agent_avatar_upload
business_id   = ""          上传后尚未绑定
business_id   = agent_uuid  曾经或当前归属该智能体
~~~

当前头像由 ClinicalAgentProfile.avatar_file 唯一决定。业务关系仅表达“该文件属于哪个智能体的头像资产集合”，不是当前头像指针。

永久保留实现：

- ManagedFileDeleteView 在删除前检查 business_type。
- clinical_agent_avatar_upload 类型一律返回 FILE_RETENTION_PROTECTED。
- 旧头像解除当前引用后仍保留 business relation。
- 未绑定头像 business_id 为空，但 business_type 不为空，因此同样禁止删除。
- 不调用 ManagedFile.soft_delete。
- 不向 OSS 发 DeleteObject。

### 10.3 文件技术所有者

ManagedFile.user 当前必填，而公开上传接口可能没有 request.user。实施时需要明确技术账号：

- 优先使用 Hospital.knowledge_service_user 作为演示期医院服务账号承载文件。
- 若该字段为空，上传接口返回 HOSPITAL_SERVICE_USER_REQUIRED，不允许创建无 owner 的 ManagedFile。
- 不使用 AnonymousUser 写入外键。
- 后续若知识与资产账号需要拆分，再单独新增 hospital_asset_service_user；本工单不重复创建文件模型。

这是技术所有权，不改变“头像业务上归医院”的结论。

### 10.4 数据迁移

新增迁移建议编号为 hospital_care/migrations/0007_clinical_agent_avatar.py，实际编号以开发时迁移队列为准。

迁移步骤：

1. 新增 avatar_source，默认 doctor。
2. 新增 avatar_file，可空、PROTECT。
3. 为所有历史 ClinicalAgentProfile 写入 doctor/null。
4. 增加数据库 CheckConstraint。
5. 不复制 DoctorProfile.avatar_file。
6. 不生成 OSS 文件。
7. 验证历史智能体 presenter 输出与迁移前一致。

回滚只允许回滚 schema，不删除任何已上传 Object 或 ManagedFile。

## 11. OSS 与图片处理落地

### 11.1 依赖

当前 requirements.txt 已包含 STS SDK，但没有 OSS V2 上传 SDK和 Pillow。实现前补充并锁定兼容版本：

~~~text
alibabacloud-oss-v2
Pillow
~~~

开发提交时必须根据当前 Python 版本选择明确版本范围，并在测试环境验证 WebP 编解码支持。

### 11.2 配置

继续读取 SparkService/settings.py 已有配置：

~~~text
ALIYUN_ACCESS_KEY_ID
ALIYUN_ACCESS_KEY_SECRET
ALIYUN_OSS_BUCKET
ALIYUN_OSS_REGION
ALIYUN_OSS_ENDPOINT
~~~

不得：

- 在代码、文档、日志或 API 响应中写入真实密钥。
- 将长期 AccessKey 返回浏览器。
- 允许客户端提交 bucket、endpoint 或 object_key。
- 使用原始文件名构造对象路径。

### 11.3 Object Key

~~~text
zhaodkdream/spark_service/hospital/avatar/{hospital_id}/{uuid}.webp
~~~

每次上传生成新 UUID，不覆盖旧对象。医院 ID 由服务端校验存在后使用；UUID 由服务端生成。

### 11.4 裁剪参数

前端传归一化坐标，避免浏览器预览尺寸和原图像素不一致：

~~~json
{
  "crop_x": 0.125,
  "crop_y": 0.000,
  "crop_size": 0.750
}
~~~

约束：

- crop_x、crop_y、crop_size 均在 0 到 1 之间。
- crop_size 必须大于 0。
- crop_x + crop_size 不得大于 1。
- crop_y + crop_size 不得大于 1。
- 坐标基于完成 EXIF 方向纠正后的图片。
- 服务端将归一化值换算为整数像素并再次检查边界。

### 11.5 图片处理顺序

1. 限制 HTTP 请求体，拒绝超过 5 MB 的文件。
2. 读取魔数并用 Pillow 解码，不能只信任扩展名和 Content-Type。
3. 调用 verify 或等价方式检查文件完整性。
4. 重新打开图片，执行 EXIF transpose。
5. 拒绝动画图片，只接受单帧。
6. 校验真实宽高和最长边不超过 2048。
7. 转为 RGB；透明像素使用统一背景色合成。
8. 按归一化坐标裁剪正方形。
9. 使用高质量缩放生成 1024×1024。
10. 编码为 WebP，并移除 EXIF、ICC、定位等元数据。
11. 计算 MD5 或 SHA-256。
12. 上传 OSS，Content-Type 固定 image/webp。
13. 创建 ManagedFile。

### 11.6 公共上传内部服务示例

建议新增 file_manager/services/oss_object_service.py，提供 bytes、流和本地路径等内部入口。HTTP 层只开放图片流，禁止公开任意本地路径和任意网络 URL。

~~~python
from dataclasses import dataclass
from io import BytesIO

import alibabacloud_oss_v2 as oss
from django.conf import settings


@dataclass(frozen=True)
class PutObjectResult:
    object_key: str
    etag: str
    request_id: str
    version_id: str


def put_bytes(*, object_key: str, content: bytes, content_type: str) -> PutObjectResult:
    provider = oss.credentials.EnvironmentVariableCredentialsProvider()
    config = oss.config.load_default()
    config.credentials_provider = provider
    config.region = settings.ALIYUN_OSS_REGION
    if settings.ALIYUN_OSS_ENDPOINT:
        config.endpoint = settings.ALIYUN_OSS_ENDPOINT
    client = oss.Client(config)
    result = client.put_object(
        oss.PutObjectRequest(
            bucket=settings.ALIYUN_OSS_BUCKET,
            key=object_key,
            body=BytesIO(content),
            content_type=content_type,
            forbid_overwrite=True,
        )
    )
    return PutObjectResult(
        object_key=object_key,
        etag=result.etag or "",
        request_id=result.request_id or "",
        version_id=result.version_id or "",
    )
~~~

注：OSS V2 SDK 的最终参数名需以项目实际安装版本为准，开发时必须用测试 Bucket 做一次集成验证。

### 11.7 图片处理示例

建议新增 file_manager/services/image_processing.py：

~~~python
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError


def build_agent_avatar(uploaded_file, *, crop_x: float, crop_y: float, crop_size: float) -> bytes:
    if uploaded_file.size > 5 * 1024 * 1024:
        raise ValueError("AVATAR_FILE_TOO_LARGE")

    raw = uploaded_file.read()
    try:
        with Image.open(BytesIO(raw)) as probe:
            probe.verify()
        with Image.open(BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source)
            if getattr(image, "n_frames", 1) != 1:
                raise ValueError("AVATAR_ANIMATED_NOT_ALLOWED")
            if max(image.size) > 2048:
                raise ValueError("AVATAR_DIMENSION_EXCEEDED")
            width, height = image.size
            left = round(crop_x * width)
            top = round(crop_y * height)
            size = round(crop_size * min(width, height))
            if size <= 0 or left < 0 or top < 0:
                raise ValueError("AVATAR_CROP_INVALID")
            if left + size > width or top + size > height:
                raise ValueError("AVATAR_CROP_INVALID")
            cropped = image.crop((left, top, left + size, top + size)).convert("RGB")
            output = cropped.resize((1024, 1024), Image.Resampling.LANCZOS)
            buffer = BytesIO()
            output.save(buffer, format="WEBP", quality=88, method=6)
            return buffer.getvalue()
    except UnidentifiedImageError as exc:
        raise ValueError("AVATAR_FORMAT_INVALID") from exc
~~~

## 12. API 契约

### 12.1 公开图片上传接口

~~~text
POST /api/v1/public/uploads/images/
Content-Type: multipart/form-data
Authentication: 不要求登录（已确认的演示规则）
~~~

请求字段：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| file | binary | 是 | JPG、JPEG、PNG、WEBP，最大 5 MB |
| purpose | string | 是 | 固定 clinical_agent_avatar |
| hospital_id | UUID | 是 | 用于路径和服务账号归属 |
| crop_x | decimal | 是 | 归一化左边界 |
| crop_y | decimal | 是 | 归一化上边界 |
| crop_size | decimal | 是 | 归一化正方形边长 |

成功响应：

~~~json
{
  "code": 0,
  "msg": "created",
  "data": {
    "file_id": 3821,
    "file_uuid": "2d7d6ad7-2740-46bc-9fc7-9bfed97f9453",
    "mime_type": "image/webp",
    "width": 1024,
    "height": 1024,
    "file_size": 84612,
    "avatar_url": "https://example-oss/.../2d7d6ad7.webp?v=2d7d6ad7",
    "binding_state": "unbound"
  }
}
~~~

公开接口保护措施：

- 固定只接受 purpose=clinical_agent_avatar。
- 单 IP 限流、并发限制、请求体上限和超时。
- 不能传 object_key、bucket、endpoint、business_type、business_id 或 user_id。
- 服务端生成随机 UUID。
- 返回值不包含 OSS 密钥。
- 公开接口不接收 agent_id，也不更新智能体。
- 该接口存在匿名存储滥用风险；这是已确认演示策略，生产上线前必须重新评审。

### 12.2 已有智能体立即设置头像

建议新增：

~~~text
PATCH /api/admin/v1/hospital-care/agents/{agent_id}/avatar/
Authentication: 后台登录
Permission: api:hospital_care:agent:update
Idempotency-Key: 必填
~~~

设置专属头像：

~~~json
{
  "avatar_source": "custom",
  "avatar_file_id": 3821,
  "version": 7
}
~~~

切回复用医生头像：

~~~json
{
  "avatar_source": "doctor",
  "avatar_file_id": null,
  "version": 8
}
~~~

响应：

~~~json
{
  "code": 0,
  "msg": "success",
  "data": {
    "id": "agent-uuid",
    "avatar_source": "custom",
    "avatar_file_id": 3821,
    "avatar_url": "https://example-oss/.../2d7d6ad7.webp?v=2d7d6ad7",
    "avatar_version": "custom:3821:2d7d6ad7",
    "version": 8
  }
}
~~~

服务约束：

- 使用 select_for_update 锁定 ClinicalAgentProfile。
- 校验 version，冲突返回 AGENT_VERSION_CONFLICT。
- custom 必须校验文件存在、未删除、MIME=image/webp、尺寸元数据符合头像规则、业务医院一致。
- doctor 必须清空 avatar_file。
- 只更新头像字段和 agent.version。
- 不将 published 改回 review，保证“立即成为线上头像”。
- 不写 hospital avatar audit；普通应用访问日志可以保留。
- 旧文件不删除、不软删除、不解除历史业务关系。

### 12.3 新建智能体接口扩展

现有 POST /api/admin/v1/hospital-care/hospitals/{hospital_id}/agents/ 增加：

~~~json
{
  "doctor_id": "doctor-uuid",
  "department_id": "department-uuid",
  "name": "开开医生智能体",
  "avatar_source": "custom",
  "avatar_file_id": 3821,
  "binding": {
    "model": "model-name"
  },
  "knowledge_bases": []
}
~~~

默认：

~~~text
avatar_source 缺省 → doctor
avatar_file_id 缺省 → null
~~~

创建事务中完成头像引用校验和 business_id 绑定。创建失败时不删除文件。

### 12.4 常规智能体更新接口

现有 PATCH /api/admin/v1/hospital-care/agents/{agent_id}/ 继续处理名称、科室、简介、AI 绑定和知识库。为避免两套头像写入路径产生不同状态：

- 本期不建议常规 PATCH 再接受头像字段。
- 头像只走专用 avatar 接口。
- 前端头像操作成功后，用响应 version 更新常规表单版本。

### 12.5 Presenter 输出

hospital_care/api/presenters.py 的 agent_public 统一增加：

~~~python
{
    "avatar_source": "doctor",
    "avatar_url": "https://...?...",
    "avatar_version": "doctor:123:uuid",
}
~~~

include_internal=true 时额外返回：

~~~python
{
    "avatar_file_id": 3821
}
~~~

公共患者接口不返回 avatar_file_id、object_key 或 ManagedFile 结构。

### 12.6 错误码

建议在 hospital_care/exceptions.py 增加：

| error_code | HTTP | 场景 | 前端文案 |
| --- | ---: | --- | --- |
| AVATAR_FILE_TOO_LARGE | 413 | 文件超过 5 MB | 图片不能超过 5 MB |
| AVATAR_FORMAT_INVALID | 400 | 真实格式不支持或损坏 | 请选择 JPG、PNG 或 WEBP 图片 |
| AVATAR_DIMENSION_EXCEEDED | 400 | 最长边超过 2048 | 图片尺寸不能超过 2048 像素 |
| AVATAR_CROP_INVALID | 400 | 裁剪参数越界 | 裁剪区域无效，请重新调整 |
| AVATAR_UPLOAD_FAILED | 503 | OSS 上传失败 | 头像上传失败，请稍后重试 |
| AVATAR_FILE_NOT_FOUND | 404 | file_id 不存在 | 上传文件不存在，请重新上传 |
| AVATAR_FILE_FORBIDDEN | 403 | 文件与医院/用途不符 | 该图片不能用于当前智能体 |
| AVATAR_SOURCE_INVALID | 400 | 来源与 file_id 组合错误 | 头像来源配置无效 |
| FILE_RETENTION_PROTECTED | 409 | 尝试删除永久头像 | 该头像文件为永久保留文件，不能删除 |
| HOSPITAL_SERVICE_USER_REQUIRED | 409 | 医院服务账号缺失 | 医院文件服务尚未配置 |

## 13. 服务端核心实现示例

### 13.1 头像解析器

建议新增 hospital_care/services/agent_avatar_service.py：

~~~python
from dataclasses import dataclass

from django.conf import settings

from file_manager.url_utils import managed_file_download_url


@dataclass(frozen=True)
class ResolvedAvatar:
    url: str
    version: str


def resolve_agent_avatar(agent) -> ResolvedAvatar:
    if agent.avatar_source == agent.AvatarSource.CUSTOM and agent.avatar_file_id:
        file = agent.avatar_file
        return ResolvedAvatar(
            url=managed_file_download_url(file),
            version="custom:{0}:{1}".format(file.id, file.file_uuid),
        )

    doctor_file = getattr(agent.doctor, "avatar_file", None)
    if doctor_file is not None:
        return ResolvedAvatar(
            url=managed_file_download_url(doctor_file),
            version="doctor:{0}:{1}".format(doctor_file.id, doctor_file.file_uuid),
        )

    return ResolvedAvatar(
        url=settings.CLINICAL_AGENT_DEFAULT_AVATAR_URL,
        version="default:{0}".format(settings.CLINICAL_AGENT_DEFAULT_AVATAR_VERSION),
    )
~~~

URL 输出层再安全附加 v 参数。不要把 avatar_version 直接当作未经编码的查询字符串。

### 13.2 立即切换服务

~~~python
from django.db import transaction

from hospital_care.exceptions import HospitalCareError
from hospital_care.models import ClinicalAgentProfile


@transaction.atomic
def set_agent_avatar(*, agent_id, avatar_source, avatar_file_id, version):
    agent = (
        ClinicalAgentProfile.objects.select_for_update()
        .select_related("hospital", "doctor__avatar_file", "avatar_file")
        .filter(pk=agent_id)
        .first()
    )
    if agent is None:
        raise HospitalCareError("AGENT_NOT_FOUND")
    if int(version) != agent.version:
        raise HospitalCareError(
            "AGENT_VERSION_CONFLICT",
            details={"version": agent.version},
        )

    if avatar_source == ClinicalAgentProfile.AvatarSource.DOCTOR:
        agent.avatar_source = avatar_source
        agent.avatar_file = None
    elif avatar_source == ClinicalAgentProfile.AvatarSource.CUSTOM:
        file = resolve_valid_agent_avatar_file(
            hospital=agent.hospital,
            file_id=avatar_file_id,
        )
        agent.avatar_source = avatar_source
        agent.avatar_file = file
        bind_avatar_file_to_agent(file=file, agent=agent)
    else:
        raise HospitalCareError("AVATAR_SOURCE_INVALID")

    agent.version += 1
    agent.save(update_fields=["avatar_source", "avatar_file", "version", "updated_at"])
    return agent
~~~

注意：此函数不调用 review 流程，不修改 publication_status，也不删除旧文件。

### 13.3 Presenter 示例

~~~python
def agent_public(agent, *, include_internal=False):
    resolved = resolve_agent_avatar(agent)
    payload = {
        "id": str(agent.id),
        "name": agent.name,
        "avatar_source": agent.avatar_source,
        "avatar_url": append_version(resolved.url, resolved.version),
        "avatar_version": resolved.version,
    }
    if include_internal:
        payload["avatar_file_id"] = agent.avatar_file_id
        payload["version"] = agent.version
    return payload
~~~

查询必须 select_related doctor__avatar_file 和 avatar_file，避免智能体列表产生 N+1 查询。

## 14. 后台前端落地

### 14.1 类型扩展

backoffice-web/src/api/modules/hospitalCare.ts：

~~~typescript
export type AgentAvatarSource = 'doctor' | 'custom';

export interface AgentRow {
  id: string;
  avatar_source: AgentAvatarSource;
  avatar_file_id?: number | null;
  avatar_url: string;
  avatar_version: string;
  version?: number;
}

export interface AgentAvatarUploadResult {
  file_id: number;
  file_uuid: string;
  avatar_url: string;
  width: 1024;
  height: 1024;
  mime_type: 'image/webp';
  binding_state: 'unbound';
}
~~~

DoctorRow 当前缺少 avatar_url 类型，而服务端 doctor_public 已返回该字段，应补充 avatar_url: string。

### 14.2 API 方法

~~~typescript
export function uploadAgentAvatar(payload: FormData) {
  return publicHttp.post('/api/v1/public/uploads/images/', payload);
}

export function setAgentAvatar(
  agentId: string,
  payload: {
    avatar_source: 'doctor' | 'custom';
    avatar_file_id: number | null;
    version: number;
  },
) {
  return http.patch(
    '/api/admin/v1/hospital-care/agents/' + agentId + '/avatar/',
    payload,
    withIdempotency(),
  );
}
~~~

公开上传客户端不得附带 OSS 凭证。设置头像继续使用后台登录态。

### 14.3 ClinicalAgentFormModal 状态

在现有患者侧展示区域的名称字段之前加入头像控件：

~~~text
患者侧展示

智能体头像
  [当前头像 96×96]
  (●) 复用医生头像
  ( ) 上传专属头像
      [选择图片] [重新上传]

名称
简介
问候语
服务边界
~~~

建议状态：

~~~typescript
const avatar = reactive({
  source: 'doctor' as AgentAvatarSource,
  url: '',
  fileId: null as number | null,
  uploading: false,
  applying: false,
  error: '',
});
~~~

已有智能体：

- 选择 doctor 后立即 setAgentAvatar。
- 上传图片后依次 uploadAgentAvatar、setAgentAvatar。
- 两步成功后更新 detail、avatar 和 detail.version。
- 头像操作中禁用两种来源切换，避免乱序响应。
- 不关闭整个编辑弹窗。
- 不提交名称、简介等其他草稿字段。

新建智能体：

- 选择 doctor 只改变本地表单。
- 上传后保存 file_id 到本地表单。
- 点击“创建”时把 avatar_source、avatar_file_id 放进 createAgent。
- 关闭新建弹窗后文件仍永久保留为未绑定。

### 14.4 版本冲突处理

头像接口返回 AGENT_VERSION_CONFLICT 时：

1. 不改变当前预览。
2. 提示“智能体已被更新，请加载最新内容后重试头像操作”。
3. 提供“加载最新内容”。
4. 不自动重试，因为自动重试可能覆盖他人刚设置的头像。
5. 已上传文件保留为未绑定。

### 14.5 图片加载降级

建议抽成 AgentAvatar 组件，后台与 chat-web 使用相同状态机：

~~~text
remote
  → agent.avatar_url 加载成功：展示图片
  → 加载失败：切换统一 AI 默认头像
default
  → 默认头像加载成功：展示默认头像
  → 加载失败：展示智能体名称首字
initial
  → 纯文本圆形头像，不再请求图片
~~~

组件收到不同 avatar_version 时重置失败状态并重新加载。

### 14.6 后台智能体列表

HospitalDetailView.vue 的智能体表格在“智能体名称”列增加当前头像：

- 只展示当前头像，不增加历史按钮。
- disabled 行仍可在后台展示其配置头像，旁边保留“已暂停”状态。
- 图片失败按统一降级处理。
- 搜索、科室筛选和分页不受影响。

## 15. chat-web 医生工作台落地

### 15.1 当前偏差

chat-web/components/doctor/CurrentAgentHeader.tsx 当前使用 agent.doctor.avatar_url，因此无法展示 custom 专属头像。

目标：

~~~tsx
<AgentAvatar
  src={agent.avatar_url}
  version={agent.avatar_version}
  name={agent.name}
/>
~~~

### 15.2 DTO

chat-web/types/hospital.ts 的 DoctorAgentDTO 增加：

~~~typescript
avatar_source: 'doctor' | 'custom';
avatar_url: string;
avatar_version: string;
~~~

医生工作台只读取 agent.avatar_url，不再自行选择 doctor.avatar_url。doctor.avatar_url 继续用于真人医生身份展示。

### 15.3 编辑弹窗

DoctorAgentForm 当前没有头像字段。若医生有 agent:update 权限，可复用与后台相同控件和接口；若医生工作台只允许维护公开资料，则头像区域只读并提示“请联系医院管理员修改”。权限必须以服务端结果为准，不能只靠隐藏按钮。

### 15.4 缓存

- CurrentAgentHeader 每次 getAgent 成功后替换内存对象。
- avatar_url 含版本，因此浏览器会请求新资源。
- 本期不订阅头像 WebSocket 事件。
- 页面不刷新时允许继续显示旧头像，符合第 22 问结论。
- 下一次进入患者工作台、刷新页面或重新请求 getAgent 时更新。

## 16. 患者端与会话边界

- 患者端名医列表、医生详情和会话首条医生智能体卡片使用 agent.avatar_url。
- 历史消息流不展示智能体头像，不修改历史消息模型。
- custom 图片变化不回写历史会话快照。
- avatar_source=doctor 时，患者端仍只看最终 avatar_url，不自行访问 doctor.avatar_url。
- 智能体下架时沿用现有下架处理，不因本地有头像缓存继续提供咨询入口。
- iOS 图片缓存键至少包含完整 avatar_url；由于 URL 带版本，变化后自然形成新键。
- 不要求 iOS 主动清空整个图片缓存。

## 17. 安全、稳定性与异常边界

### 17.1 已确认接受的风险

公开上传 URL 不要求登录，因此不能可靠证明上传人属于某家医院，也可能产生匿名存储滥用。随机 object_key 只能降低猜测和覆盖风险，不能代替鉴权。

演示版至少必须具备：

- 单 IP 和全局限流。
- 反向代理与 Django 双重 5 MB 限制。
- 只允许图片。
- 解码后重新编码，剥离元数据。
- 超时和并发隔离。
- 监控上传量、失败率和 OSS 成本。
- 不支持删除，容量告警必须启用。

### 17.2 不记录审计的准确边界

“不审计”表示：

- 不调用 write_hospital_audit_log 记录 avatar.upload、avatar.bind、avatar.source.change。
- 不新增头像历史审计表。
- 不在医院审计记录页面展示头像变更。

仍允许：

- Web 服务器访问日志。
- OSS 请求 ID、状态码和耗时日志。
- 异常堆栈和告警。
- ManagedFile.created_at、updated_at 等正常业务字段。

日志不得记录图片字节、AccessKey、Secret、完整 Authorization 或患者信息。

### 17.3 原子性

OSS 与数据库不能形成真正的单一事务：

- OSS 上传失败：不写数据库。
- OSS 成功、数据库失败：Object 永久保留，记录 orphan 指标，不删除。
- ManagedFile 成功、头像引用失败：文件保持未绑定。
- 头像引用事务成功后才返回最终成功。

### 17.4 并发

- 头像设置使用 select_for_update 和 agent.version。
- 每次成功更新 version+1。
- 前端只接受最后一次主动操作对应的响应。
- 上传/应用期间禁止再次选择，避免 A 上传慢于 B 却覆盖 B。
- Idempotency-Key 防止浏览器重试造成重复更新；由于文件永久保留，第一阶段重复上传仍可能产生两个文件，因此前端也要防双击。

### 17.5 URL 与缓存

- 每个 custom 文件使用唯一 Object Key。
- doctor 来源随医生 avatar_file 变化生成不同 avatar_version。
- 默认 AI 头像也有固定版本。
- Cache-Control 可设 public, max-age=31536000, immutable，因为 URL 随版本变化。
- API 响应中的智能体对象不应长时间公共缓存；后台接口使用 private/no-store 或短缓存。

## 18. 关键文件与改造清单

| 文件 | 当前事实 | 需要落地 |
| --- | --- | --- |
| hospital_care/models/agent_profiles.py | ClinicalAgentProfile 无头像字段 | 增加 AvatarSource、avatar_source、avatar_file、约束 |
| hospital_care/migrations/ | 当前到 0006 | 新增头像字段迁移与历史数据默认值 |
| hospital_care/api/backoffice/serializers.py | AgentCreate/Update 无头像字段 | 创建接口补头像字段；新增 AvatarUpdateSerializer |
| hospital_care/api/backoffice/views.py | 有智能体创建、详情、更新 | 新增 AgentAvatarView；公开上传放 file_manager |
| hospital_care/api/backoffice/urls.py | 无 avatar 子路由 | 增加 agents/{id}/avatar/ |
| hospital_care/services/agent_provisioning_service.py | 创建/更新有版本锁与事务 | 创建时校验头像；常规更新不处理立即头像 |
| hospital_care/services/agent_avatar_service.py | 当前不存在 | 新增解析、校验、立即切换和版本 URL |
| hospital_care/api/presenters.py | agent_public 不返回智能体头像 | 输出 avatar_source、avatar_url、avatar_version |
| hospital_care/selectors/hospital_knowledge_catalog.py | get_agent 未预取头像文件 | select_related avatar_file、doctor__avatar_file |
| hospital_care/exceptions.py | 无头像错误码 | 增加头像上传、裁剪、归属、保留错误 |
| file_manager/models.py | ManagedFile 可复用 | 不新增二进制表 |
| file_manager/business_relations.py | 支持业务关联 | 增加头像用途绑定辅助方法 |
| file_manager/views.py | 当前仅登记和删除 | 新增公开图片上传 View；删除时拦截永久头像 |
| file_manager/serializers.py | 当前无二进制图片校验 | 新增 PublicImageUploadSerializer |
| file_manager/services/image_processing.py | 当前不存在 | 新增校验、裁剪、WebP 生成 |
| file_manager/services/oss_object_service.py | 当前不存在 | 新增 OSS V2 服务端上传封装 |
| file_manager/urls.py 或独立 public_urls.py | 当前 API 都要求登录 | 注册公开图片上传 URL |
| SparkService/settings.py | 已读取 OSS 通用变量 | 增加默认 AI 头像 URL/版本和上传限流配置 |
| SparkService/urls.py | 已挂载 files、oss、hospital-care | 增加最小 public upload 路由 |
| requirements.txt | 无 OSS V2 与 Pillow | 增加依赖并锁版本 |
| backoffice-web/src/api/modules/hospitalCare.ts | AgentRow 无头像字段 | DTO、上传 API、立即设置 API |
| backoffice-web/src/components/hospital-care/ClinicalAgentFormModal.vue | 无头像控件 | 增加来源切换、裁剪、上传和立即应用 |
| backoffice-web/src/views/hospital-care/HospitalDetailView.vue | 列表名称无头像 | 展示当前智能体头像 |
| chat-web/types/hospital.ts | DoctorAgentDTO 无智能体头像字段 | 增加 avatar 字段 |
| chat-web/components/doctor/CurrentAgentHeader.tsx | 使用 agent.doctor.avatar_url | 改用 agent.avatar_url |
| chat-web/components/doctor/DoctorAgentForm.tsx | 无头像配置 | 按权限接入或只读展示 |

关键现有代码位置：

- ClinicalAgentProfile：hospital_care/models/agent_profiles.py:12
- DoctorProfile.avatar_file：hospital_care/models/organization.py:137
- AgentCreateSerializer：hospital_care/api/backoffice/serializers.py:119
- AgentUpdateSerializer：hospital_care/api/backoffice/serializers.py:135
- 智能体创建入口：hospital_care/api/backoffice/views.py:286
- 智能体详情更新入口：hospital_care/api/backoffice/views.py:351
- create_clinical_agent：hospital_care/services/agent_provisioning_service.py:183
- update_clinical_agent：hospital_care/services/agent_provisioning_service.py:258
- agent_public：hospital_care/api/presenters.py:89
- doctor_public：hospital_care/api/presenters.py:75
- ManagedFile：file_manager/models.py:8
- ManagedFileBusinessRelation：file_manager/models.py:42
- 当前文件登记：file_manager/views.py:94
- 当前 OSS URL：file_manager/url_utils.py:8
- 当前 OSS 配置：SparkService/settings.py:147
- 后台智能体表单：backoffice-web/src/components/hospital-care/ClinicalAgentFormModal.vue:1
- 后台智能体 DTO/API：backoffice-web/src/api/modules/hospitalCare.ts:114
- 医生工作台头部：chat-web/components/doctor/CurrentAgentHeader.tsx:13
- 医生工作台表单：chat-web/components/doctor/DoctorAgentForm.tsx:10

## 19. 测试与验收

### 19.1 服务端单元测试

建议新增：

~~~text
hospital_care/tests/test_agent_avatar.py
file_manager/tests/test_public_image_upload.py
~~~

必须覆盖：

1. 历史智能体默认迁移为 doctor/null。
2. doctor 来源动态读取医生头像。
3. 医生无头像返回默认 AI 头像。
4. custom 必须关联有效 ManagedFile。
5. doctor + 非空 avatar_file 被数据库约束拒绝。
6. custom + 空 avatar_file 被拒绝。
7. JPG、PNG、WEBP 上传成功并统一输出 WebP。
8. 超过 5 MB 拒绝。
9. 最长边超过 2048 拒绝。
10. 扩展名伪造拒绝。
11. 损坏图片拒绝。
12. 动图拒绝。
13. 非法裁剪参数拒绝。
14. EXIF 旋转后裁剪坐标正确。
15. 输出正好 1024×1024。
16. 输出不保留 EXIF。
17. Object Key 符合固定前缀且不含原文件名。
18. 上传成功创建 ManagedFile 和永久业务关系。
19. 未绑定文件删除被拒绝。
20. 已绑定文件删除被拒绝。
21. 已有智能体 custom 立即生效。
22. 切回 doctor 立即生效。
23. 两次并发更新只有正确 version 成功。
24. 头像更新不改变 published 状态。
25. 旧 custom 文件永久保留。
26. presenter 不向公共接口泄露 avatar_file_id/object_key。
27. 列表查询无 N+1。

### 19.2 API 集成测试

- 公共上传无需登录可成功。
- 公共接口拒绝视频、PDF、SVG 和未知 MIME。
- 公共接口忽略或拒绝客户端 object_key。
- 受保护头像设置接口未登录返回 401/403。
- 无 agent:update 权限返回 403。
- 跨医院 file_id 返回 AVATAR_FILE_FORBIDDEN。
- version 冲突返回 409 与最新 version。
- Idempotency-Key 重试不重复切换版本。
- OSS 失败返回 503，当前头像不变。

### 19.3 后台验收

- 新建表单默认显示医生头像来源。
- 更换医生时，新建表单预览同步变化。
- 新建时上传后未提交，文件保留但不产生智能体。
- 编辑已存在智能体上传后，无需点击整表保存即可在重新请求后看到新头像。
- 取消弹窗后重新打开，已切换头像仍存在。
- 切回复用医生头像立即生效。
- 头像操作后再保存简介不会产生伪版本冲突。
- 不展示头像历史列表。
- 不提供删除按钮。
- 失败时不出现破图，最终展示名称首字。

### 19.4 医生工作台与患者端验收

- CurrentAgentHeader 显示 custom，而不是医生头像。
- doctor 来源随医生头像变化，在下次刷新后更新。
- 页面打开期间不要求实时变化。
- 默认 AI 头像失败时显示名称首字。
- 历史消息不出现头像。
- 智能体停用后不能通过旧头像缓存继续进入咨询。

### 19.5 性能验收

- 5 MB 图片处理不造成请求进程长期阻塞。
- 单次转换和上传记录耗时指标。
- 列表 50 条智能体时不产生逐条头像数据库查询。
- 图片使用缩略参数，列表不下载完整 1024 图。
- 相同 avatar_url 命中浏览器/CDN 缓存。
- avatar_version 变化后命中新 URL。

### 19.6 完成定义

以下全部满足才可关闭工单：

- 数据迁移通过且历史智能体无展示回归。
- 后台新建、编辑两条流程通过验收。
- 公共上传和受保护头像设置边界清楚。
- 头像永久保留与删除保护已测试。
- 版本冲突不会覆盖其他智能体修改。
- 后台、医生工作台和患者端统一使用 agent.avatar_url。
- 默认头像和首字兜底可用。
- 全部自动化测试通过。
- 文档中的 API 字段与实际 OpenAPI/序列化器一致。

## 20. 当前非目标

- 本阶段不修改代码。
- 不创建独立图片二进制表。
- 不直接在 ClinicalAgentProfile 保存 OSS URL。
- 不复制医生头像文件生成新的智能体文件。
- 不改变医生头像现有维护流程。
- 不在本工单内设计医院 Logo、科室 Logo 或患者头像。
- 不展示历史头像列表。
- 不提供头像文件删除能力。
- 不新增头像 WebSocket 实时推送。
- 不在历史会话消息中展示头像。
- 不支持视频、SVG、GIF 动图或任意文件上传。
