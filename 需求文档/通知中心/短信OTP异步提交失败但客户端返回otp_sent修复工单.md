# SparkService 短信 OTP 异步提交失败但客户端返回 `otp_sent` 修复工单

创建日期：2026-07-13  
关联模块：账户鉴权、短信 OTP、通知中心、阿里云短信、后台管理系统  
优先级：P0  
修复类型：接口语义错误 / 异步发送一致性 / OTP 生命周期错误 / 客户端误导

## 1. 背景

客户端调用：

```http
POST /api/v1/otp/phone/request/
```

请求体：

```json
{
  "provider_uid": "",
  "scene": "account_deactivation",
  "user_id": 813,
  "phone_number": "+8618255099136",
  "bundle_id": "cn.Zhaodk.Health",
  "device_id": "680783DA-E49E-4C68-BBE9-2939FFC7897F"
}
```

客户端收到：

```json
{
  "code": 0,
  "msg": "otp_sent",
  "data": {
    "otp_id": "3bbf5a82-7fd0-4728-b513-dab37445c515",
    "expires_in": 300
  }
}
```

但后台通知中心中，该短信实际为：

```text
template_code=SMS_508370089
status=failed
submit_status=failed
delivery_status=submit_failed
provider_code=isv.BUSINESS_LIMIT_CONTROL
error_message=isv.BUSINESS_LIMIT_CONTROL:触发分钟级流控Permits:1
```

也就是阿里云提交失败，但客户端已经被告知 `otp_sent`。

## 2. 结论

当前不是“完全没处理阿里云失败”，而是处理发生在异步 Worker 阶段，晚于 HTTP 响应。

当前链路的真实语义是：

1. `/api/v1/otp/phone/request/` 创建 `PhoneOTP`。
2. 创建通知中心 `NotificationIntent / NotificationMessage / NotificationOutbox`。
3. 接口立即返回 `200 + otp_sent`。
4. 事务提交后异步 Worker 才调用阿里云 `SendSms`。
5. 阿里云返回 `isv.BUSINESS_LIMIT_CONTROL` 后，通知中心记录被更新为 `submit_failed`。

因此问题是：HTTP 接口把“OTP 请求已排队”包装成了“短信已发送”，客户端会误以为验证码已经发送成功。

## 3. 当前代码链路

### 3.1 HTTP 入口

文件：

```text
accounts/otp/views.py
```

`PhoneOTPRequestView.post` 固定在 `OTPService.request_phone_otp` 成功返回后响应：

```python
return success_response(result, msg="otp_sent", code=0, status_code=status.HTTP_200_OK)
```

### 3.2 OTP 创建

文件：

```text
accounts/services/otp_service.py
```

`OTPService.request_phone_otp` 先创建 `PhoneOTP`，再调用：

```python
NotificationCenterService.send_phone_otp(...)
```

只要通知中心创建消息和 Outbox 成功，`send_phone_otp` 就返回：

```python
return True, "", str(message.id)
```

### 3.3 通知中心异步发送

文件：

```text
notification_center/services.py
```

`NotificationCenterService.send_phone_otp` 只创建：

- `NotificationIntent`
- `NotificationMessage(status=queued)`
- `NotificationOutbox(status=pending)`

随后通过事务提交钩子触发：

```python
transaction.on_commit(lambda: relay_notification_outbox_task.delay())
```

真正调用阿里云发生在：

```python
NotificationCenterService.execute_phone_otp_intent
```

也就是 HTTP 响应之后。

## 4. 问题影响

1. 客户端误判短信已成功发送，进入倒计时和验证码输入页。
2. 用户实际收不到验证码，体验表现为“系统说发了，但我没收到”。
3. 后台通知中心显示 `submit_failed`，但客户端请求已经是 `code=0`。
4. `PhoneOTP` 已经生成，在有效期内仍存在；虽然普通用户拿不到验证码，但从生命周期一致性上它不应该继续保持可用。
5. 对账号注销等敏感场景，短信提交失败必须明确反馈，不能让用户继续以为验证流程可继续。

## 5. 根因

### 5.1 接口语义与实现不一致

