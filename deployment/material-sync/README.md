# 单包同步生产：部署与运行

实现日期：2026-10-27。目标为独立 sticker 包。代码默认关闭发送/接收；配置示例见 env.example。需求规格位于 TravelDiaryClient/需求文档/贴纸库/08-后台单包同步生产需求.md。

## 组成

- sync_protocol.py：有界白名单快照、稳定身份、跨环境 SHA256、差异与冲突基线、OSS HEAD。
- sync_transport.py：固定 HTTPS 目标、HMAC 服务身份、nonce 防重放、禁止重定向、超时与响应大小限制。
- sync_api.py / sync_urls.py：来源用户 API、生产服务 API、预检、确认、查询、重试和历史。
- sync_engine.py：目标事务写入、整数外键重映射、旧版本保留、映射和审计。
- tasks.py：现有 Celery 执行、租约、每30秒恢复、失联结果按原幂等键查询。
- MaterialProductionSync.vue：确认面板、差异、历史恢复、任务轮询；MaterialCatalogView 列表操作与状态。
- 0009：同步任务、nonce、包串行槽位和映射表；MaterialLibrary 新增 sync_materiallibrary 权限。

## 首次部署

1. 生产数据库先备份。用原 deploy_sparkservice.sh 发布兼容代码并执行迁移；默认 SYNC_DEPLOY_ENV=1，本地 .env 参与发布；脚本在候选副本将同步身份转换为 production / source=false / receiver=true，并将本地 KEY_ID/SECRET 配对登记为生产 ACCEPTED_KEYS。远端合并保留既有接收凭证；同名不同凭证阻断，轮换请使用新 KEY_ID。本地原文件不变，生产发送凭证清空。设置 SYNC_DEPLOY_ENV=0 可保留服务器其他配置。环境依据已校验 SSH 生产目标确定，不依据操作系统、主机名或用户输入的环境身份猜测。同步功能本身不会执行部署 shell。
2. 本地和生产均执行 `python manage.py migrate`，重启各自 API、现有 Celery worker、beat。恢复任务依赖 beat；生产 worker 必须加载新任务。
3. 生产配置 MATERIAL_SYNC_RECEIVER_ENABLED=true、MATERIAL_SYNC_ENVIRONMENT_ID=production、SOURCE_ENABLED=false；配置 ACCEPTED_KEYS。密钥通过受保护环境文件分发，建议至少32随机字节，不写入仓库或前端。
4. 本地配置 SOURCE_ENABLED=true、RECEIVER_ENABLED=false、ENVIRONMENT_ID=local-authoring、固定 TARGET_BASE_URL=https://diary.dreamwhale.top、KEY_ID和SECRET。KEY_ID对应生产ACCEPTED_KEYS中environment=local-authoring的记录。
5. 双方保持 ALIYUN_OSS_BUCKET、ENDPOINT 和 DIARY_PRESETS_OSS_PREFIX 一致；只读HEAD校验使用已有OSS配置，不新增图片处理节点。
6. 应用更新后的 Nginx 模板：同步接收路径限2MiB。应用中间件同样限制2MiB（含流式请求）；普通素材管理仍256KiB。
7. 给操作人员同时授予 material_library.sync_materiallibrary 和 publish_materiallibrary。超级管理员自动具备；不修改普通用户权限。
8. 后台刷新，查看环境/目标标识。在独立已发布包的更多菜单中点击同步到生产，先预检、再确认。生产下架、草稿、身份冲突和共享素材修改均阻断。

仅允许 diary.dreamwhale.top 或 39.106.39.110 的443 HTTPS，证书验证开启；固定域名的生产反代应保持指向允许服务器。不得修改配置指向139.196.215.51。

## 资源与版本

每个唯一资源一次HEAD，不GET图片。预检检查记录在同一生产任务内5分钟有效，确认仍有效时复用；超过5分钟重新HEAD。单次最多5个HEAD并行，生产最多2个同步任务持有执行租约。HEAD确认存在、长度和MIME，不代表服务端重新计算SHA256或审核图像内容。

同一快照重复导入不增加版本；生产版本独立递增，整数ID重新映射，UUID保留。保留生产推荐/排序/上新字段和旧版本、用户收藏；移出新包的素材不删除。首次遇到目标已存在不同内容且没有来源映射时阻断，不接管。

来源API不接收任意URL、数据库账号或图片文件。生产密钥仅能访问受限接收器。接收器验证时间窗±5分钟、nonce去重10分钟；轮换时生产可暂存两个key_id，再更新来源，最后移除旧key。

## 任务恢复

浏览器关闭后任务继续运行，重新打开包可读取历史恢复。网络中断先按原幂等键查生产结果，再考虑提交；连续3次网络失败停止自动重试，显示手动确认结果。beat恢复过期租约；手动确认会清零网络失败计数。

已提交后的失败为 committed_verification_pending；不会重复创建版本。生产内部验收检查可见性、快照和数量，来源通过生产HTTPS服务接口查询结果。真实iOS浏览/插入/保存/导出仍需生产业务验收，不能用单元测试替代。

失败重试：未提交事务回滚；无冲突可重新预检。存在冲突需先在生产处理，不提供强制覆盖。成功发版后撤回使用生产管理流程，不恢复整库备份。运行时不会删除任何OSS对象。

## 当前测试和运行边界

初始实现时默认关闭；2026-10-27 经用户授权，已部署至39.106.39.110并应用0009，双方服务身份已配置。与海见个面本地v2到生产v1的首次及重复同步通过，生产31项下载计划及OSS抽样哈希验证通过。完整记录见 docs/releases/2026-10-27-material-production-sync.md；真实iOS操作验收仍待完成。

当前实现使用一张任务表区分side=source/target，等价承载需求中的来源任务/生产回执；MaterialSyncSlot还使用全零UUID行作为目标并发租约锁。成功映射和任务结果保留，不会自动清理导致幂等键失效。未加90天快照自动清理（先保留审计）。

全目录替换脚本 sync_local_catalog.sh 不参与此流程；新的同步映射通过PROTECT保护历史版本。以后要执行全目录替换，必须先另行处理其对同步映射的兼容，不能直接删除映射绕过保护。
