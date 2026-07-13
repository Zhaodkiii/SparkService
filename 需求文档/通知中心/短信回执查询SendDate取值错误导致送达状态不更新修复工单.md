# SparkService 短信回执查询 `SendDate` 取值错误导致送达状态不更新修复工单

创建日期：2026-07-13  
关联模块：通知中心、短信发送记录、阿里云短信回执查询、后台管理系统  
优先级：P0  
修复类型：状态更新错误 / 回执查询参数错误 / 送达状态不一致

## 1. 背景

后台管理系统中，管理员在短信发送记录详情页点击“查询回执”后，接口已经正常返回 `200`，阿里云 `QuerySendDetails` 也实际返回了最终送达结果，但本地记录的“送达状态”和“回执状态”没有更新为已送达，仍停留在 `accepted / pending`。

本次问题的复现日志如下：

```text
INFO aliyun.sms.query_send_details.begin biz_id=415416983891345679^0 phone_number=15385056020 send_date=20260712 current_page=1 page_size=10
INFO aliyun.sms.query_send_details.result biz_id=415416983891345679^0 phone_number=15385056020 send_date=20260712 ... normalized_status=accepted total_count=0
```

但你提供的阿里云实际查询结果中，使用同一个 `PhoneNumber` 和 `BizId`，只要把 `SendDate` 传成 `20260713`，即可查到回执：

```json
{
  "TotalCount": 1,
  "Code": "OK",
  "SmsSendDetailDTOs": {
    "SmsSendDetailDTO": [
      {
        "PhoneNum": "15385056020",
        "SendDate": "2026-07-13 05:22:25",
        "ReceiveDate": "2026-07-13 05:22:29",
        "SendStatus": 3,
        "ErrCode": "DELIVERED"
      }
    ]
  }
}
```

这说明问题不是“阿里云没有回执”，而是系统查询回执时传错了 `SendDate`，导致查不到同一天的最终回执，所以本地状态没有被更新。

## 2. 问题现象

### 2.1 后台页面表现

1. 在通知中心短信记录列表中选择一条记录。
2. 点击“查询回执”。
3. 接口返回成功，页面提示“已查询并更新短信回执状态”。
4. 但列表里的：
   - 送达状态没有变成“已送达”
   - 回执状态没有变成最终状态
   - 详情里的回执时间也没有更新到阿里云实际返回值

### 2.2 日志表现

系统当前发起查询时打印的 `send_date` 是 `20260712`，而实际应查询的日期是 `20260713`。

这类误差在跨时区、跨零点发送、或 `created_at` 与真实发送时间不一致时最容易出现。

## 3. 根因分析

### 3.1 手工查询回执使用了错误的日期源

在 [`notification_center/services.py`](../../notification_center/services.py) 的 `query_sms_send_details_for_message` 中，当前传给阿里云的 `send_date` 来自：

```python
delivery.created_at
```

对应代码位置：

```python
query_result = AliyunSMSProvider.query_send_details(
    phone_number=query_phone,
    biz_id=delivery.provider_message_id,
    send_date=delivery.created_at,
    current_page=1,
    page_size=10,
    request_id=request_id or "",
)
```

但 `created_at` 是记录创建时间，不是短信真实发送时间。对于短信回执查询，阿里云要求的 `SendDate` 应使用原发送日期，而且国内短信应按业务时区 `Asia/Shanghai` 解释。

### 3.2 定时回执同步也存在同样问题

在同一文件的回执轮询逻辑里，`poll_pending_sms_deliveries` 也使用了：

```python
send_date=delivery.created_at
```

因此这个问题不只影响后台手工点击“查询回执”，也会影响自动回执同步任务。

### 3.3 误差会直接导致状态保持在 `accepted/pending`

当 `SendDate` 传错后，阿里云可能返回：

- `TotalCount=0`
- `normalized_status=accepted`

本地逻辑会把这类结果视为“暂未生成回执”，于是不会把状态推进到 `delivered`。

所以从用户视角看，就是“查询回执点了，但送达状态没更新”。

## 4. 影响范围

1. 后台短信记录列表的送达状态展示不准确。
2. 短信详情页的回执时间、回执状态不准确。
3. 自动轮询回执任务可能长期查不到实际已送达短信。
4. 运营/客服排障时会误判为“短信没送达”。

