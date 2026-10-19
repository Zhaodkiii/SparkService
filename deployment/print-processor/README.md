# 实体印制部署与验证

2026-10-19。代码已接入，正式售卖仍需实际打样、业务配置及真实环境联调。

## 数据及后台

在 API 项目环境执行：

```sh
python manage.py migrate print_orders
python manage.py seed_print_products
```

种子命令幂等创建 A5（148×210mm）、ISO B5（176×250mm），启用免费印制，初始运费为 0。不会覆盖已有配置，不伪造纸张、工艺、打样状态或售后条款。后台 `/print-orders` → 印制规格中补全后启用。

免费模式忽略基础费及内页面单价，运费独立计价。总价 0 的订单使用 `not_required` 支付状态；客户端确认上传完成后自动待审核，不创建微信交易，也不创建退款。运费大于 0 则仍使用微信支付。历史订单金额为快照，不随商品修改变化。

后台操作包含审核、下载 PDF、要求原订单修改重提、开始制作、质检、异常处理、发货及售后。

## 文件传输（2026-10-19 最新方案）

服务器不连接 OSS，不进行 HEAD、下载、文件内容校验、分片初始化/查询/合并、打包或删除。仅在本地生成短期签名并保存订单。无需部署文件处理器，内部处理器接口及清理定时任务已取消。

客户端检查 PDF 页数、尺寸、加密与旋转状态和本地摘要，直接向 OSS 初始化分片、查询已上传分片、上传和合并；持久化 UploadId 与完成角色支持续传。完成两个 PDF 后提交 client_confirmed、completed_roles 和 production_id；免费或已支付订单进入待人工审核，未付款单仍需付款。

后台浏览器通过短期签名直接预览、下载封面和内页 PDF，生产说明在浏览器本地生成；不提供服务器 ZIP。staging 目录现在存放正式生产原稿，不能沿用自动删除整个 staging 前缀的短期生命周期规则。可清理未完成分片；已完成对象须按订单及售后保留期限制定存储侧策略。

本次接口需要与新版 iOS 同步发布；旧版客户端不再支持新的上传完成协议。发布时停止旧文件处理器并重启 API 和 Celery。人工印前审核继续保留。

## 微信支付

总价为 0 无需微信配置。收费订单使用 API v3 普通商户 APP 支付、公钥验签模式。`wechat.env.example` 列出服务端配置；密钥文件只部署在服务端。公钥 ID 和 PEM 从微信商户平台获得，支持轮换时切换对应配置。

公开 HTTPS 回调 `/api/v1/print/wechat-notify/`。回调验证签名、时间戳、公钥 ID，AES-GCM 解密，再检查 appid、mchid、商户单号、币种、金额和交易流水。不能由客户端确认支付。

已注册 Celery Beat 每分钟任务 `print_orders.tasks.reconcile_payments` 处理支付查询、过期关单和退款。Beat 与消费 `celery` 队列的 worker 需重启加载新任务；也可手动执行：

```sh
python manage.py reconcile_print_payments
```

退款为当前整单全额退款，异步结果由查单确认。异常退款保留状态，需要商户侧处理；禁止人工直接改成退款成功。

## iOS

已链接腾讯官方 WechatOpenSDK 2.0.9 XCFramework，并接入 PayReq、URL 回跳和 Universal Link 回跳。设置构建变量 `WECHAT_APP_ID`、`WECHAT_UNIVERSAL_LINK`。在签名配置添加对应 Associated Domains（applinks 域名），部署该域名的 apple-app-site-association；必须与微信开放平台的 Bundle ID、Universal Link 完全一致。不得使用示例域名正式签名。

正式微信支付必须在真机、微信及已开通 APP 支付商户环境验证。缺少配置或未安装微信时会显示不可支付，不模拟支付成功。

## 首期生产限制

独立正封面与封底，不支持书脊展开、额外出血和 CMYK/PDF-X 自动转换；内页按阅读顺序交付，双面时补尾部空白面。用户必须预览最终 PDF 并确认。缺失字体阻断，低清及复杂照片槽位提示检查；人工审核仍需要核对裁切、安全区和颜色。

客户端分片为 5 MiB，恢复时按 OSS 已上传分片续传，且先检查本地 PDF SHA-256。后台下载不自动开工。导出冻结来源文件，原作品修改或删除不改变已生成生产稿。

## 验证

```sh
python manage.py test print_orders --settings=SparkService.test_settings
cd backoffice-web
npm run build
```

包含订单去重、越权、价格校验、免费流程、取消、生产状态、微信验签及文件校验测试。完整 iOS 测试目标中原有 XCTest 存在 Swift 6 actor 隔离编译问题；本次印制、PDF 和图片导出测试使用聚焦测试构建执行，不改变无关测试源码。


## 修改重提

客户端在原订单重提，服务端固定原作品、尺寸规格、页数、份数和总价；已付款单无需再次付款。新稿使用新的生产标识，完成客户端直传后回到待审核。服务器不再删除旧 OSS 对象。线下已下载旧稿需由工作人员作废。

审核、开工和质检接口必须提交 checklist 与 production_id；上传授权及完成上传也必须提交当前 production_id。服务器保留身份、订单归属、价格、状态及版本一致性检查，这些不涉及文件下载或 OSS 请求。
