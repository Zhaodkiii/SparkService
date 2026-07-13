# 通知中心日志治理与 QuerySendDetails 日志修复工单

## 1. 背景

后台短信发送记录点击“查询回执”时，接口实际已经调用阿里云 `QuerySendDetails`，但运行日志存在两个问题：

1. 只能在控制台看到 `accounts.infrastructure.sms_provider` 的 begin/result 日志，通知中心服务层日志缺失。
2. 日志文件目录下没有独立的 `notification_center.log`，通知中心业务日志无法按模块归档排查。
3. 当前 console 文本格式只输出 `message`，`extra` 中的 `biz_id`、`provider_request_id`、`normalized_status`、`duration_ms` 等结构化字段不会显示，导致日志看起来只有 `begin/result`，缺少可排查信息。

## 2. 问题原因

### 2.1 `notification_center` 未配置专属 logger

`SparkService/settings.py` 中已配置 `accounts`、`accounts.request`、`accounts.api_io`、`chat_sync`、`medical.flow`、`file_manager` 等 logger，但没有配置 `notification_center`。

因此 `notification_center.services` 使用 `logging.getLogger(__name__)` 打出的日志没有稳定写入业务日志文件。

### 2.2 短信 Provider 位于 `accounts.infrastructure`

短信 Provider 当前文件为：

```text
accounts/infrastructure/sms_provider.py
```

logger 名称是：

```text
accounts.infrastructure.sms_provider
```

该日志属于通知中心短信链路，但按 logger 命名会落在 `accounts` 体系下，不利于在通知中心排障时集中查看。

### 2.3 文本日志不展示 `extra`

当前 `console` formatter：

```text
%(levelname)s %(asctime)s %(name)s [request_id=%(request_id)s] %(message)s
```

只展示 `message`。如果业务字段只放在 `extra={...}`，文本日志不会显示这些字段。JSON 格式能保留字段，但本地默认 `LOG_FORMAT=console`，所以开发调试看不到关键参数。

## 3. 修复目标

1. 新增通知中心专属日志文件：

```text
logs/YYYY-MM-DD/notification_center.log
```

2. `notification_center` 模块日志同时写入：

```text
notification_center.log
app.log
console
```

3. `accounts.infrastructure.sms_provider` 的短信 Provider 日志同时写入：

```text
notification_center.log
app.log
console
```

4. `QuerySendDetails` 日志在 console 文本格式下也必须直接可读，不能只依赖 `extra`。

## 4. 已实施修改

### 4.1 日志路由

在 `SparkService/settings.py` 新增 handler：

```text
notification_center_file -> notification_center.log
```

新增 logger：

```text
notification_center
accounts.infrastructure.sms_provider
```

其中 `accounts.infrastructure.sms_provider` 设置 `propagate=False`，避免同时被 `accounts` 父 logger 重复写入。

### 4.2 服务层日志

在 `NotificationCenterService.query_sms_send_details_for_message` 增加：

```text
notification.sms.query_send_details.begin
notification.sms.query_send_details.result
notification.sms.query_send_details.failed
```

文本日志直接包含：

```text
message_id
delivery_id
biz_id
phone_number
send_date
operator_user_id
provider_request_id
provider_code
provider_status
normalized_status
reason
```

### 4.3 Provider 层日志

在 `AliyunSMSProvider.query_send_details` 增加：

```text
aliyun.sms.query_send_details.begin
aliyun.sms.query_send_details.result
aliyun.sms.query_send_details.failed
```

文本日志直接包含：

```text
biz_id
phone_number
send_date
current_page
page_size
duration_ms
provider_request_id
provider_code
provider_status
total_count
normalized_status
reason
```

## 5. 验收标准

点击后台页面：

```text
/notifications/sms
```

选择短信记录后点击“查询回执”，应同时看到以下日志：

```text
logs/YYYY-MM-DD/notification_center.log
logs/YYYY-MM-DD/app.log
控制台
```

关键日志示例：

```text
notification.sms.query_send_details.begin message_id=10 delivery_id=9 biz_id=415416983891345679^0 phone_number=15385056020 send_date=20260712 operator_user_id=1
aliyun.sms.query_send_details.begin biz_id=415416983891345679^0 phone_number=15385056020 send_date=20260712 current_page=1 page_size=10
aliyun.sms.query_send_details.result biz_id=415416983891345679^0 phone_number=15385056020 send_date=20260712 duration_ms=203 provider_request_id=019F5859-360C-55AF-8125-BF92F0A9AD6F provider_code=OK provider_status=accepted total_count=0 normalized_status=accepted reason=-
notification.sms.query_send_details.result message_id=10 delivery_id=9 biz_id=415416983891345679^0 normalized_status=accepted provider_request_id=019F5859-360C-55AF-8125-BF92F0A9AD6F provider_code=OK provider_status=accepted reason=-
```

## 6. 后续建议

1. 将 SMS Provider 从 `accounts.infrastructure` 迁移到 `notification_center` 专属 Adapter 目录，避免领域归属混乱。
2. 本地开发可继续使用 `LOG_FORMAT=console`，生产和集中采集建议使用 `LOG_FORMAT=json`。
3. 后续 SendSms、APNs、Email Provider 调用应统一采用 `begin/result/failed + request_id + provider_request_id + duration_ms` 的日志规范。