## 5. 修复目标

1. 查询回执时不再使用 `delivery.created_at` 作为 `SendDate`。
2. 改为使用短信真实发送日期来源，例如：
   - `sent_at`
   - 或已经记录下来的供应商发送时间
   - 必要时统一做业务时区转换后再截取 `yyyyMMdd`
3. 手工查询和自动同步复用同一套日期计算逻辑，避免两条链路不一致。
4. 阿里云返回 `DELIVERED` 时，本地必须更新：
   - `delivery.status`
   - `delivery.delivered_at`
   - `message.status`
   - `message.delivered_at`
   - `provider_request_id / provider_code / provider_status`
5. 增加回归测试，覆盖跨午夜发送、UTC/本地时区偏移和已有回执命中场景。

## 6. 修复方案

### 6.1 新增统一的回执查询日期计算方法

建议在 `NotificationCenterService` 中新增类似方法：

```python
@staticmethod
def _sms_receipt_query_send_date(delivery: ChannelDelivery) -> datetime:
    ...
```

优先级建议：

1. 优先使用 `delivery.sent_at`
2. 其次使用 `delivery.message.sent_at`
3. 仅在历史兼容场景下回退到 `delivery.created_at`

并且在输出 `SendDate` 前，统一转换为业务时区后再取日期：

```python
timezone.localtime(..., timezone=ZoneInfo("Asia/Shanghai"))
```

### 6.2 手工“查询回执”改用统一方法

将 `query_sms_send_details_for_message` 中的：

```python
send_date=delivery.created_at
```

改为统一的查询日期。

同时日志里也要打印：

- 实际使用的查询日期
- 日期来源字段
- 是否发生了回退

这样后续排障不会再次猜错。

### 6.3 自动回执同步改用同一日期逻辑

`poll_pending_sms_deliveries` 中也要同步替换，避免：

- 手工查询能更新
- 定时任务查不到

或者反过来。

### 6.4 查询到 `DELIVERED` 后确保落库字段完整

当 `QuerySendDetails` 返回：

- `SendStatus=3`
- `ErrCode=DELIVERED`

本地必须更新为：

| 字段 | 期望值 |
|---|---|
| `ChannelDelivery.status` | `delivered` |
| `ChannelDelivery.delivered_at` | 运营商回执时间 |
| `NotificationMessage.status` | `delivered` |
| `NotificationMessage.delivered_at` | 同上 |
| `provider_request_id` | 查询请求 ID |
| `provider_status` | 供应商回执状态 |
| `provider_code` | `DELIVERED` 或供应商返回码 |

### 6.5 增加回归测试

至少补三类用例：

1. 发送时间与创建时间跨天，查询应使用真实发送日期。
2. 阿里云返回 `SendStatus=3 / ErrCode=DELIVERED` 时，本地状态更新为 `delivered`。
3. 手工查询和自动同步使用相同的日期计算结果。

## 7. 验收标准

1. 使用你提供的真实样例复测时，查询回执应命中阿里云返回的 `DELIVERED` 记录。
2. 后台短信记录的“送达状态”更新为“已送达”。
3. 详情页能显示正确的回执时间。
4. `query_send_details` 的日志里可以看出实际查询日期来自哪一个字段。
5. 自动回执同步任务与手工查询结果一致。

## 8. 关联代码位置

- [`/Users/hua/Downloads/Reference/SparkService/notification_center/services.py`](../../notification_center/services.py)
- [`/Users/hua/Downloads/Reference/SparkService/accounts/infrastructure/sms_provider.py`](../../accounts/infrastructure/sms_provider.py)
- [`/Users/hua/Downloads/Reference/SparkService/backoffice-web/src/views/NotificationLogsView.vue`](../../backoffice-web/src/views/NotificationLogsView.vue)

## 9. 备注

这个问题和日志治理工单不是同一个问题。日志治理只会让“看起来更清楚”，但不会修复“查询日期传错导致查不到回执”。

因此这次修复的核心是：把 `SendDate` 的来源修正为真实发送日期，并保证手工查询与定时同步共用同一逻辑。
