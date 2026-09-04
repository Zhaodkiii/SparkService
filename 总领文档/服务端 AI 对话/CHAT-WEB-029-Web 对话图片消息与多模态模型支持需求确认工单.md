# CHAT-WEB-029 Web 对话图片消息与多模态模型支持需求确认工单

> 工单状态：需求确认完成，待实施
> 创建日期：2026-09-04
> 适用范围：SparkService / `chat-web` Web 对话、SparkService 对话服务、阿里云 OSS、ManagedFile
> 参考实现：`/Users/hua/Documents/project/DeepTutor/DeepTutorSerevr`
> 当前阶段：只确认方案与维护工单，不修改业务代码

## 1. 用户目标

当前 Web 对话存在两个直接问题：

1. 用户不能在对话过程中选择并发送图片给 AI。
2. 用户已经发送的图片不能在消息流中展示。

本工单需要让 Web 对话具备与现有客户端一致的图片发送体验：用户选择图片后，在输入区域预览；图片上传到阿里云 OSS 并展示进度；上传成功后才允许发送；发送后用户消息展示图片；服务端将图片传递给 AI。只有当前运行模型支持多模态/视觉能力时才允许发送图片，非多模态模型不能发送图片，也不能静默退化为普通文本发送。

本期只支持图片，不支持视频、PDF、Word、音频和其他文件格式。

## 2. 当前代码事实与偏差

### 2.1 `chat-web` 当前事实

| 位置 | 当前事实 | 对本工单的影响 |
| --- | --- | --- |
| `chat-web/components/chat/home/ChatComposer.tsx` | 发送按钮只依赖文本 `value.trim()`；没有图片选择状态、上传状态和附件校验 | 需要在现有输入框附近增加图片草稿状态，并将发送条件扩展为“文本或已上传图片” |
| `chat-web/components/chat/home/ComposerInput.tsx` | 只有 textarea，没有 file input、预览区或删除图片能力 | 需要新增图片选择与预览区域；不要破坏现有 Enter 发送规则 |
| `chat-web/context/RunControlContext.tsx` | `CreateRun` 已发送 canonical `input_message.blocks`，并在 `run_options.attachments` 中传递 `{file_id}` | 可以复用现有回合创建链路，但必须定义图片 block、图片附件元数据和服务端校验契约 |
| `chat-web/types/run.ts` | `attachments` 为 `unknown[]`，输入 block 支持任意 `kind` 与 `payload` | 需要把图片协议收敛成明确的类型，不继续依赖任意 JSON |
| `chat-web/lib/context/turn-context-draft.ts` | 只把 ready 的附件映射成 `{file_id}` | 需要区分“引用文件”与“发送图片”；图片发送不能依赖手工输入 ManagedFile ID |
| `chat-web/components/chat/context/ContextToolbar.tsx` | 当前“文件引用”是手填 ManagedFile ID，不是用户选择图片上传 | 本功能应放在消息输入区域，不能把图片发送伪装为上下文引用 |
| `chat-web/components/chat/home/ChatMessages.tsx` | 用户消息主要按文本渲染，图片 block 未进入用户消息展示路径 | 需要在用户消息中渲染已确认的图片缩略图/预览图，并处理加载失败 |
| `chat-web/components/chat/blocks/MediaBlocks.tsx` | 已存在 `imageGallery` 的图片渲染能力，支持 `url/src` 等字段 | 优先复用现有图片展示组件或其数据规范，避免新增第二套图片渲染器 |
| `chat_sync/ai_api/serializers.py` | `attachments` 已要求每项包含 `file_id`，数量与 references 合计最多 16 项 | 可作为服务端入口，但必须增加图片 MIME、归属、大小、用途和模型能力校验 |
| `chat_sync/ai_services/context/reference_resolver.py` | ManagedFile 可按 `file_id` 解析并校验访问权，但目前只返回文件元信息，未形成视觉输入 | 需要在不泄漏不必要文件路径的前提下，为 AI 运行时解析可访问图片 |
| `chat_sync/views.py` | 消息 wire payload 已返回 `attachments`；已有 `image_delivery_mode` 读取逻辑 | 可保留兼容字段，但应统一图片消息的服务端返回结构和送达状态 |
| `file_manager/models.py` | `ManagedFile` 已记录 MIME、大小、MD5、OSS object key、公开状态和软删除状态 | 图片上传应复用该模型，不新建图片文件表 |
| `file_manager/oss_sts_views.py` | 已有登录态 OSS STS 接口 | 上传链路需确认是否直接复用当前客户端同一套 STS/OSS 上传协议，以及是否需要 Web 专用 object key 前缀 |

### 2.2 DeepTutor 参考事实

DeepTutor 的参考位置与可复用原则如下：

- `deeptutor/services/llm/multimodal.py`：把最后一条用户消息转换为 content parts，图片使用 OpenAI-compatible 的 `image_url` 结构，或 Anthropic 的 base64 image source 结构。
- `deeptutor/agents/base_agent.py`：LLM 调用链接受 `attachments`，统一在最终发送前准备多模态消息。
- `deeptutor/agents/vision_solver/vision_solver_agent.py`：示例使用 `text` 与 `image_url` 两类内容块调用视觉模型。
- `deeptutor/tools/vision/image_utils.py`：包含图片 MIME 校验、大小限制、URL/base64 解析和图片输入规范化。

这些代码只作为协议与边界参考，不直接复制到 SparkService。SparkService 的运行模型、ManagedFile、OSS 和 `CreateRun` 仍以当前项目实现为唯一事实源。

## 3. 已确认的产品边界

- Web 对话支持发送图片。
- 用户发送的图片必须在 Web 消息流中展示。
- 只支持图片格式；其他文件格式本期不进入图片发送入口。
- 图片在输入区域先预览，上传到阿里云 OSS，并展示上传进度。
- OSS 上传成功后才允许发送；上传中、上传失败或图片校验失败时不能发送该图片。
- 只有多模态模型允许发送图片；非多模态模型应禁用图片发送或在选择/发送前明确提示原因。
- AI 必须实际收到图片内容，而不是只收到文件名或图片 URL 字符串。
- 继续复用已有对话、Run、ManagedFile、OSS 和消息 block 能力，不新建平行对话体系。
- 本工单当前只做需求确认和方案维护，不直接改动代码。

