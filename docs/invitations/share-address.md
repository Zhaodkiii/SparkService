# 邀请链接的环境归属

邀请接口返回 `invite_token`（UUID）和 `invite_path`（`/invite/<UUID>`）；未参与或无活动时为空。
iOS 使用发出邀请请求的 `SupportNetworkEngine.serviceBaseURL` 生成 URL，文案和二维码共用该 URL，不读取独立的分享域名配置。

旧客户端兼容字段 `link` 由服务端根据当前请求的域名和协议生成。反向代理必须保留 Host，正确传递 HTTPS 协议；Django ALLOWED_HOSTS 应限制为本环境可信域名。
旧服务端兼容：新客户端只提取旧 link 的 UUID，域名仍使用实际网络引擎地址。

`INVITATION_WEB_ORIGIN` 已不再使用，旧环境文件中的该变量可删除。无需修改邀请码和数据库；已发送的错误二维码无法自动更新，需重新生成。

验证：生产和开发请求分别返回自身域名；新客户端检查正式/开发地址、旧链接错误域名、空链接、无效 UUID。服务端升级后旧客户端刷新邀请页即可获得正确地址，新客户端逻辑需构建安装生效。
