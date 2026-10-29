# 字体模块实施记录

日期：2026-10-28。状态：核心代码已接入，两端构建及本地自动化通过；尚未部署、迁移真实数据库或完成 OSS／支付／真机验收，不能作为全需求完成记录。

## 已接入

- font_library 模型及初始迁移：字体家族、草稿、不可变发布、已验证资源、上传任务与租约、个人记录、作品使用依据、发布幂等及审计。
- JSON 控制面请求限制；上传签名、OSS HEAD 和条件 COPY；独立处理器拉取任务与可信结果确认。业务服务没有字体 GET／PUT 正文逻辑。
- 文件、封面、预览和授权附件上传；静态单字面 TTF／OTF 验证。同 PostScript 不同文件冲突阻断。浏览器生成真实字体小样并检查 cmap 缺字。
- 后台内容资源四入口、旧入口跳转、字体编辑六分区、草稿冲突、发布检查、上下架、复制历史为草稿。价格复用收费中心。
- billing font 类型适配；首次资源发布前可配置已验证草稿的价格，兑换仍要求资源真正上架。免费领取有独立长期记录。
- iOS 字体集市、已获取／收藏／最近、详情、已有购买／会员组件、按字面下载、流式摘要校验、原子落盘、动态注册、存储管理及文字编辑返回。
- 文档字体引用增加可选 faceID，旧 JSON 兼容；恢复接口按账户和作品授权记录判断；画布与导出预热入口接入缺失资源恢复。

## 配置与运行

先备份目标库再执行 `python manage.py migrate`。本轮仅生成迁移，没有修改实际业务库。正常后台权限初始化包含 font_library 五项权限，运营角色需按现有 RBAC 授予菜单和操作权限。

环境变量：

- FONT_OSS_PREFIX：显式指定环境命名空间，例如 traveldiary/fonts/production/；默认 development，生产必须修改。
- FONT_PROCESSOR_TOKEN：独立处理器与 API 共享的高强度随机凭据，留空时处理器接口关闭。不得存入仓库或网页。
- 独立处理器另设 FONT_API_BASE，指向目标 API 根地址；运行 `python scripts/font_processor.py --once` 验证单次拉取，去掉 --once 持续运行。
- 处理器依赖见 requirements-font-processor.txt，仅在运营电脑／独立环境安装。当前工作区旧 .venv/bin/pip shebang 无效，应使用 `python -m pip`；本次依赖下载还遇到证书连接错误，脚本真实运行未完成验证。
- OSS 复用现有 ALIYUN 配置，浏览器需要 PUT CORS；字体下载只允许 HTTPS OSS 域名。私有文件经服务端鉴权签名，不能借业务代理绕行。

流程：新建 → 上传 → 独立处理器验证 → 加入字面／选择封面和详情 → 核对授权 → 保存 → 登记计费商品并发布策略 → 返回字体校验发布。小样可以通过后台本地 FontFace 生成，也可运行脚本 --specimen／--output／--text。

## 验证结果

- `manage.py test font_library billing --settings=SparkService.test_settings`：59 项通过。
- 字体小样字符覆盖与现有素材页面回归：14 项通过。
- `npm run build`：通过，存在原有大 chunk 提示。
- `manage.py makemigrations --check --dry-run`：无遗漏迁移。
- iOS Debug Simulator 两轮 xcodebuild：通过（含恢复入口补充）。未进行真机交互验收。

## 未完成范围与上线阻断项

以下仍需继续实施或真实验证，不能宣称五份需求全部完成：

1. 服务端签名离线凭据及客户端离线新使用资格；当前远程字体新使用走在线权限校验。
2. 模板发布精确字体绑定、模板附带字体权益及模板导入依赖下载的完整联动。
3. SQLite 文件／作品依赖索引、自动清理与活动资源租约；当前采用原子 JSON 索引和显式删除，已注册字体会阻止本会话清理。
4. 后台批量操作、完整分类／权益筛选、客户端目录持久化缓存、图片专用缓存与断点下载进度／取消；当前 URLSession 下载去重和失败重试不是完整断点队列。
5. 离线最近记录仅在编辑确认入口登记；进一步应与提交成功／取消状态校验统一。跨设备最近、限免和生产同步尚未实现。
6. 上传文件真实性、小样视觉、独立处理器完整执行、真实 OSS CORS、故障恢复、支付沙盒和真机 UI 需实测。
7. 旧作品恢复依据已有服务端使用记录；历史未登记或复制作品的授权迁移未完成。特殊撤回／退款影响和印制许可范围需进一步联动。

已下载字体本身不能视作账号新使用权益；当前编辑器内置字体列表排除 cloud 条目，远程新选择通过详情权限流程。现阶段不应开放真实收费字体销售，需补齐上述权益和端到端验收后再灰度。

## MySQL 首次迁移修复（2026-10-28）

原 FontAsset.object_key 为 varchar(1024) UNIQUE，utf8mb4 下索引超出 MySQL 3072 字节限制，错误 1071。已将内部生成的资源 key 限定为 varchar(255) UNIQUE，并约束 FONT_OSS_PREFIX 不超过 160 字符，以留足任务路径空间。

修正 0001 以支持全新安装；0002_mysql_object_key_index 为已完成旧 0001 的环境提供兼容字段迁移。部分失败环境不能用 --fake 跳过剩余表。

本机实际检查：font_library 尚无迁移记录，仅 FontFamily、FontAudit 两张空表，且无外部表外键引用。执行 repair_font_initial_migration --apply 前检查计数并备份 SHOW CREATE TABLE，按依赖顺序清除空表后正常 migrate；0001、0002 均成功，10 张字体表存在，object_key 已核对为 varchar(255)。备份位于 run/font-migration-backups/。

恢复命令仅接受上述精确的空表状态；已有数据、已记录迁移或其他部分迁移状态会拒绝处理。其他环境先运行不带 --apply 的命令检查，并停止字体写入后操作。

回归：7 项字体测试通过；makemigrations --check --dry-run 无遗漏。剩余 support_center.GarbageObject.key 的既有 MySQL 警告不在此次字体修复范围。

仓库没有根目录 install.sh；安装 Python 依赖应使用有效解释器执行 python -m pip install -r requirements.txt，独立字体处理器环境使用 requirements-font-processor.txt，而非 sh install.sh。

## 2026-10-28 字体生产同步增量

[字体同步操作与配置](./PRODUCTION-SYNC.md)：已增加与贴纸同流程的生产同步。共用 OSS 配置与文件 key，仅同步元数据；包含预检、确认、历史、幂等、任务恢复和版本冲突处理。93 项服务端组合测试与 18 项前端回归通过。此增量实现单字体同步，未进行真实部署／生产导入，不覆盖本文其他未完成项。