## 4. 目标用户流程（待确认细节）

```text
打开 Web 对话
  → 检查当前会话模型是否支持多模态
  → 支持：显示图片入口；不支持：入口禁用并说明原因
  → 用户选择图片
  → 前端校验格式、数量、大小和基础尺寸
  → 输入区域显示本地预览
  → 上传 OSS，显示进度
  → 上传成功并登记 ManagedFile
  → 图片草稿状态变为 ready，允许发送
  → 创建 Run，携带图片附件和用户图片 block
  → 服务端校验文件与模型能力
  → 运行时读取图片并组装多模态消息
  → AI 返回结果
  → 消息流展示用户图片与 AI 回复
```

## 5. 初步 Plain Text UI 原型

### 5.1 多模态模型可用

~~~text
┌──────────────────────────────────────────────────────────────────────────────┐
│ 对话                                                                     ⋯  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  用户 09:30                                                               │
│  ┌──────────────────────────────┐                                          │
│  │ [图片缩略图]                 │                                          │
│  │      IMG_001.png             │                                          │
│  └──────────────────────────────┘                                          │
│  请帮我看看这张图片。                                                       │
│                                                                            │
│  AI 09:30                                                                  │
│  我可以结合图片内容为你提供健康信息与就医建议……                              │
│                                                                            │
├──────────────────────────────────────────────────────────────────────────────┤
│  [待发送图片预览区]                                                        │
│  ┌──────────────┐                                                          │
│  │ [缩略图]  ×  │  IMG_001.png                                             │
│  │              │  上传完成                                                │
│  └──────────────┘                                                          │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │ 输入消息……                                                     [发送] │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  [＋] [图片]                         当前模型：支持图片理解                  │
└──────────────────────────────────────────────────────────────────────────────┘
~~~

### 5.2 上传中、失败与不支持模型

~~~text
上传中： [缩略图]  IMG_001.png  ███████░░░ 70%  正在上传…
上传失败：[缩略图]  上传失败                         [重试] [移除]
不支持： [图片] 当前模型不支持图片理解，无法发送图片
~~~

## 6. 已确认决策

### 6.1 图片上传链路：选择 A

确认采用“服务端签发 STS，浏览器直传 OSS，再登记 `ManagedFile`”链路。

落地约束：

1. Web 选择图片后先保留本地预览，不立即进入消息历史。
2. SparkService 只签发短期、受限用途的 OSS STS，不把长期阿里云密钥下发到浏览器。
3. 浏览器使用 STS 直传 OSS，并通过 OSS SDK 或 XMLHttpRequest/fetch 上传事件维护进度。
4. OSS 上传成功后，Web 调用 SparkService 的文件登记/确认接口，由服务端校验 object key、MIME、大小、MD5 和上传会话，再创建或确认 `ManagedFile`。
5. 只有拿到服务端确认的 `file_id` 且文件状态为可用，图片草稿才变为 `ready`，发送按钮才允许提交该图片。
6. CreateRun 只提交 `file_id` 和约定的图片消息 block，不直接提交图片二进制或长期 OSS 凭证。
7. STS 获取失败、OSS 上传失败、登记失败均停留在输入区域，允许重试或移除，不创建 AI Run。
8. 该链路与 iOS 共用 OSS 文件登记语义；Web 只增加浏览器上传适配，不新建第二套文件模型。

### 6.2 图片校验与压缩规则：选择 D

确认 Web 端在上传前统一压缩为服务端规定的标准图片，再通过 STS 直传 OSS。

落地约束：

1. 用户选择原始图片后，输入区域立即显示本地预览；预览不等于上传成功。
2. Web 在上传前读取图片真实尺寸和 MIME，拒绝无法解码、非图片或超出原始输入限制的内容。
3. Web 按服务端约定执行方向修正、裁剪/缩放、编码和质量处理，生成标准化图片后再上传。
4. 标准化规则必须与 iOS 最终上传结果兼容，至少明确输出 MIME、最长边/宽高、质量、文件名后缀和大小上限。
5. SparkService 登记时仍重新检查文件真实 MIME、文件大小、图片可解码性、标准尺寸和 MD5；不能信任浏览器提交的扩展名或 `Content-Type`。
6. 消息中展示的是实际发送给 AI 的标准化图片；原始图片不进入 AI 消息，也不作为本期消息附件长期保存。
7. 压缩失败时图片草稿进入失败状态，显示可重试/移除，不创建 Run。

### 6.3 单条消息图片数量与图片-only：选择 A

确认单条消息最多携带 3 张图片，并允许不填写文字直接发送图片。

落地约束：

1. 前端选择第 4 张图片时立即阻止，并保留当前 3 张图片草稿。
2. 服务端在文件登记和 CreateRun 两处都校验数量，不能只依赖前端限制。
3. 图片-only 消息仍创建正常用户消息和 Run，不伪造空文本；消息 block 中至少包含图片内容及可识别的图片元数据。
4. AI Runtime 需要将图片-only 请求转换成明确的视觉分析输入，例如“请分析用户发送的图片，并在无法判断时说明需要补充的信息”，具体提示词由服务端统一维护。
5. 图片与文字同时发送时，保持用户文字原文，并按图片顺序传递给多模态模型。
6. 3 张图片属于同一条用户消息、同一个 Run 和同一个幂等请求，不拆成多个 AI 回合。

### 6.4 OSS 存储与访问：选择 B

确认聊天图片使用 OSS 公共读，并在消息中保存公开图片 URL。

落地约束与风险记录：

1. Web 上传成功并登记 `ManagedFile` 后，服务端返回稳定的图片访问 URL，消息 block 和消息附件元数据保存该 URL 或可重建 URL 所需的文件标识。
2. 消息历史加载时直接使用该 URL 展示用户图片，不需要每次重新申请短期下载地址。
3. object key 必须使用 UUID 或不可预测随机段，不能使用患者姓名、手机号、证件号或原始文件名作为路径。
4. URL 不得写入日志、错误提示、埋点或 AI 提示词日志；日志只记录 `file_id`、哈希或脱敏标识。
5. 公共读意味着 URL 泄漏后无法依靠登录态撤回访问；演示数据不得使用真实患者敏感图片。
6. 即使 OSS 公共读，SparkService 仍需在图片登记和 CreateRun 时校验当前用户、Thread、文件状态和消息归属，不能因为 URL 可访问而放开业务越权。
7. 删除、软删除或后续改为私有存储时，需要定义历史消息图片加载失败的展示状态。

