# 素材上传：浏览器处理、OSS 直传

当前方案不需要独立处理主机或素材 worker。后台浏览器检查图片并生成缩略图，API 只管理授权、元数据和 OSS HEAD/COPY 指令。

## 使用现有服务

1. 在现有 API 环境配置 `ALIYUN_ACCESS_KEY_ID`、`ALIYUN_ACCESS_KEY_SECRET`、`ALIYUN_OSS_BUCKET`、`ALIYUN_OSS_ENDPOINT`、`ALIYUN_OSS_REGION`。沿用项目 `.env`，不要把真实密钥写入文档或版本库。
2. 执行 `python manage.py migrate material_library`，包含 `0008_browser_upload_metadata`，重启 API。当前运行方式带 `--noreload`，更新 Python 源码后需要重启。
3. 上传默认启用，`MATERIAL_UPLOADS_ENABLED=false` 可显式关闭。`manage/options/` 返回真实的配置可用状态和错误原因；不再检查独立处理任务或素材 STS 角色。
4. 现有 API 凭证需要对素材临时目录及正式目录执行 HEAD、COPY 和可选清理 DELETE 所需的 OSS 权限。浏览器仅取得绑定临时对象 key、Content-Type 和 Content-MD5 的 PUT 签名，期限 1 小时，不取得 AccessKeySecret，也不能写正式目录。
5. OSS CORS 允许实际后台来源的 PUT，以及预览所需的 GET/HEAD；PUT 允许 `Content-Type`、`Content-MD5` 请求头。浏览器的上传请求只发 OSS，不附带业务 JWT。
6. 使用新版后台选择图片，浏览器处理后直传原图和缩略图，再调用完成接口。完成接口同步确认，不需要轮询图片处理任务。

## API 协议

`POST /api/v1/materials/manage/uploads/` 仅接收 JSON：

```json
{
  "name": "flower.png",
  "purpose": "sticker",
  "original": {
    "sha256": "64位小写摘要",
    "md5": "16字节MD5的Base64值",
    "byte_size": 1024,
    "width": 512,
    "height": 512,
    "mime": "image/png",
    "has_visible_pixels": true,
    "has_transparency": true
  },
  "thumbnail": {
    "sha256": "独立的64位小写摘要",
    "md5": "缩略图MD5的Base64值",
    "byte_size": 256,
    "width": 256,
    "height": 256,
    "mime": "image/png"
  }
}
```

返回 `id / expires_at / uploads.original / uploads.thumbnail`，每个上传目标包含 `url` 和必须原样设置的 `headers`。两个图片文件通过单次 PUT 直传 OSS，不进入 API。文件上限为 10/15 MiB，无需分片。

`POST manage/uploads/{id}/complete/` 接收空 JSON，检查当前管理员所属会话。API 通过 HEAD 核对对象大小、MIME 和单次 PUT 的 ETag，再使用源 ETag 条件 COPY 建立正式对象、登记资源并返回 `state=verified`、`resource`、`thumbnail`。重复确认返回同一结果；上传成功但确认响应丢失时可重试，不要重新上传图片。

`verified` 是沿用的内部状态，在新协议中表示 **OSS 元数据确认和正式文件建立成功**。不代表 API 解码图片或重新计算 SHA-256。格式、透明度、尺寸和 SHA-256 检查在授权管理员的浏览器完成；OSS 对 PUT 的 Content-MD5 进行一致性检查。该入口不适用于匿名投稿和不可信公开上传。

原图保留原始字节，Canvas 只生成单独的静态 PNG 缩略图，保留比例和透明度。缩略图最长边 256px，不放大小图，上传时原图与缩略图分别计算摘要。

## 重试与兼容

- 浏览器本地处理失败：提示真实文件原因，不申请上传授权。
- 原图成功、缩略图失败：页面未关闭时保留上传进度，仅重试未成功的图片；签名过期则重新申请。
- 两张图片已上传：按账号保存 uploadID 和所属素材包，重新打开原包可继续确认、加入草稿，不保存文件、凭证或签名 URL。
- 文件字节未传完就关闭页面：重新选择文件；不宣称跨刷新恢复未完成的文件字节。
- 服务端 HEAD/COPY 超时：重试原 complete 请求。临时文件保持，正式目录不允许浏览器覆盖；源 ETag 约束防止确认时复制了不同文件。
- 旧版没有 `upload_metadata` 的未完成会话：要求重新选择文件，不会排队等待旧 worker。
- 已有模板素材、不可变版本、已保存作品不迁移、不覆盖。相同 SHA-256 资源还需核对属性和 OSS ETag 后才复用。

旧 `process_material_uploads` 命令已停用；停止历史部署中的该进程。临时文件清理可在现有 API 环境执行 `python manage.py cleanup_material_uploads --days 7` 预览，确认范围后增加 `--execute`。仅删除临时目录的对象，不删除正式资源；不下载图片文件。

## 验证

本地已使用运行中的 API、现有 `.env` 和真实 OSS 完成：两张图片 CORS 预检、两个直接 PUT、HEAD/COPY 确认、重复确认及两个直接 GET 哈希一致性。测试会话和对象已清理。没有改动 bucket CORS 配置或生产服务。

相关实现：`material_library/direct_uploads.py`、`management_api.py`、`backoffice-web/src/views/materialImageUpload.ts`。自动测试覆盖不接收图片正文、不调用 OSS GET/PUT 转发、错误重试、资源去重、账号权限及浏览器本地处理。

OSS 行为参考：[PutObject 的 Content-MD5 检查](https://www.alibabacloud.com/help/en/oss/developer-reference/putobject)、[CopyObject 源 ETag 条件](https://www.alibabacloud.com/help/en/oss/developer-reference/copyobject)。
