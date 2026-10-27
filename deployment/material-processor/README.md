# 旧素材独立处理方案已取消

2026-10-27 按用户要求取消独立处理服务器。当前使用浏览器本地检查、生成缩略图并直传 OSS，现有 API 只执行 HEAD/COPY 元数据操作。

请使用 [素材直接上传运行说明](../material-direct-upload/README.md)。无需配置 MATERIAL_WORKER_ENABLED、MATERIAL_WORKER_OSS_ENDPOINT 或新建处理主机。旧 process_material_uploads 命令已停用；如历史环境运行了该进程，应停止它。
