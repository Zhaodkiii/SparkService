"""file_manager 内部服务：OSS 服务端上传与图片处理。

这些能力只供 SparkService 服务端内部调用；HTTP 层只开放图片上传，
不暴露任意本地路径或任意网络 URL，避免本地文件读取与 SSRF 风险。
"""
