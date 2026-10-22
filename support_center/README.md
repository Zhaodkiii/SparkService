# TravelDiary 帮助与反馈

本模块提供帮助发布、反馈工单、私有截图、角色权限、公开回复与内部备注、未读、通知 Outbox 和回收。用户 API 为 `/api/v1/support/`，管理 API 为 `/api/admin/v1/support/`。后台页面位于 `backoffice-web/src/views/Support*View.vue`。

完整需求、实际契约及本地验证记录见 [客户端项目中的实施记录](/Users/dream/Documents/project/TravelDiary/TravelDiaryClient/需求文档/设置与服务/实施与验证记录.md)。当前代码已本地验证，尚未远程部署。

部署先执行 `python manage.py migrate` 和 `python manage.py seed_support`，再重启 API、worker、beat 并构建后台。初始化提供 11 篇帮助，不覆盖已有文章，不开启受理；需实际管理员核对内容、服务说明和客服权限后在后台开启受理。

权限统一采用 `support_center.*`，兼容现有后台角色及 Django permission；管理员还须为有效 staff/superuser。普通移动用户的 token bundle_id 默认允许 `cn.zhaodk.TravelDiary`，可通过设置 `SUPPORT_ALLOWED_BUNDLE_IDS` 显式调整。

队列使用现有 `notification.transactional` 和 `cleanup`；每小时任务 `support_center.tasks.cleanup_support_data` 回收过期未绑定附件、超过配置周期的结束工单和对象墓碑。`python manage.py cleanup_support` 默认预览，`--execute` 执行。活跃工单和文章历史版本引用的帮助图片受保护。

测试：

```sh
.venv/bin/python manage.py test support_center --settings=SparkService.test_settings
cd backoffice-web
pnpm run test:support
pnpm run build
```

对象存储与 APNs 在专项测试中隔离；真实 OSS 的 PUT/CORS/HEAD 以及生产推送需部署后验证。私人截图不能用作公开帮助图片，私有 API 请求正文及响应签名不得写入普通访问日志。
