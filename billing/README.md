# TravelDiary billing implementation

RevenueCat owns DIAMOND balances. SparkService stores verified wallet identities, immutable prices and quotes, durable debit/compensation operations, permanent content grants, top-up observations and audit evidence. Store purchases never trigger a second local currency grant. API adjustments are finalized from the provider response rather than waiting for a webhook.

## Configuration

Only the server reads `REVENUECAT_V2_SECRET` and `REVENUECAT_WEBHOOK_AUTH`. Keep both in ignored, mode-0600 environment configuration. The iOS application receives only the public SDK key and its opaque, expiring billing session.

Production gates default to false: `DIAMOND_RECHARGE_ENABLED`, `DIAMOND_REDEMPTION_ENABLED`, `DIAMOND_CUSTOMIZATION_ENABLED`, `MEMBERSHIP_SALES_ENABLED`. `BILLING_SANDBOX_SALES_ENABLED` enables test purchases only after the server verifies an Apple-signed AppTransaction in Sandbox. Client-supplied environment booleans are not accepted.

`REVENUECAT_CONFIRMED_REPLAY_SECONDS` remains zero until the provider's replay retention contract has been verified. An uncertain operation is retained for manual reconciliation instead of sending a new debit key. Do not reopen a wallet or compensate an unknown debit based only on a displayed balance.

## Local setup and recovery

Back up MySQL first; run `python manage.py migrate billing` then `python manage.py seed_billing_catalog`. New recharge mappings remain draft unless deliberately activated after checking the corresponding store products. The current local database has the confirmed three mappings active for sandbox verification; all production gates remain off.

The worker executes `billing.tasks.process_pending` every 30 seconds through Beat. `python manage.py process_billing_operations` is available for an explicit recovery sweep. All provider HTTP occurs outside database transactions. Operation rows retain request hashes, fixed idempotency keys and fencing leases.

The normal webhook is `/api/v1/billing/revenuecat/webhook/`. The dedicated sandbox endpoint is `/api/v1/billing/sandbox-webhook/`, which rejects production events. Both require an exact authorization header. The Nginx snippet in `deployment/billing/sandbox-webhook.nginx` forwards only the sandbox endpoint to the existing local FRP tunnel.

## Administration

`/billing` manages content policy drafts, publication impact checks, fixed customization package versions and operation/reconciliation lists. Publication binds the reviewed draft hash. A concurrent change requires a new review. Existing free content is seeded explicitly by migration 0002; missing policies fail closed. Existing free/Pro scope reductions require a separate migration plan.

Customization workbench displays immutable quotes and funding status. A quoted commission must be funded before production can start. Historical requests without billing quotes preserve the original flow. Billing permissions are registered in the existing RBAC catalog by migration 0005; ordinary operator roles require explicit permission assignment.

## Validation limits

See the client document `需求文档/商业化与会员/10-落地实施与沙盒联调记录.md` for the dated implementation/acceptance status. An official webhook TEST response does not verify a StoreKit purchase, a currency grant, spending, restoration, or refund behavior. Real-device sandbox purchase acceptance and remaining product requirements must pass before opening production sales.

## 后台交易查询

交易中心入口 `/billing/transactions`，实现及操作说明见 `docs/billing/transaction-center.md`。迁移 0007/0008 创建报表投影和独立权限；`backfill_billing_payments` 可将已处理回调回填为交易记录，不发钻。正式环境与沙盒环境分别查询。