### 6.5 AI Runtime 图片输入方式：选择 A

确认 SparkService 在服务端读取 `ManagedFile`，将图片转换为受控 base64，并通过 `image_url` data URL 传给多模态模型。

落地约束：

1. CreateRun 只接收并校验 `file_id`，不信任客户端提交的公开 URL、base64、MIME 或文件大小作为事实来源。
2. Runtime 根据 `file_id` 查询当前有效 `ManagedFile`，读取 OSS 对象并重新校验图片类型、大小和可解码性。
3. 读取的图片字节只在本次 Run 的服务端内存/受控临时处理范围内使用，转换成 `data:{mime_type};base64,{data}` 后交给模型适配器。
4. 多张图片按用户选择顺序组装为多个图片 content part；文字 content part 保持原始用户文本。
5. 模型不支持图片、图片读取失败、base64 转换失败或供应商拒绝图片时，Run 返回明确失败结果，不能静默移除图片后继续纯文本回答。
6. 日志只记录 `file_id`、图片数量、MIME、字节数、耗时和稳定错误码，不记录 base64、完整图片 URL 或图片内容。
7. DeepTutor 的 `prepare_multimodal_messages`、`image_url` content part 和图片解析工具作为适配参考；SparkService 仍由自身 Runtime/Provider 入口负责调用。

## 7. 第 6 问：多模态模型能力由什么作为唯一判断来源？

为什么要问：当前 Web 必须在用户选择或发送图片前给出准确反馈，服务端也必须防止客户端伪造“支持图片”。如果 Web 自己维护模型名称列表，模型配置变化后会出现前端允许但服务端失败，或前端误禁用可用模型的问题。

请选择：

- **A. 复用服务端现有模型能力/Provider capability 判断，并由同一能力结果返回给 Web（推荐）**  
  服务端以当前实际运行绑定解析出的 capability 为准，例如 `vision`/`multimodal`；Web 只消费 `supports_image_input` 和能力版本，不维护模型名称白名单。

- **B. 由 `AIScenarioModelBinding` 或模型配置中新增/读取明确的 `supports_vision` 字段**  
  配置直观、可由运营维护，但需要保证所有模型绑定数据完整，并处理字段缺失和历史配置兼容。

- **C. Web 根据模型名称自行判断，服务端仅在模型调用失败时拦截**  
  前端改造较少，但存在客户端与服务端判断不一致和错误请求进入 Runtime 的问题。

- **D. 所有模型都允许先发送，AI Provider 失败后再提示不支持**  
  对模型配置要求最低，但会产生失败 Run、重复上传和不稳定的用户体验，不符合“非多模态模型不能发送图片”的边界。

请回复 **A、B、C 或 D**。

## 16. 最终需求摘要

### 16.1 必须实现

1. `chat-web` 对话输入区域增加图片选择入口、图片本地预览、移除、重新选择和上传进度。
2. 图片只能在当前服务端能力结果 `supports_image_input=true` 时选择和上传；非多模态模型保留置灰入口，点击提示“当前模型不支持图片理解”。
3. 图片选择后先在输入框预览，再经过 Web 标准化压缩，使用服务端签发的短期 STS 直传阿里云 OSS。
4. OSS 上传成功后调用 SparkService 文件登记/确认接口，拿到 `ManagedFile.file_id` 后才允许发送。
5. 单条消息最多 3 张图片，允许图片-only 消息，图片按选择顺序发送。
6. 用户图片消息复用 `imageGallery` block；`attachments` 保留 `file_id` 等服务端元数据。
7. SparkService 服务端按 `file_id` 读取 `ManagedFile`，转成受控 base64，以 `image_url` data URL 传给多模态模型。
8. 用户消息流展示已发送图片；图片加载失败显示固定尺寸占位卡和“重试加载”。
9. CreateRun 失败时保留图片草稿和 `file_id`，支持重试，不重新上传。
10. 上传会话、文件登记和 CreateRun 分别幂等，使用稳定 `client_message_id` 和稳定业务错误码。

### 16.2 明确不做

- 不支持视频、PDF、Word、音频和其他非图片文件。
- 不把图片二进制直接塞进 CreateRun 请求。
- 不把原始图片长期保存到 Web IndexedDB/localStorage。
- 不允许发送后编辑历史图片。
- 不支持本期拖拽调整图片顺序。
- 不允许非多模态模型上传图片后再尝试发送。
- 图片处理失败不自动移除图片并改发纯文本。
- 不新建第二套文件模型、消息模型或 OSS 存储体系。

## 17. 完整业务流程

### 17.1 进入对话与模型能力

1. Web 按现有会话流程加载 Thread、模型运行配置和消息历史。
2. 服务端在会话上下文或模型配置响应中返回 `supports_image_input`。
3. `true`：图片按钮可用；`false`、未知、配置失败或超时：图片按钮置灰但可点击提示。
4. Web 不根据模型名称自行判断，不在能力未知时上传。
5. 模型切换或运行配置版本变化时刷新能力状态；已有未发送图片任务不能自动跨模型恢复。

### 17.2 选择、预览和标准化

1. 用户点击图片按钮并选择一个或多个本地图片。
2. Web 检查选择数量，最多保留 3 张。
3. Web 检查文件可解码性和原始输入限制，读取 EXIF 方向并生成本地 object URL 预览。
4. Web 将图片统一转换为服务端约定的标准格式、尺寸和质量；标准化结果才是实际上传、展示和 AI 输入对象。
5. 图片草稿状态从 `selected` 进入 `processing`，处理成功进入 `ready_to_upload`，失败进入 `failed`。

### 17.3 STS 与 OSS 上传

