# 制作工具与字体后台兼容性核对

日期：2026-10-28。检查目录：`/Users/dream/Documents/project/TravelDiary/字体/制作工具/font-specimen-maker`。结论：展示图片兼容；整套输出不是后台可直接导入协议。

## 实测

对 skill验收 目录下 Sarasa Mono SC SemiBold、Poppins Regular 两款 manifest 做独立核对：

- cover.png 均 1024×1024，PNG，约 76～81 KB；通过 UploadInput，独立处理器识别正确，满足 cover 至少 512 方图限制。
- specimen.png 均 1600×2080，PNG，约 324～343 KB；通过 UploadInput，像素数低于 2400 万，独立处理器识别正确。
- 所有被检查图片的 SHA256 与 manifest 一致；文件大小低于当前每文件 100 MiB 上限。
- thumbnail-256.png 可保留为工具缩略图，但不是合法后台 cover；当前后台未提供独立 thumbnail 关联字段。
- 两个源文件均为静态 TTF，PostScript 存在；通过现有独立处理器 inspect_file。未执行真实上传、发布或收费配置。
- 工具脚本完整回归通过：尺寸、来源、源文件保留、覆盖保护、配方复现、缺字拒绝、部分失败、语言选择、TTC 索引。
- 已查看 Sarasa 封面，主体字形清晰、装饰不遮挡；本次未逐张复核全部详情图，不替代原视觉验收记录。

## 对接差异

1. 工具支持 TTC、OTC 和可变默认轴，后台当前仅支持单字面静态 TTF／OTF；制作成功不代表源字体可上架。不默认转换或改名。
2. 工具 manifest.source 是扁平字面信息（postscript_name、variable_axes），处理器结果要求 faces 数组及 variable 布尔值；不能直接拿 manifest 作为可信处理回报。
3. 工具 recipe.text 是对象，后台 Recipe.text 是字符串；实际后台 serializer 检查两份 recipe 均失败。展示图片可上传，但配方不能原样粘贴入后台。主题与 palette 还需映射或保留完整工具配方的独立字段。
4. folder 哈希不是 UUID 业务 ID，后台还需要 family UUID、asset UUID、face ID、版本；本地路径应通过上传结果映射。
5. manifest 记录 SHA256，上传接口还需文件体积、MIME 和 Base64 MD5；现有后台选择文件会计算，工具自身没有完整上传命令。
6. 工具不复制字体二进制、不打包授权附件、不登记收费和审核结论；后台发布仍需原字体、已验证封面、至少一张详情、语言、默认字面、授权附件与许可范围、有效商品策略。
7. 工具通过 preferred family/style 名称识别 SemiBold，后台处理器目前采用旧 name ID 1/2，实测可能显示 label Regular。PostScript 对得上，文件可加载；运营需把字面展示名手动纠正为 SemiBold，后续统一优先采用 name ID 16/17。

## 当前可执行流程

后台新建字体 → 上传原 TTF／OTF → 上传 cover.png 为封面 → 上传 specimen.png 为详情图 → 等独立处理器验证 → 加入字面并选默认字面 → 补齐语言和授权 → 发布收费策略 → 字体校验并发布。工具输出不直接上传为整个 ZIP，manifest／recipe 是制作记录，不是后台发布包。
