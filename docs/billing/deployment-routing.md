# 订阅环境隔离与可靠回调

## 环境边界

- Debug：`https://diary-dev.dreamwhale.top`，本机 API、本机账号和会员/额度数据库，`BILLING_DEPLOYMENT=development`。
- Staging / Production：`https://diary.dreamwhale.top`，线上服务，`BILLING_DEPLOYMENT=production`。
- Apple Sandbox / Production 是另一维度，由签名 AppTransaction 验证。线上支持两者；本地只接受 Sandbox 身份初始化。
- 客户端校验 bootstrap 的 deployment，环境不匹配时不登录 RevenueCat、不发起购买。新客户端依赖本次服务端版本。
- 不修改既有 rc_app_user_id、不跨数据库复制会员，不按账号整数 ID 合并身份。

## 身份路由

新建本地身份仍为 UUID v4，保留随机部分，前 8 个十六进制字符固定为 `d1a7de00`。该标记仅用于已鉴权事件的路由，不作为授权证据。线上身份继续随机生成。

开发环境仅按新身份标记路由，不保留旧 UUID 名单或迁移逻辑。已有未带标记的测试身份不再支持跨端转发；后续联调使用新测试账号。

## 回调流程

RevenueCat 应将事件发送到线上 `/api/v1/billing/revenuecat/webhook/`；既有线上 `/api/v1/billing/sandbox-webhook/` 仍可用，仅接收 Sandbox。实际 RevenueCat 控制台配置需单独核实，服务器配置不能证明控制台订阅了该地址。

1. 校验 RevenueCat Authorization、app_id 和事件 ID。
2. 线上先持久化 CurrencyEvent，已知开发身份同时建立唯一 WebhookDelivery。
3. 属于开发且线上无该身份：状态 forwarding，不进入线上权益处理。
4. 独立 Celery 任务 `billing-dev-delivery` 每 30 秒尝试转发，每批最多 5 条，HTTP 超时 10 秒；不会在 webhook 请求中等待网络。
5. 独立 `BILLING_RELAY_TOKEN` 鉴权；本机 `/api/v1/billing/relay-webhook/` 要求本机存在对应身份，否则 409，发送端继续保留。
6. 本机按事件 ID 去重，成功落库/处理后确认 received=true；线上记录 forwarded、delivered_at。
7. 本机离线、HTTP 错误、错误确认响应均保留事件，指数退避至最多一小时。发送前领取两分钟租约，进程崩溃后可重试；重复发送由接收端去重。
8. TRANSFER 同时涉及两端时，两端分别使其拥有的会员快照失效并重新查询；不复制余额、订单或内容所有权。

线上配置：`BILLING_DEV_RELAY_URL=https://diary-dev.dreamwhale.top/api/v1/billing/relay-webhook/`。两端共享独立转发 token；不得使用 RevenueCat webhook token 代替。

部署脚本始终将生产候选配置的 BILLING_DEPLOYMENT 设为 production，避免本地 .env 导致线上变成 development。

## 运维与补偿

Django Admin 中 WebhookDelivery 只读查看 attempts、last_status、next_attempt_at、delivered_at。CurrencyEvent 保留原始来源事件。

回滚时保持新增表和已记录事件，关闭转发定时任务即可暂停发送，不删除队列。客户端要求 deployment 字段存在且与编译环境一致。

## 恢复购买的边界（尚需 RevenueCat 控制台确认）

共享 RevenueCat 项目时，仅分开 UUID 不能保证 Apple 收据不会在恢复购买时被 RevenueCat 转移。必须分别使用测试 Apple 沙盒账号；如业务要求禁止用户间恢复转移，评估并设置 Restore Behavior = Keep with original App User ID。该设置同时影响线上用户换账号恢复购买，不应未经评估直接全项目切换。

官方说明：https://www.revenuecat.com/docs/projects/restore-behavior

当前实现没有自动合并身份，也没有修改 RevenueCat 控制台恢复策略。不能把这解释为平台层已经禁止跨环境转移。

## 验证记录（2026-11-15）

- 61 项 billing 测试通过：路由、线上 Sandbox 保留、重复事件、断网重试、接收鉴权、未标记身份不转发、跨端 TRANSFER、会员查询与交易回归。
- iOS Debug 模拟器构建通过。
- 本机数据库迁移 0013 执行成功，线上通过现有发布脚本备份、迁移、发布。
- 线上访问开发接口成功；正确转发 token + 未知身份返回 409，未写入虚假交易。
- 未执行新的 Apple 沙盒购买；本机离线重试由自动化测试覆盖。