1. Web 向 SparkService 请求短期图片上传 STS/上传会话。
2. 服务端校验登录态、用途、当前会话/用户范围、图片能力和上传数量，返回短期凭证、bucket、endpoint、object key 约束和上传会话 ID。
3. Web 使用 STS 直传标准化图片到 OSS，监听上传进度。
4. 上传中显示百分比，发送按钮保持不可用。
5. OSS 上传完成后，Web 调用登记/确认接口。
6. SparkService 校验上传会话、object key、文件存在性、真实 MIME、大小、图片解码结果和 MD5，然后创建或复用 `ManagedFile`。
7. 返回 `file_id`、公开展示 URL、版本标识和文件状态 `ready`。
8. 所有图片都 `ready` 后，图片草稿才能进入可发送状态。

### 17.4 CreateRun 与多模态 AI

1. Web 生成稳定 `client_message_id`，将文字和图片按选择顺序组装成一个用户消息。
2. `input_message.blocks` 包含现有 `imageGallery` block；`run_options.attachments` 包含每个图片的 `file_id`。
3. SparkService 在 CreateRun 入口再次校验 Thread、用户、图片数量、文件状态和当前模型能力。
4. Runtime 根据 `file_id` 读取 ManagedFile 对应 OSS 对象，重新验证图片，不信任客户端 URL/base64。
5. 服务端将文字和图片转换为 Provider 适配器需要的 content parts：文字为 `text`，图片为 `image_url` data URL。
6. 多模态模型开始流式/非流式调用，AI 回复沿用现有 Run、事件和消息写入机制。
7. 用户消息的图片 block 与 AI 回复一起进入消息历史，Web 使用现有图片渲染规则展示。

### 17.5 失败与重试

- 压缩失败：输入区显示失败，允许重试/移除，不上传。
- STS 失败：显示上传失败，允许重试，不创建 Run。
- OSS 失败：保留本地草稿，允许重试上传。
- 登记失败：若可重试，复用上传会话；若文件状态不合法，要求移除并重新选择。
- CreateRun 失败：保留 `file_id` 和文字草稿，允许重试，不重新上传。
- 模型不支持图片：直接阻断，不自动改为纯文本。
- 历史图片加载失败：只显示占位卡，不影响文字和 AI 回复。

## 18. 图片草稿与发送状态机

```text
selected
  → processing
  → ready_to_upload
  → uploading(progress)
  → uploaded
  → registering
  → ready
  → sending
  → sent

processing/uploading/registering/sending
  → failed(retryable | non_retryable)

failed(retryable) → retry_same_file_or_upload
failed(non_retryable) → remove_or_reselect
ready → removed
```

规则：

- 只有全部图片为 `ready` 才能发送。
- `selected`、`processing`、`uploading`、`registering`、`failed` 图片不能进入 CreateRun。
- CreateRun 失败不回退为 `selected`，保留 `ready` 和 `file_id`。
- 已发送消息只能展示，不能回写或替换图片。

## 19. 数据与消息模型方案

### 19.1 复用模型

- 继续复用 `ManagedFile`：记录文件归属、MIME、大小、MD5、OSS object key、公开状态和生命周期。
- 继续复用 `ChatMessage`、canonical blocks 和 `ChatRun`。
- 继续复用 `imageGallery` block 及现有 `MediaBlocks` 渲染能力。
- 继续复用 `attachments[].file_id` 的现有 CreateRun 输入入口。

### 19.2 建议的图片附件字段

```json
{
  "file_id": "123",
  "type": "image",
  "order": 0,
  "mime_type": "image/webp",
  "file_size": 183420,
  "file_version": "uuid-or-revision",
  "display_url": "https://oss.example/..."
}
```

其中 `file_id` 是服务端事实来源，`display_url` 只用于展示，客户端不能使用它替代文件校验。

### 19.3 图片 block 示例

```json
{
  "kind": "imageGallery",
  "status": "ready",
  "revision": 1,
  "order_key": 1100,
  "node_role": "timeline",
  "payload": {
    "images": [
      {
        "file_id": "123",
        "url": "https://oss.example/...",
        "filename": "image-001.webp",
        "mime_type": "image/webp",
        "order": 0
      }
    ]
  }
}
```

## 20. 接口契约建议

以下接口名称为需求契约建议，实施时应优先对齐当前 iOS 已有接口，避免新增重复协议。

### 20.1 获取图片上传 STS

```http
POST /api/v1/oss/chat-images/upload-sessions/
Authorization: Bearer <access-token>
Idempotency-Key: <upload-intent-key>
Content-Type: application/json
```

```json
{
  "purpose": "chat_image",
  "thread_id": "thread-uuid",
  "count": 1,
  "mime_type": "image/webp",
  "file_size": 183420,
  "client_upload_id": "upload-uuid"
}
```

成功响应应包含：`upload_session_id`、短期 STS、`region`、`bucket`、`endpoint`、限定 object key、过期时间和服务端能力限制。不得返回长期 AccessKey/Secret。

### 20.2 登记/确认 OSS 文件

```http
POST /api/v1/oss/chat-images/upload-sessions/{session_id}/complete/
Authorization: Bearer <access-token>
Idempotency-Key: <client-upload-id>
```

```json
{
  "client_upload_id": "upload-uuid",
  "object_key": "zhaodkdream/spark_service/chat/image/<uuid>.webp",
  "mime_type": "image/webp",
  "file_size": 183420,
  "file_md5": "..."
}
```

成功返回：`file_id`、`file_uuid`、`status=ready`、`display_url`、`version`。重复提交返回同一 `file_id`。

### 20.3 CreateRun 图片请求

```json
{
  "input_message": {
    "thread_id": "thread-uuid",
    "role": "user",
    "client_message_id": "message-uuid",
    "blocks": [
      {
        "kind": "text",
        "payload": {"text": {"_0": "请帮我看看"}}
      },
      {
        "kind": "imageGallery",
        "payload": {"images": [{"file_id": "123", "order": 0}]}
      }
    ]
  },
  "run_options": {
    "capability": "chat",
    "attachments": [
      {"file_id": "123", "type": "image", "order": 0}
    ],
    "client": {"platform": "web", "version": "p3", "device_id": "web"}
  }
}
```

