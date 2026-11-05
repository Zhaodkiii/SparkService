# 旧 AI 配置模块清理

2026-11-05。按用户要求清除 AI 场景配置、模型目录、AI 小任务、Provider 配置、试用期。保留 AI 制作额度 ai_production。

## 原代码与表位置

| 功能 | 原页面 | 原 Django 模型／物理表 |
| --- | --- | --- |
| 场景配置 | AIScenariosView.vue、AIScenarioModelsView.vue | AIScenarioModelBinding / ai_config_aiscenariomodelbinding |
| 模型目录 | AIModelsView.vue | AIModelCatalog / ai_config_aimodelcatalog |
| 小任务 | AISmallTasksView.vue | SmallTask / ai_config_smalltask |
| Provider 配置 | AIProvidersView.vue | AIProviderKeyConfig / ai_config_aiproviderkeyconfig |
| 试用期 | AITrialsView.vue | TrialApplication、TrialApplicationRequest / ai_config_trialapplication、ai_config_trialapplicationrequest |
| 关联试用策略 | ai_config 模块 | TrialModelPolicy、TrialModelPolicyItem / ai_config_trialmodelpolicy、ai_config_trialmodelpolicyitem |
| 关联 bootstrap | ai_config 模块 | AIBootstrapProfile / ai_config_aibootstrapprofile |

服务端仓库为 /Users/dream/Documents/project/Reference/SparkService。页面原位于 backoffice-web/src/views，前端 API 原为 src/api/modules/ai.ts。后台视图和序列化器原位于 backoffice/views.py、serializers.py，公共接口位于 ai_config/views.py、urls.py。

## 实际清理

删除六个旧页面、前端 API、后台路由和菜单、相关视图／序列化器、ai_config 服务／任务／资格判断／默认配置。清除登录自动发放试用、用户详情的试用查询与用户管理发放／回收入口。旧 is_pro 响应兼容字段返回 false，不影响独立 billing 会员系统。

AI 制作额度不再依赖 TrialService，使用已登录且启用的账户资格，双窗口次数和后台管理保留。其供应商请求凭证依然由 ai_production 自身服务端环境变量提供，不依赖已删除的 Provider 配置。

保留 ai_config 的空应用壳和历史迁移。0008 以 SeparateDatabaseAndState 注销全部旧模型，不直接 DROP 现有物理表。历史表数据仍留在数据库，当前没有运行代码和接口访问。backoffice 0007 停用旧权限及其子权限，保留 AI 制作额度权限。

## 验证

- 83 项服务端回归通过，覆盖 AI 制作额度、后台用户管理、登录和异步任务管理。
- 新增测试确认旧 URL 无法解析、旧模型已注销、账户可直接使用制作额度。
- 后台 vue-tsc 和 Vite 构建通过。
- 完整迁移图校验通过，ai_production 模型保留。
- 未执行正式数据库迁移或物理删表。部署时需应用上述迁移，让数据库中的旧权限条目停用。
