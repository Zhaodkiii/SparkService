# 实拍素材与分享封面（2026-11-16）

用户提供的 13 个 JPG 文件经 SHA-256 核对为 8 张独立原图，带 ` 2` 后缀的文件均为完全相同副本，未改动或删除原文件。本次选取 IMG_6692.JPG 作为主视觉、IMG_6699.JPG 作为实物结构辅助参考；并非为全部 8 张照片分别生成版本。

## 交付素材

- 高清横版主视觉：`assets/from-photos/invitation-hero.png`（1536×1024）。
- 高清方形分享封面：`assets/from-photos/wechat-share-cover.png`（1254×1254）。
- 网页主视觉：`public-web/src/assets/invitation/travel-journal-photo.jpg`。
- 网页分享封面：`public-web/public/public-assets/invitation/share-cover-v1.jpg`（1024×1024）。部署地址：`https://diary.dreamwhale.top/public-assets/invitation/share-cover-v1.jpg`。
- iOS 图片资源：TravelDiary 项目 `Assets.xcassets/InvitationShareCover.imageset/cover.jpg`（600×600）。
- 网页 Logo：直接取自用户指定的 `Logo/寻寻仔-AppIcon-1024.png`，缩小为 128×128，未重新设计图形。

两张创意素材均由内置 imagegen 基于原图生成，属于 AI 辅助产品展示图，不是逐像素原图抠图。纸页小字、照片细节可能存在生成差异。仅使用 sips 生成部署用缩小/压缩版本；高清生成稿保留。旧主视觉未删除。

## 分享接入

iOS 原入口分享的是拼接长文案字符串，现在改为 URL 类型 ShareLink，并传入 SharePreview 标题与 InvitationShareCover 图片。

网页新增独立 `invite.html`，在初始 HTML 提供 og:title、og:description、og:image 与 image_src，避免仅用客户端 JS 设置、抓取端读不到；不改其他公开页面的分享标题。Vite 同时构建 index.html 与 invite.html。Nginx 的 /invite/ 路由需随此次变更更新为 /public/invite.html。图片放在现有 /public-assets/ 静态资源目录。分享图地址使用用户当前生产域名，其他独立部署环境需修改到实际可访问域名。

注意：系统 SharePreview 和网页 Open Graph 提供了预览素材，但不能保证所有微信版本、转发入口都会采用。没有接入微信 JS-SDK，也没有将发送改成微信原生 SDK。未向微信联系人发送消息。上线与 App 安装后需在真机验证 App 分享及微信内转发；图片缓存可能影响旧消息。此轮未部署生产。

验证：前端生产构建通过；Swift 语法解析通过。App 完整构建结果见本次交付说明。

## Imagegen 提示词

### 横版主视觉

Edit reference photos into one premium minimalist website product hero, landscape 3:2. Use the actual tan leather silver-ring-bound travel scrapbook from reference 1 as the central hero object. Preserve its real page artwork, sea-blue collage, red maple leaves, original photographs and Chinese printing as faithfully as possible; do not invent new faces or replace the scrapbook with a generic notebook. Reference 2 shows the same product construction and is supporting reference only. Remove the distracting water bottles, cups, table clutter and harsh sunlight. Present the complete open scrapbook on a clean warm ivory #faf8f4 studio background, natural soft contact shadow, slightly elevated three-quarter top-down view, all edges inside frame with generous margins. Realistic product photography, restrained, elegant, crisp paper and leather texture. No new text, no captions, no logo, no UI, no watermark.

### 方形分享封面

Create one square 1024x1024 brand invitation share cover for a Chinese travel scrapbook app, designed to remain readable at a very small WeChat link thumbnail size. Warm ivory background, forest green and tiny terracotta accent matching reference 3. Center/lower area: one beautifully photographed open tan leather silver-ring travel scrapbook based on references 1 and 2; preserve actual rich blue-sea, red-maple travel page collage feel and physical construction. Remove bottles and table clutter. Upper area: the exact friendly dark green smiling open-book emblem from reference 3, intact and recognizable, modest scale. Main headline in large clear Chinese: “一起收藏旅途”. No other text, no QR code, no fake controls, no watermark. Minimal balanced editorial composition, generous breathing room, soft natural shadows. Book fills roughly lower 55 percent; headline is readable at thumbnail size. This is a finished share thumbnail asset, not a mockup of a phone or chat interface.