服务端必须拒绝：数量超过 3、非图片 MIME、非 ready 文件、未授权文件、非多模态模型、缺少稳定消息 ID、图片 block 与 attachments 数量不一致的请求。

## 21. 稳定业务错误码建议

| 错误码 | 含义 | 客户端动作 |
| --- | --- | --- |
| `chat_image_capability_unavailable` | 当前模型不支持或能力未知 | 置灰入口/提示，不上传 |
| `chat_image_count_exceeded` | 超过 3 张 | 保留已有图片，拒绝新增 |
| `chat_image_format_invalid` | 不是允许的图片 | 移除该图片并提示 |
| `chat_image_normalize_failed` | 标准化压缩失败 | 允许重新处理或重选 |
| `chat_image_upload_failed` | OSS 上传失败 | 重试上传 |
| `chat_image_registration_failed` | ManagedFile 登记失败 | 按 retryable 决定重试 |
| `chat_image_not_ready` | 文件尚未可发送 | 等待或重试登记 |
| `chat_image_not_found` | 文件不存在 | 移除并重新选择 |
| `chat_image_read_failed` | Runtime 无法读取 | Run 失败，不降级纯文本 |
| `chat_image_provider_rejected` | Provider 拒绝图片 | 明确失败，不降级 |
| `chat_run_idempotency_pending` | 同一消息仍在处理中 | 查询/等待原 Run |
| `chat_thread_not_writable` | Thread 不可发送 | 沿用现有会话错误处理 |

## 22. 关键文件位置

### 22.1 Web `chat-web`

- `chat-web/components/chat/home/ChatComposer.tsx`：图片草稿状态、发送按钮条件、上传/发送协调。
- `chat-web/components/chat/home/ComposerInput.tsx`：textarea 与图片预览区的组合输入组件。
- `chat-web/components/chat/home/ChatMessages.tsx`：用户消息 `imageGallery` block 接入和失败占位。
- `chat-web/components/chat/blocks/MediaBlocks.tsx`：复用图片展示和加载失败渲染规则。
- `chat-web/components/chat/blocks/registry.tsx`：确认 `imageGallery` 注册保持兼容。
- `chat-web/context/RunControlContext.tsx`：CreateRun 请求、稳定 `client_message_id`、失败重试。
- `chat-web/lib/api/run-api.ts`：Run 接口封装；如新增图片上传 API，应放在独立 file/chat-image API 模块。
- `chat-web/types/run.ts`：补齐明确的图片 block、附件和错误响应类型。
- `chat-web/types/chat.ts`：确认用户图片消息和 `imageGallery` wire 类型。
- `chat-web/lib/context/turn-context-draft.ts`：避免将图片发送误当成普通文件引用。
- `chat-web/components/chat/context/ContextToolbar.tsx`：保留原文件引用能力，与图片发送入口分离。

### 22.2 SparkService 服务端

- `chat_sync/ai_api/serializers.py`：CreateRun 图片 block、attachments 数量和字段校验。
- `chat_sync/ai_api/views.py`：CreateRun API 入口和稳定错误响应。
- `chat_sync/ai_services/run_service.py`：用户消息、Run 幂等和图片附件快照。
- `chat_sync/ai_services/context/reference_resolver.py`：ManagedFile 访问校验与图片来源解析边界。
- `chat_sync/views.py`：消息 wire payload、attachments 和图片送达字段兼容。
- `chat_sync/models.py`：确认 Thread/消息现有图片元数据字段是否足够，避免重复建表。
- `chat_sync/ai_services/run_readiness_service.py`：能力或运行准备状态接入位置。
- `file_manager/models.py`：复用 `ManagedFile`。
- `file_manager/oss_sts_views.py`、`file_manager/sts_utils.py`：复用 STS 签发机制。
- `file_manager/public_views.py`、`file_manager/services/oss_object_service.py`：参考现有图片上传和 OSS Object 操作边界。
- `file_manager/serializers.py`、`file_manager/urls.py`：文件登记与输出结构。
- `chat_sync/ai_runtime` 或实际 Provider 适配目录：把 `file_id` 解析为 base64 data URL 并组装多模态消息。

### 22.3 DeepTutor 参考位置

- `deeptutor/services/llm/multimodal.py`：content parts 和 data URL 组织参考。
- `deeptutor/agents/base_agent.py`：attachments 进入 LLM 调用的参考。
- `deeptutor/agents/vision_solver/vision_solver_agent.py`：`text + image_url` 结构参考。
- `deeptutor/tools/vision/image_utils.py`：图片类型、大小、URL/base64 处理参考。

## 23. 核心伪代码示例

### 23.1 Web 选择与上传

```ts
async function selectImages(files: File[]) {
  if (!supportsImageInput) return showHint("当前模型不支持图片理解");
  if (draftImages.length + files.length > 3) return showError("最多发送 3 张图片");

  const drafts = files.map(createLocalPreview);
  setDraftImages(append(draftImages, drafts));

  for (const draft of drafts) {
    try {
      const normalized = await normalizeForServer(draft.file);
      draft.status = "uploading";
      const session = await api.createUploadSession(normalized.metadata);
      await oss.put(session, normalized.blob, (progress) => updateProgress(draft.id, progress));
      const managed = await api.completeUpload(session.id, normalized.metadata);
      updateDraft(draft.id, { status: "ready", fileId: managed.file_id, url: managed.display_url });
    } catch (error) {
      updateDraft(draft.id, { status: "failed", error: toStableError(error) });
    }
  }
}
```

### 23.2 Web 发送

```ts
async function submit() {
  const images = draftImages.filter((item) => item.status === "ready");
  if (draftImages.some((item) => item.status !== "ready")) return showError("图片尚未上传完成");
  if (!text.trim() && images.length === 0) return;

  const clientMessageId = stableDraftMessageId();
  const payload = buildCanonicalMessage({
    clientMessageId,
    text,
    imageBlock: buildImageGallery(images),
    attachments: images.map(toAttachment),
  });

  try {
    await runApi.create(threadId, payload, clientMessageId);
    clearDraftAndObjectUrls();
  } catch (error) {
    keepDraftForRetry({ clientMessageId, payload, images });
    showSendFailure(toStableError(error));
  }
}
```

### 23.3 服务端 Runtime 组装多模态消息