`otp_sent` 表示“验证码短信已发送”，但当前实现实际只保证“发送任务已创建”。

### 5.2 OTP 生命周期没有绑定短信提交结果

`PhoneOTP` 创建早于阿里云提交结果，且短信提交失败后没有反向更新或作废 `PhoneOTP`。

### 5.3 异步发送没有给客户端失败反馈路径

通知中心能落库 `submit_failed`，后台也能看到失败原因，但移动端没有：

- 同步失败响应
- 查询发送状态接口
- WebSocket/推送通知失败事件
- 自动作废并提示重新获取的机制

## 6. 修复目标

1. 对客户端不要再把“排队成功”伪装成“发送成功”。
2. 阿里云明确提交失败时，客户端必须能得到失败结果或可感知的失败状态。
3. 短信提交失败后，对应 `PhoneOTP` 必须失效，不能继续作为有效验证码存在。
4. 通知中心、OTP、客户端三方状态语义必须一致。
5. 对流控类错误给出可理解的客户端错误码和重试时间建议。

## 7. 推荐方案

### 7.1 P0 推荐：OTP 短信改为同步提交，提交成功后再返回 `otp_sent`

OTP 是强交互安全链路，不适合只返回“任务已排队”。建议对手机号 OTP 使用同步提交策略：

1. `OTPService.request_phone_otp` 生成验证码。
2. 调用通知中心同步发送方法，或在当前请求内执行 OTP 短信发送。
3. 阿里云返回 `Code=OK` 且拿到 `BizId` 后：
   - 创建或确认 `PhoneOTP` 有效
   - 返回 `200 + otp_sent`
4. 阿里云返回明确失败时：
   - 不返回 `otp_sent`
   - 作废或删除本次 `PhoneOTP`
   - 返回明确错误

建议错误映射：

| 阿里云错误 | HTTP | 业务 code | 客户端提示 |
|---|---:|---:|---|
| `isv.BUSINESS_LIMIT_CONTROL` | 429 | `42902` | 请求过于频繁，请稍后再试 |
| 配置缺失 / SDK 不可用 | 502 | `50231` | 短信服务暂不可用 |
| 网络超时 / 结果未知 | 202 或 503 | `20231` / `50331` | 正在确认发送结果，请稍后 |
| 其他提交失败 | 502 | `50232` | 验证码发送失败，请稍后重试 |

### 7.2 兼容方案：保留异步，但响应语义改为 `otp_queued`

如果必须保留异步发送，则接口不能继续返回 `otp_sent`。

响应应改为：

```json
{
  "code": 0,
  "msg": "otp_queued",
  "data": {
    "otp_id": "...",
    "message_id": 17,
    "expires_in": 300,
    "send_status": "queued"
  }
}
```

并新增状态查询接口：

```http
GET /api/v1/otp/phone/request/{otp_id}/status/
```

当通知中心状态变为：

- `accepted`：客户端进入验证码输入倒计时
- `submit_failed`：客户端停止倒计时，提示失败并允许重试
- `submit_unknown`：客户端显示确认中，限制重复请求

该方案改动面更大，客户端也要适配，所以不作为首选。

## 8. 必须补充的服务端处理

### 8.1 增加 `PhoneOTP` 发送状态字段

建议给 `PhoneOTP` 增加字段：

| 字段 | 说明 |
|---|---|
| `send_status` | `queued / accepted / submit_failed / submit_unknown` |
| `notification_message_id` | 关联通知中心消息 |
| `provider_request_id` | 阿里云 RequestId |
| `provider_biz_id` | 阿里云 BizId |
| `send_error_code` | 失败码 |
| `send_error_message` | 失败原因 |
| `invalidated_at` | 发送失败后作废时间 |

### 8.2 验证 OTP 时检查发送状态

`verify_phone_otp_and_issue_tokens` 必须拒绝：

- `send_status=submit_failed`
- `invalidated_at IS NOT NULL`
- `send_status=queued` 且超过合理等待窗口

否则会出现“短信发送失败但 OTP 记录仍被视为有效”的状态漏洞。

### 8.3 Worker 失败后反向更新 OTP

`execute_phone_otp_intent` 在阿里云提交失败时，应根据 `business_id=otp_id` 找到 `PhoneOTP`，更新：

