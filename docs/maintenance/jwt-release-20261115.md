# JWT 发布保护与生产轮换

目标：39.106.39.110；分支 TravelDiary，基础提交 1583c659ea56153b025ce9d7971b97aec6b32bc3，发布包含工作区改动。
Release：20261115_232634_37083_3777。配置已同步，无回滚。

普通发布移除本地候选中的 JWT_SIGNING_KEY，远端保留生产旧值；旧配置无显式 JWT 时固定原 DJANGO_SECRET_KEY。其他配置沿用原同步流程。显式 DEPLOY_JWT_KEY_FILE 才执行轮换。本次按用户要求生成生产独立密钥并显式轮换，已有登录将失效一次。

四服务运行，web/frontend 健康；API、迁移检查、Celery ping/注册/队列验收通过。web/worker/beat 实际签名密钥均与本次生产文件一致（只比对摘要）。

配置合并测试 4 项通过，目标保护测试 6 项通过。额外部署模拟测试 17 项中有 10 项失败（包括 public-web fixture 缺失、mock remote 未执行预期流程）；未宣称全套测试通过。线上真实部署及 post_release_audit 成功。存在既有 MySQL 长唯一字段检查警告。

密钥保存于发版技能目录 private-jwt-20261115，权限 600，不提交内容。computer-b.jwt 为另一台测试电脑生成，其配置需用户手动更新并重启。