```py
def build_multimodal_user_content(*, user_text, attachments, thread, user):
    assert len(attachments) <= 3
    parts = []
    if user_text.strip():
        parts.append({"type": "text", "text": user_text.strip()})
    if not parts:
        parts.append({"type": "text", "text": IMAGE_ONLY_PROMPT})

    for attachment in ordered(attachments):
        file = resolve_authorized_image_file(
            user=user, thread=thread, file_id=attachment["file_id"]
        )
        raw, mime = read_and_validate_managed_file(file)
        encoded = base64.b64encode(raw).decode("ascii")
        parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime};base64,{encoded}"},
        })
    return parts
```

### 23.4 服务端能力阻断

```py
def validate_image_run(*, runtime_capability, attachments):
    if not attachments:
        return
    if not runtime_capability.supports_image_input:
        raise ChatError("chat_image_capability_unavailable")
    if len(attachments) > 3:
        raise ChatError("chat_image_count_exceeded")
    for item in attachments:
        if item.get("type") != "image" or not item.get("file_id"):
            raise ChatError("chat_image_format_invalid")
```

## 24. 安全与运营边界

1. STS 仅短期有效、限定 bucket/object key 前缀和上传动作；浏览器不接触长期 AK/SK。
2. 公共读 URL 可能被转发，演示环境禁止使用真实患者敏感图片。
3. object key 使用 UUID，不包含姓名、手机号、证件号和原始文件名。
4. 前端提交的 MIME、URL、大小和文件名全部视为不可信；服务端读取真实对象重新校验。
5. 不记录 base64、图片 URL 和图片内容；日志使用 `file_id`、哈希、request ID 和稳定错误码。
6. 对 STS、上传登记和 CreateRun 分别限流，避免重复点击和恶意大批量上传。
7. OSS 公共读下不得把完整 URL 放进错误文案、埋点、诊断面板或 AI trace。
8. ManagedFile 软删除后历史消息显示不可用占位；不能通过旧 URL 恢复业务权限。
9. 图片处理和 base64 转换应限制最大字节数、最大像素数和并发数，防止内存耗尽。
10. 生产环境上线前必须重新评估公共读策略；本工单仅按已确认方案落地演示版本。

## 25. 测试与验收标准

### 25.1 Web 输入与上传

- 多模态模型显示可用图片入口。
- 非多模态模型入口置灰，点击出现提示，不打开文件选择器、不上传。
- 选择图片后立即出现预览。
- 超过 3 张时第 4 张被拒绝。
- 上传进度从 0 到 100% 正确展示。
- 上传失败可以重试或移除。
- 压缩失败不会创建上传会话或 Run。
- 只有所有图片 ready 后发送按钮可用。

### 25.2 CreateRun 与 AI

- 文字+图片创建一个用户消息和一个 Run。
- 图片-only 可以创建正常 Run。
- 图片顺序与选择顺序一致。
- `attachments` 与 `imageGallery` 数量不一致时服务端拒绝。
- 非多模态模型伪造图片请求时服务端拒绝。
- Runtime 实际将图片转换为 `image_url` data URL。
- 图片读取失败时 Run 明确失败，不转纯文本。

### 25.3 消息展示

- 用户消息展示图片而不是只展示文件名。
- 多图按顺序显示。
- 图片加载失败显示固定占位卡和重试按钮。
- 重试加载不创建新 Run。
- 文本和 AI 回复不因图片展示失败而消失。
- 页面刷新后使用 URL/版本正确更新，不持久化原图。

### 25.4 幂等与异常

- 重复完成上传返回同一 `file_id`。
- CreateRun 超时使用同一 `client_message_id` 重试不生成重复消息。
- CreateRun 失败后图片草稿仍存在。
- 不可重试错误不会自动循环重试。
- 错误展示根据业务码，不依赖错误文案。

### 25.5 iOS 回归

- 现有 iOS 图片消息仍能按 `imageGallery` 展示。
- 新增 Web 字段不会破坏既有 `attachments` 解析。
- iOS 不因 Web 新增公开展示 URL 而改变既有图片同步逻辑。
- 同一消息在 Web 和 iOS 的图片数量、顺序和展示语义一致。

## 26. 实施顺序与回滚

### 阶段一：服务端契约与 Runtime

1. 固定图片附件 JSON、`imageGallery` payload 和错误码。
2. 补齐 CreateRun 图片数量、类型、状态、能力和幂等校验。
3. 接入 ManagedFile 到 OSS 对象读取和图片真实校验。
4. 接入 Provider 多模态 content parts 和 base64 data URL。
5. 完成服务端单测、接口测试和模型能力矩阵测试。

### 阶段二：Web 上传与消息输入

1. 增加图片草稿状态模型。
2. 增加标准化压缩和 object URL 预览。
3. 接入 STS、OSS 直传和登记确认。
4. 改造发送按钮和 CreateRun payload。
5. 接入用户 `imageGallery` 渲染、失败占位和重试加载。

### 阶段三：联调与回归

1. 使用演示图片完成 OSS、登记、Run、流式事件和历史消息闭环。
2. 覆盖普通文本模型、多模态模型、网络失败、重复点击和刷新恢复。
3. 执行 iOS 协议回归，不新增 iOS UI。
4. 检查日志、URL 泄漏、STS 过期和错误码映射。

### 回滚方案

- Web 通过功能开关关闭图片入口，普通文本对话保持原链路。
- 服务端保留已写入图片消息的只读展示，停止新图片 CreateRun。
- 不删除已上传 ManagedFile/OSS 对象，避免破坏历史消息引用。
- Provider 多模态适配异常时只关闭图片能力，不影响文本模型。

## 27. 最终状态

本工单已完成需求确认，最终采用：

```text
STS 直传 OSS
  → 登记 ManagedFile
  → 最多 3 张图片 / 支持图片-only
  → imageGallery + attachments.file_id
  → 服务端读取并转 base64 data URL
  → Provider 多模态模型处理
  → 用户消息展示图片
  → 失败可恢复、错误码稳定、全链路幂等
```

实施顺序确定为：服务端契约与 Runtime → Web 上传/发送 → 端到端联调；本期验收 Web，iOS 执行协议回归。未修改任何业务代码。

