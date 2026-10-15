# TravelDiary 项目裁剪记录

当前架构、运行方式和升级注意事项见根目录 [README](../README.md)。

本次基于 TravelDiaryClient 的 `SupportBackend`、`AppBootstrapper`、AI 设置、账号管理与文件 API 调用核对保留范围。保留账号、文件/OSS/OCR、客户端 AI 配置、通知和异步任务，以及精简后的管理后台。

已删除：medical、nutrition、task_system、hospital_care、zdk_migration、content、chat_sync、subscriptions、app_version、chat-web、open-web 及对应后台页面、接口、任务路由、周期任务配置和历史专项文档。

客户端 AI 设置仍调用 bootstrap、trial/status、trial/apply、providers/test-connection，因此保留 ai_config；本地模型配置中的 chat 场景只用于下发客户端模型参数，不提供服务端聊天接口。健康模型场景与服务端工具配置已清理。

文件系统不再依赖医疗成员授权；文件及相同业务 ID 下的附件均只对文件所有者可见。

工作区原有未提交内容与删除目录的本地文件已备份到仓库外 `../SparkService-before-travel-cleanup-20261015-200046/`，包括 `working-tree.patch`。本轮包含已有的“设备游客不绑定演示医疗成员”变更，这是删除 medical 后登录可用所需的改动。
