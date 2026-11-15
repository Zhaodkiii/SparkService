# 购买统一接入线上服务

2026-11-14 生效。Debug、Staging、Production 客户端均访问 `https://diary.dreamwhale.top`。

## 路由与环境

- 正式/通用回调：`/api/v1/billing/revenuecat/webhook/`。
- 沙盒回调：`/api/v1/billing/sandbox-webhook/`，仍拒绝正式事件。
- 两个入口均指向线上 SparkService `127.0.0.1:12026`，不再使用本地 FRP `22026`。
- RevenueCat 已配置的沙盒回调 URL 可以保留；线上 Nginx 已修正 upstream。
- 服务端继续验证 Apple 签名确定 sandbox/production。统一服务不混合钱包、会员身份和正式收入统计。
- Nginx 通用 `/api/` 配置已指向线上；如保留专用沙盒 location，使用 deployment/billing/sandbox-webhook.nginx，不能恢复旧隧道地址。

## 本次排查与验证

线上原先没有任何回调事件，也没有交易 2000001265781320；该交易在本地账户 ID 4 下。对应 RevenueCat 用户 d116…3f37 有有效沙盒会员，线上当前用户 65a9…4589 的权益和订阅均为空。证明除回调路由外，旧购买与线上身份也不一致。

已备份线上 Nginx 配置，修改唯一的 22026 upstream 为 12026，nginx -t 通过并 reload。使用线上配置的鉴权头向两个公网入口发送 TEST 事件，均返回 HTTP 200、received=true。TEST 仅验证入口/鉴权，不代表真实购买恢复完成。

## 已有沙盒购买恢复

1. 使用连接线上服务的客户端登录正确账号。
2. 在会员页点击“恢复购买”，客户端先 bootstrap 并登录线上签发的 RevenueCat App User ID，再执行 restorePurchases，最后强制刷新线上会员状态。
3. 能否转移已有购买取决于 RevenueCat 项目的 restore/transfer 设置；若拒绝转移，应核查配置及 Apple 测试账号归属，不要重复购买或直接在数据库手工授予会员。
4. 在线上交易中心选择“沙盒环境”核对新事件、身份与会员状态。历史回调不会因路由修改自动迁移，交易报表可能不包含此前只投递到本地的历史记录。
5. 验收一次沙盒购买/恢复及回调处理，确认线上会员 active=true，Pro 额度正确；正式事件仍按 production 隔离。

本次没有复制本地用户、交易或手动转移会员，已有购买的真机恢复仍待执行。