### 6.6 多模态能力判断来源：选择 A

确认复用服务端现有模型能力/Provider capability 判断，并由同一能力结果返回 Web。服务端能力结果是 Web 是否允许选择图片和 CreateRun 是否接受图片的唯一事实源。

落地约束：

1. Web 不维护模型名称、Provider 名称或版本号白名单，不根据字符串猜测是否支持图片。
2. 服务端在当前实际运行配置解析完成后，返回 `supports_image_input`、能力标识和必要的能力版本信息。
3. Web 首次进入会话、切换模型或运行配置版本变化时刷新能力状态；发送前仍由服务端再次校验。
4. 客户端认为支持但服务端最终判定不支持时，以服务端稳定业务错误码为准，不能创建图片 Run。
5. 能力字段缺失、能力服务异常或运行配置未确定时，按“不允许发送图片”处理，并向用户说明当前模型图片能力暂不可用。
6. 能力判断只决定是否允许图片输入，不改变普通文本对话的既有模型选择和发送逻辑。

### 6.7 非多模态模型的图片入口：选择 A

确认保留图片按钮但置灰。用户点击时提示“当前模型不支持图片理解”，不打开文件选择器、不上传 OSS、不创建图片草稿。

落地约束：

1. 图片按钮的可用状态由服务端返回的 `supports_image_input` 驱动。
2. `false`、能力未知、运行配置加载失败和能力检查超时均按置灰处理。
3. 置灰按钮仍可获得焦点并响应点击提示，不能使用完全不可访问的 `disabled` 语义导致用户无法理解原因；视觉上必须明确不可用。
4. 从多模态模型切换到非多模态模型时，尚未发送的图片草稿必须停止上传并进入“当前模型不支持”的待处理状态；不得继续发送。
5. 从非多模态模型切换到多模态模型后，只有重新选择图片才开始上传，不自动恢复被阻止的旧图片上传任务。
6. 服务端 CreateRun 仍必须独立阻断图片请求，不能把前端置灰作为安全边界。

### 6.8 用户图片消息协议：选择 A

确认复用现有 `imageGallery` block 展示用户图片，并在 `attachments` 中保留 `file_id` 等服务端元数据。

落地约束：

1. 用户消息的 `blocks` 包含一个 `imageGallery` block；图片顺序由 `payload.images` 或当前系统约定的等价字段表达。
2. `attachments` 保存每张图片的 `file_id`，作为服务端权限校验、ManagedFile 解析和 AI Runtime 输入的唯一文件关联。
3. 图片 URL 可以作为展示字段返回，但不能替代 `file_id` 成为服务端事实来源。
4. Web 优先复用 `MediaBlocks` 的图片渲染规则；`ChatMessages` 只负责将用户消息中的图片 block 接入现有消息布局。
5. iOS 和 Web 使用相同的图片 block 语义，避免同一条消息在不同客户端一端可见、一端只显示文本。
6. AI Runtime 从 `attachments.file_id` 解析图片；不从 `imageGallery` 中的公开 URL 反向抓取图片作为运行时输入。

### 6.9 CreateRun 失败后的图片草稿：选择 A

确认图片上传成功但 CreateRun 失败时，保留图片草稿和已确认的 `file_id`，显示“发送失败”，允许用户点击重试。

落地约束：

1. 上传成功的图片不重新上传；重试复用原图片 `file_id` 和标准化图片 URL。
2. 原始文字、图片顺序和图片列表作为同一份可重试草稿保留，用户可以在重试前编辑文字或移除图片。
3. 每次 CreateRun 重试使用新的请求幂等键，但继续携带稳定的客户端消息标识，服务端不得重复创建同一用户消息。
4. 如果失败原因是模型不支持图片、文件不存在、权限失效或图片已删除，禁止反复重试无效请求，应提示移除图片或切换模型。
5. 本期至少保证当前页面生命周期内保留失败草稿；刷新后的草稿持久化属于后续缓存能力。
6. 用户主动移除图片时不发送消息；文件清理由 ManagedFile/OSS 生命周期另行处理。

### 6.10 历史图片加载失败：选择 A

确认历史消息中的图片加载失败时，显示固定尺寸的失败占位卡，保留文件名或图片数量，并提供“重试加载”；不影响同一条消息中的文字和 AI 回复。

落地约束：

1. 图片加载失败只影响图片展示 block，不把已完成的用户消息或 Run 改成失败。
2. 占位卡至少展示“图片加载失败”、原始文件名或“共 N 张图片”等可识别信息。
3. 点击“重试加载”只重新加载展示 URL，不重新上传、不重新创建消息、不重新调用 AI。
4. 多图消息中单张失败时，只替换失败图片的占位状态，其他图片继续展示。
5. 如果服务端已标记文件删除或不可用，重试后仍显示“图片已不可用”。
6. 图片失败时不隐藏文字、不隐藏 AI 回复；AI 是否处理成功以 Run 状态为准。

### 6.11 发送前图片编辑：选择 A

确认发送前允许移除和重新选择图片，不支持拖拽排序；图片按选择顺序发送，已发送历史消息不可修改。

落地约束：

1. 每张图片草稿卡提供“移除”操作；移除只从当前待发送列表删除，不删除 OSS Object 或 `ManagedFile`。
2. 替换图片通过移除旧草稿后重新选择并重新上传实现，不覆盖原 OSS Object。
3. 上传任务进行中移除时应取消前端任务监听；已完成上传但尚未发送的文件不参与 CreateRun。
4. 不提供拖拽排序；服务端以客户端提交的图片顺序保存 `imageGallery` 与附件关联顺序。
5. 图片发送成功后，输入区域清空；历史消息中的图片、URL、文件关联和 AI 输入不可通过 Web 编辑。
6. 发送失败重试仍可以移除图片或编辑文字，但保留图片顺序规则。

### 6.12 图片缓存策略：选择 A

确认只缓存消息展示所需的标准图片 URL 和浏览器临时缓存，不单独持久化原图；URL 或版本标识变化时自然刷新。

落地约束：