```text
send_status=submit_failed
invalidated_at=now
send_error_code=isv.BUSINESS_LIMIT_CONTROL
send_error_message=触发分钟级流控Permits:1
```

## 9. 验收标准

1. 当阿里云返回 `isv.BUSINESS_LIMIT_CONTROL` 时，客户端不能收到 `msg=otp_sent`。
2. 同步方案下，接口应返回 `429` 或明确业务错误码。
3. 异步兼容方案下，接口只能返回 `otp_queued`，后续状态查询必须返回 `submit_failed`。
4. 后台通知中心显示 `submit_failed` 时，对应 `PhoneOTP` 也必须为失效状态。
5. 使用已失效 `otp_id` 调用 verify，必须返回明确失败，不得继续验证。
6. 日志必须能通过同一个 `request_id` 串起：
   - OTP 请求
   - 通知中心消息
   - 阿里云 RequestId
   - 提交失败原因

## 10. 测试用例

1. Mock 阿里云返回 `isv.BUSINESS_LIMIT_CONTROL`，断言 `/api/v1/otp/phone/request/` 不返回 `otp_sent`。
2. Mock 阿里云返回 `OK + BizId`，断言接口返回 `otp_sent` 且通知中心状态为 `accepted`。
3. Mock 阿里云超时，断言返回 `submit_unknown` 或“确认中”语义，不能伪装成已发送。
4. 提交失败后，用该 `otp_id` 调用 verify，断言失败。
5. 后台短信列表展示 `submit_failed`，并且 `PhoneOTP.send_status=submit_failed`。

## 11. 迁移与兼容

1. 历史 `PhoneOTP` 没有发送状态，迁移时可默认 `send_status=accepted` 或 `unknown`，以避免破坏历史登录记录。
2. 对新版本客户端，优先切换到同步提交方案。
3. 如果短期无法改客户端，服务端仍应至少在 Worker 失败时作废 `PhoneOTP`，避免失败验证码继续有效。

## 12. 备注

这次问题与短信回执查询无关。回执查询发生在供应商已受理后，用于确认运营商最终送达；本问题发生在更早的提交阶段，即阿里云 `SendSms` 已明确返回提交失败。

## 13. 已实施技术方案

### 13.1 手机号 OTP 改为同步提交

`NotificationCenterService.send_phone_otp` 增加 `dispatch_sync` 参数，手机号 OTP 请求默认使用：

```python
dispatch_sync=True
```

同步模式下仍然创建通知中心台账：

- `NotificationIntent`
- `NotificationMessage`
- `NotificationOutbox`
- `ChannelDelivery`
- `ProviderEvent`

区别是：创建消息后立即在当前请求内执行 `execute_phone_otp_intent`，等阿里云 `SendSms` 返回后再决定是否向上返回成功。

如果阿里云返回：

```text
Code=OK
BizId 非空
```

服务端返回 `otp_sent`。

如果阿里云返回：

```text
isv.BUSINESS_LIMIT_CONTROL
```

服务端返回业务失败，不再返回 `otp_sent`。

### 13.2 保留异步兼容能力

为了兼容通知中心内部队列能力，`dispatch_sync=False` 仍保留旧行为：

```python
NotificationCenterService.send_phone_otp(..., dispatch_sync=False)
```

该模式只创建 Outbox 并由 Celery 后续投递，主要用于测试、内部任务或未来需要恢复异步的场景。

### 13.3 `PhoneOTP` 增加发送状态字段

新增迁移：

```text
accounts/migrations/0005_phone_otp_send_state.py
```

新增字段：

| 字段 | 说明 |
|---|---|
| `send_status` | `queued / accepted / submit_failed / submit_unknown / unknown` |
| `notification_message_id` | 对应通知中心 `NotificationMessage.id` |
| `provider_request_id` | 阿里云 `RequestId` |
| `provider_biz_id` | 阿里云 `BizId` |
| `send_error_code` | 提交失败码 |
| `send_error_message` | 提交失败详情 |
| `invalidated_at` | 发送失败或不可用时的作废时间 |

### 13.4 OTP 状态流转

正常成功：

