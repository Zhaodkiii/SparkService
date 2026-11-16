# 邀请页重设计与登记验证

## 设计

旧页的问题：整段活动规则抢占首屏；主标题、说明、规则、表单权重不清；下拉菜单隐藏登记方式；缺少品牌主视觉；未验证联系方式即可登记；登记后自动跳转，用户无法确认结果。

新页使用暖白纸色、陶土色按钮、旅行手帐主视觉。桌面双栏，手机单栏。表单优先，手机号/邮箱直接切换；奖励摘要明确标注属于邀请人，完整规则折叠。验证通过展示成功页，由用户主动前往 App Store。截止时间明确使用北京时间。

## 素材

- 生成方式：内置 imagegen（未使用 CLI）。
- 原始图片：`docs/invitations/assets/travel-journal-original.png`
- 页面使用：`public-web/src/assets/invitation/travel-journal.webp`，约 72 KB；Vite 导入生成 `/public-assets/` 哈希资源，与现有 Nginx 路由兼容。
- 验收截图：`docs/invitations/assets/invitation-desktop.jpg`、`invitation-mobile.jpg`。截图使用隔离数据库测试活动，不是线上数据。

完整生成提示词：

> Use case: ads-marketing. Asset type: compact hero illustration for a minimalist Chinese travel diary friend invitation landing page. Create a refined editorial still-life of an open ivory travel scrapbook with two small photographic prints of a peaceful mountain lake and an old-town street, one terracotta travel ticket and a tiny sage-green leaf, arranged with generous negative space. Warm off-white background #faf8f4, soft natural shadows, muted sage and terracotta, tactile fine paper, understated premium stationery photography with gentle illustrative styling. Landscape 3:2 composition, objects centered and fully visible, no text, no lettering, no logos, no watermark, no UI. This is one reusable website artwork, not a screenshot.

## 登记协议

1. `POST /api/public/v1/invitations/{token}/code/`：`contact_kind`、`contact`、`consent: true`。返回 `challenge_id`、`resend_after: 60`、`expires_in: 300`。
2. `POST /api/public/v1/invitations/{token}/`：同上，另需 `challenge_id` 和 6 位 `code`。服务端校验通过后才能创建登记，返回 `awaiting_app`。
3. 验证码隔离于登录验证码，不创建账号或令牌，不提前计入奖励。App 身份验证与原有归因规则保持原逻辑。

验证码绑定邀请链接和规范化联系方式。只持久化联系方式 HMAC 与验证码密码哈希；单次消费；5 分钟有效；60 秒重发；每个联系方式滚动 24 小时最多发送 10 次；每个验证码最多错误 5 次。以数据库行锁串行化同一联系方式的发送与验证，跨邀请链接共享发送预算。保留现有 IP 限流。发送失败也记录冷却，失败的验证码不能验证。上线环境应使用支持行锁的现有数据库；SQLite 单元测试未验证多进程并发。

## 短信与邮件

2026-11-16 通过用户已打开的阿里云控制台核对：

- 「登陆短信模版」`SMS_508370089`，已通过、正常。
- 签名 `梦原鲸苏州科技服务`，可用。
- 内容：`您的验证码：${code}，您正在进行身份验证，请勿泄露于他人！`
- 模板支持 4–6 位数字，本功能使用 6 位。

短信复用 `AliyunSMSProvider.send_login_code`、`ALIYUN_SMS_OTP_TEMPLATE_CODE` 与 `ALIYUN_SMS_SIGN_NAME`，没有新建或修改云端模板。仅支持大陆手机号，其他地区使用邮箱。已检查本地配置匹配上述模板且 SDK/密钥配置就绪，未输出密钥。

邮件通过 Django `send_mail` 调用项目现有 SMTP backend，使用既有 `EMAIL_*` 与 `DEFAULT_FROM_EMAIL` 配置。内容明确为邀请登记验证码；禁止 console/dummy/file backend 假报发送成功。测试使用独立 locmem backend。已确认本地 SMTP 用户及密码已配置，尚未向真实收件人实发验证。

## 上线与验证

- 先执行 `python manage.py migrate public_experience`，新增 `0003_invitationotp`，然后发布后端及 `public-web` 构建产物。
- 旧无验证码 POST 将返回 400，前后端应同次发布。
- `manage.py test public_experience.tests_invitations public_experience.tests_invitation_otp --settings=SparkService.test_settings --noinput`：25 项通过。
- `npm --prefix public-web run build`：通过。
- `manage.py makemigrations --check --dry-run --noinput`：无遗漏迁移。
- 浏览器验收桌面与 390px 手机布局，邮箱切换、禁用态、无横向溢出。
- 未部署线上，未对实际业务数据库执行迁移，未进行真实短信/邮件实发。上线后需以测试手机号、邮箱完成各一次投递与登记验收。