1. 消息状态中保存标准化图片的展示 URL、`file_id` 和必要的版本标识；不在 Web IndexedDB/localStorage 中长期保存原图二进制。
2. 输入区域的本地预览只服务于当前草稿；发送完成、移除草稿或页面离开后释放 object URL。
3. 历史消息优先使用浏览器正常缓存；服务端返回新的 URL 或版本参数时，前端替换旧 URL，避免继续展示旧图。
4. 不新增离线图片数据库、不做原图预下载、不把图片写入普通用户偏好缓存。
5. 浏览器缓存无法由业务完全控制，涉及真实患者图片时仍须遵循演示数据和隐私边界；本期不承诺离线图片可用。
6. 图片加载失败只按第 10 问确认的占位与重试规则处理，不通过本地长期缓存绕过服务端返回状态。

### 6.13 异常码与幂等：选择 A

确认上传会话、文件登记和 CreateRun 分别幂等；客户端使用稳定 `client_message_id`，服务端返回稳定业务错误码。

落地约束：

1. STS 获取、OSS 上传、文件登记、CreateRun 各自拥有明确阶段状态；客户端不能把某一阶段的成功误认为整个发送成功。
2. 文件登记接口支持同一上传会话或客户端上传标识重复确认，重复确认返回同一个有效 `file_id`，不重复创建 ManagedFile。
3. CreateRun 重试携带同一 `client_message_id`，服务端按已有消息/幂等记录返回原结果或明确处理中状态，不重复创建用户消息和 Run。
4. 请求超时不能直接判断为失败并重新创建新消息；客户端先查询幂等结果或使用同一标识重试。
5. 业务错误至少区分：模型不支持图片、图片数量超限、文件不存在、文件不可用、图片格式非法、图片读取失败、上传失败、登记失败、Thread 不可发送和服务暂不可用。
6. 客户端根据稳定错误码决定重试、移除图片、切换模型或联系管理员，不依赖错误文案匹配。
7. 日志和埋点记录阶段、`client_message_id` 哈希、`file_id`、错误码和 request ID，不记录图片内容和公开 URL。

## 14. 第 14 问：本工单实施顺序和验收范围如何安排？

为什么要问：图片能力同时涉及 Web 输入框、OSS、ManagedFile、CreateRun、消息渲染和 AI Provider。若没有明确先后顺序，前端可能先完成预览但服务端不能处理，或服务端支持图片但消息历史无法展示。

请选择：

- **A. 先服务端契约与 Runtime，再 Web 上传/发送，最后端到端联调；本期只验收 Web，iOS 做协议回归（推荐）**  
  先固定能力判断、图片登记、CreateRun、消息 block 和错误码，再实现 Web 交互；iOS 不新增 UI，但验证既有客户端不被新协议破坏。

- **B. 先做 Web UI，服务端接口和 AI 处理后补**  
  能快速看到界面，但会产生临时 mock 协议和较高返工风险。

- **C. Web、iOS、服务端同时并行开发，最后统一定义协议**  
  并行速度快，但容易出现 block、字段、错误码和图片生命周期不一致。

- **D. 先只实现图片上传与展示，AI 多模态处理延后**  
  可以拆小范围上线，但不满足本工单“图片需要实际交给 AI”的核心目标。

已确认选择 **A**：先服务端契约与 Runtime，再 Web 上传/发送，最后端到端联调；本期验收 Web，iOS 做协议回归。

## 15. 问答确认结果索引

本工单已完成一问一答，以下为最终确认索引：

1. 图片上传链路：已确认 A。
2. Web 上传是否复用当前客户端的图片大小、格式、数量和压缩规则：已确认 D，标准化压缩后上传。
3. 单条消息最多发送几张图片，以及是否允许只发图片不填文字：已确认 A，最多 3 张，允许图片-only。
4. 图片在 OSS 中使用什么 object key 根目录和可见性策略：已确认 B，OSS 公共读并保存公开 URL。
5. 图片发送给 AI 时，运行时使用受控下载/内部读取，还是给模型使用临时签名 URL：已确认 A，服务端转 base64 data URL。
6. 多模态能力由模型配置的 capability 字段判断，还是由现有模型能力服务判断：已确认 A，服务端 Provider capability 为唯一来源。
7. 非多模态模型是在选择图片前隐藏入口、选择后提示，还是保留入口但置灰：已确认 A，按钮置灰并提示，不触发上传。
8. 用户图片消息使用现有 `imageGallery` block，还是新增专用 canonical block：已确认 A，复用现有 block 并保留 `attachments.file_id`。
9. 图片上传成功但 CreateRun 失败时，草稿图片是否保留并允许重试发送：已确认 A，保留草稿和 `file_id` 重试。
10. 图片消息的加载失败、OSS 过期、文件被删除时如何展示：已确认 A，局部失败占位并支持重试加载。
11. 是否允许用户在发送前移除、替换和重新排序图片：已确认 A，允许移除和重新选择，按选择顺序发送。
12. 图片 URL、缩略图和原图在消息历史中的缓存与安全边界：已确认 A，只用 URL 和浏览器临时缓存。
13. 服务端异常码、幂等、重复上传和消息重放规则：已确认 A，分阶段幂等并使用稳定错误码。
14. Web 与 iOS 的验收矩阵和实施顺序：已确认 A，先服务端契约与 Runtime，再 Web，最后联调；本期验收 Web，iOS 做协议回归。

## 28. 文档补齐状态

问答结束后要求补齐的内容已经在第 16—27 章完成：

- 最终需求摘要和不做范围。
- Web、SparkService、OSS、ManagedFile、AI Runtime 的完整业务流程。
- 图片草稿状态机和消息发送状态机。
- 数据模型复用与必要字段变更建议。
- 上传、登记、图片消息、运行时多模态调用的接口契约。
- 多模态模型判断、非多模态阻断和错误码映射。
- 图片消息 Plain Text UI 全状态原型。
- `chat-web`、SparkService 后端和 DeepTutor 参考位置对应的关键文件清单。
- 核心代码示例（仅在需求方案阶段以伪代码/接口示例描述，不直接改代码）。
- 安全、隐私、OSS URL、日志脱敏、限流和资源清理方案。
- 单元测试、接口测试、端到端测试和验收标准。
- 分阶段实施顺序、回滚方案和上线检查清单。