```text
PhoneOTP.send_status=queued
  -> Aliyun SendSms OK
  -> PhoneOTP.send_status=accepted
  -> API 返回 otp_sent
```

阿里云明确失败：

```text
PhoneOTP.send_status=queued
  -> Aliyun SendSms failed
  -> ChannelDelivery.status=submit_failed
  -> PhoneOTP.send_status=submit_failed
  -> PhoneOTP.invalidated_at=now
  -> API 返回错误
```

提交结果未知：

```text
PhoneOTP.send_status=queued
  -> provider timeout / unknown
  -> ChannelDelivery.status=submit_unknown
  -> PhoneOTP.send_status=submit_unknown
  -> PhoneOTP.invalidated_at=now
  -> API 返回 sms_send_unknown
```

白名单固定验证码：

```text
PhoneOTP.send_status=accepted
```

白名单不真实发送短信，但服务端明确认可该验证码可用于测试。

### 13.5 客户端错误码映射

手机号 OTP 请求中，短信提交失败按以下规则抛出：

| 场景 | HTTP | 业务 code | msg |
|---|---:|---:|---|
| 阿里云业务流控 `isv.BUSINESS_LIMIT_CONTROL` | 429 | `42902` | `sms_send_rate_limited` |
| 本地 OTP 请求频控 | 429 | `42901` | `otp_requested_too_frequently` |
| 提交结果未知或超时 | 503 | `50331` | `sms_send_unknown` |
| 短信服务不可用或其他提交失败 | 502 | `50231` | `sms_send_failed` |

响应体约定改为：

- `msg` 返回稳定错误 key，供移动端做本地化。
- `data.reason` 返回原始原因，供客户端日志、客服和服务端排查。
- `data.error_type` 与 `msg` 保持一致，便于客户端保留旧解析逻辑。
- `data.request_id` 始终透传，便于问题定位。

```json
{
  "code": 42902,
  "msg": "sms_send_rate_limited",
  "data": {
    "error_type": "sms_send_rate_limited",
    "reason": "isv.BUSINESS_LIMIT_CONTROL:触发天级流控Permits:10",
    "request_id": "AB49292E-55CD-45F1-B9A4-FFA5BD5911E0"
  }
}
```

移动端展示优先级建议：

```text
本地化文案映射(msg) -> data.reason 仅用于日志/诊断页
```

其中 `error_type` 保留给客户端做分支处理，例如命中 `sms_send_rate_limited` 时可以禁用“重新发送”按钮或展示倒计时。

### 13.6 验证阶段硬检查

`verify_phone_otp_and_issue_tokens` 增加检查：

```text
invalidated_at IS NOT NULL -> 拒绝
send_status in queued/submit_failed/submit_unknown -> 拒绝
```

账号注销服务 `DeactivationService._verify_otp_row` 同步增加相同检查，避免注销流程绕过登录 verify 入口。

### 13.7 通知中心反写 OTP

`execute_phone_otp_intent` 在以下路径反写 `PhoneOTP`：

- 已存在终态投递记录
- OTP 已过期
- Worker 中断后状态未知
- 阿里云提交成功
- 阿里云提交失败

反写依据：

```text
NotificationIntent.business_id == PhoneOTP.otp_id
```

这样可以通过同一个 `otp_id/request_id` 串起：

- 客户端 OTP 请求
- `PhoneOTP`
- `NotificationMessage`
- `ChannelDelivery`
- 阿里云 `RequestId/BizId`

### 13.8 回归测试

已补充并通过：

```bash
python manage.py test accounts.tests_phone_otp notification_center.tests.NotificationCenterServiceTests -v 1
python manage.py test accounts.tests_deactivation_service accounts.tests_device_session -v 1
```

重点覆盖：

1. 阿里云返回 `isv.BUSINESS_LIMIT_CONTROL` 时，服务端返回 429，不返回 `otp_sent`。
2. 提交失败的 `PhoneOTP` 被标记为 `submit_failed` 并写入 `invalidated_at`。
3. 已作废 OTP 不能通过 verify。
4. 白名单固定验证码仍可正常验证。
5. 原异步 Worker 路径仍保留并可工作。
