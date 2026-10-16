# 预设手帐制作与 OSS 发布操作手册

更新：2026-10-16。本文依据舟山 v1 实际执行的脚本与结果编写，适用于“开发机制作 → 开发机直接上传 OSS → 登记当前连接的数据库 → 验证 → 后台/iOS 使用”。

## 1. 发布后得到什么

一次发布生成一份不可变手帐版本。数据库保存系列、手帐、页序、资源索引和版本快照；OSS 保存可编辑内容 JSON、素材和预览图。iOS 向 Django 查询目录及下载计划，再直接向 OSS 获取文件。上传和下载的资源字节均不经过低带宽 API 服务器。

本次舟山只登记本机 MySQL `127.0.0.1:3306/sparkservice`。OSS 上传成功不会自动同步生产数据库；生产是否可见取决于生产数据库是否有对应模板与版本记录。

```text
PSD 原稿 → 转换工具 → 完整 .diarypreset 目录 → ZIP
                                              │
                              publish_diary_preset（开发机）
                                ├─校验、命名空间转换
                                ├─直传 OSS 私有 blobs
                                └─数据库事务：版本快照 + 当前版本指针
                                              │
                                  verify_diary_preset
                                              │
                                  后台目录 / iOS 预设页
```

## 2. 工具、路径与身份

| 用途 | 当前路径或标识 |
|---|---|
| 后端仓库 | `/Users/dream/Documents/project/Reference/SparkService`，分支 `TravelDiary` |
| iOS 仓库 | `/Users/dream/Documents/project/TravelDiary/TravelDiaryClient` |
| PSD 转换工具 | `/Users/dream/Documents/project/TravelDiary/PSD转换工具` |
| 舟山源文件 | `/Users/dream/Documents/project/TravelDiary/舟山/成品` |
| 舟山制作与报告目录 | `/Users/dream/Documents/project/TravelDiary/舟山/发布准备` |
| Bucket / 地域 | `zhaodkdream` / `cn-beijing` |
| OSS 资源前缀 | `traveldiary/presets/` |
| 系列 slug / 名称 | `islands` / `海岛系列` |
| 舟山数据库模板 UUID | `21a8759e-e59f-58a0-b92e-86d41d88848a` |
| 舟山源 manifest 标识 | `islands-zhoushan` |

区分三个编号：源包 `templateBookID` 是制作端标识；`--template-id` 是数据库模板 UUID，更新同一本时必须复用；数据库版本号由发布命令自动递增。当前发布器会将线上 manifest 的 templateBookID 改成模板 UUID，将 packageVersion 改成数据库新版本号，故不要用源 manifest 标识直接请求云端模板 API。

## 3. 首次准备运行环境

```sh
cd /Users/dream/Documents/project/Reference/SparkService
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate diary_presets --noinput
```

转换工具使用自己的虚拟环境：

```sh
cd /Users/dream/Documents/project/TravelDiary/PSD转换工具
.venv/bin/python -m pip install -r requirements.txt
```

确保磁盘能容纳源文件、转换时未压缩素材、压缩后包、ZIP 及发布校验临时解包目录。不要仅按最终 ZIP 大小预留空间。

### 3.1 后端环境配置

在后端未入 Git 的 `.env` 或进程环境中配置，使用占位值示意：

```dotenv
DB_ENGINE=django.db.backends.mysql
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=sparkservice
DB_USER=<本机数据库用户>
DB_PASSWORD=<从安全环境注入>
DB_CONN_MAX_AGE=60
ALIYUN_ACCESS_KEY_ID=<RAM AccessKey ID>
ALIYUN_ACCESS_KEY_SECRET=<RAM AccessKey Secret>
ALIYUN_STS_ROLE_ARN=acs:ram::1589159843550123:role/zhaodoss
ALIYUN_OSS_BUCKET=zhaodkdream
ALIYUN_OSS_REGION=cn-beijing
ALIYUN_OSS_ENDPOINT=https://oss-cn-beijing.aliyuncs.com
ALIYUN_STS_DURATION_SECONDS=3600
DIARY_PRESETS_OSS_PREFIX=traveldiary/presets/
DIARY_PRESETS_UPLOAD_ROLE_ARN=<浏览器上传使用的受限角色ARN>
DIARY_PRESETS_PROCESSOR_TOKEN=<仅云端处理器与控制API共享的随机密钥>
```

命令行发布使用 `storage.bucket()` 中的 RAM AK/SK 直接操作 OSS，不调用 STS；浏览器直传才调用 AssumeRole。命令行 RAM 身份需要目标 blobs 的存在性检查/读取、写入，以及 releases manifest 写入权限；校验命令需要读取与 HEAD。不要用可写正式目录的身份给浏览器签发宽泛凭证。

生产服务器禁用静态凭证返回客户端的开发回退。文件传输使用 OSS 公网端点；只有同地域云处理器使用内网端点。模板发布不得部署到 `139.196.215.51`。

### 3.2 只输出非敏感的连接目标

发布前在后端目录执行，确认所连数据库与 Bucket；此检查不会打印密码或 AK：

```sh
.venv/bin/python manage.py shell -c "from django.conf import settings; from django.db import connection; print({k:settings.DATABASES['default'][k] for k in ('ENGINE','HOST','PORT','NAME','USER')}); connection.ensure_connection(); print('数据库连接成功'); print(settings.ALIYUN_OSS_BUCKET, settings.ALIYUN_OSS_REGION)"
```

发布命令没有 `--local` 开关，实际目标完全由 Django settings 的连接配置决定。连接错库时先纠正环境，不能直接执行发布。

## 4. PSD 筛选与页序

先列出所有 PSD，建立包含源相对路径、画布尺寸、图层数、选用原因、排除原因和最终页序的制作清单。用 PSD 合成预览检查左右页、封面和重复构图；文件名类似不代表内容相同。

舟山 v1 的清单见 [源文件选择记录](./zhoushan-source-selection.json)：

- 开篇固定：封面 → 跨页左页 → 跨页右页。
- 定海古城、沈家门、花鸟岛选较新的 v02/v2。
- 嵊山岛选“第一版”，排除“初稿版”。
- 排除枸杞岛“文字纸卡已分离-待Logo”中间稿。
- 其余按章节和主题排，左右页相邻且左先右后；照片墙普陀山构图不同，保留。
- 最终 63 页，全部 2185×3130。

本次脚本与清单保存在舟山 `发布准备` 目录：`inventory_sources.py` 生成 PSD 元数据和联系表；`selected-pages.json` 记录最终选取；`selected-psd/` 是加上 001、002 等顺序前缀的输入集合。序号必须补零，避免字典序错位。

本次 selected-psd 文件是原稿的硬链接，不能在里面编辑 PSD，否则可能修改原稿。后续制作建议复制源文件，或把这个目录当完全只读输入。不要把重复版本和中间稿都交给递归转换器。

## 5. 转换为 `.diarypreset`

```sh
cd /Users/dream/Documents/project/TravelDiary/PSD转换工具
.venv/bin/python convert_psd.py \
  '/Users/dream/Documents/project/TravelDiary/舟山/发布准备/selected-psd' \
  --output '/Users/dream/Documents/project/TravelDiary/舟山/发布准备/舟山-v1.diarypreset' \
  --title '舟山 · 海风会替我们记得' \
  --book-id islands-zhoushan \
  --series islands \
  --version 1 \
  --rasterize-smart-objects
```

| 参数 | 含义 |
|---|---|
| 输入目录 | 递归寻找 PSD 并自然排序，目录应只有本次选中页面 |
| `--output` | 完整包输出位置，必须以 .diarypreset 结尾且尚不存在 |
| `--title` | 手帐名称 |
| `--book-id` | 稳定制作标识，仅英文、数字、下划线、连字符 |
| `--series` | 当前工具接受 hiking/city/food/islands/yubeng |
| `--version` | 源包正整数版本，数据库版本另行生成 |
| `--rasterize-smart-objects` | 不支持的智能对象允许烘焙为独立图片；能够解析的仍尽量保留内部结构 |
| `--rasterize-special-layers` | 可选，有原生文字/特殊效果且确需栅格化时使用；需记录能力损失 |
| `--flatten` | 整页合成，会失去内部分层；本次未使用 |
| `--mapping` | 可选照片槽位/原生文字显式映射 |
| `--quality` / `--workers` | 图片压缩质量与并行数，默认 85 / 4 |

不要直接覆盖已有包，更新时用新的输出目录。转换失败不会把未完成目录当成功产物；检查日志中具体页和层。舟山遇到变形智能对象后使用上述栅格化参数重新转换。

转换日志的 `Converted n/619` 表示图片压缩进度，不是页数。最终实际去重后素材数可能小于待处理图像数。

## 6. 包结构与文件格式

`.diarypreset` 是目录，不是一个图片格式。上传 ZIP 应展开为下列结构：

```text
package.json
pages/page-xxx.json
objects/object-xxx.json
assets/xxx.webp
previews/page-xxx-480.jpg
previews/page-xxx-1800.jpg
drawings/xxx.drawing          # 仅有实际绘画时存在
```

ZIP 根部必须直接是 `package.json`，不能套 `舟山-v1.diarypreset/package.json`。禁止包含 PSD、.DS_Store、__MACOSX、转换报告、临时缓存或其他未索引文件。单页包使用相同格式，但 pages 恰好一项且包含该页全部依赖。

### 6.1 manifest 字段

| 字段 | 要求 |
|---|---|
| format | TravelDiary.PresetBook |
| schemaVersion / layerSchemaVersion | 当前均为 1 |
| templateBookID / packageVersion | 制作端标识和正整数版本 |
| title / seriesID | 名称和系列 slug |
| pageSize | width/height 为正数，当前一本内保持统一 |
| coverPageID / shellPageID | 封面必须存在，可选外壳页也需在 pages 中 |
| pages | 有序数组，每项 id/title/path；顺序就是手帐页序 |
| objectTable | content ID → 对象 JSON 相对路径 |
| assetTable | asset ID → path、pixelSize、byteCount、sha256 等 |
| requiredCapabilities / requiredFonts | 图层能力与字体要求 |
| files | 所有运行时文件的 path、byteCount、sha256；不含 package.json 自身 |

页面 JSON 包含 id/title/size/rootContentID/preview，其中 preview 指向缩略图和大预览；对象 JSON 包含 id/role/referenceSize/layers，图层引用子 contentID 或 assetID；素材表必须与实际图片尺寸和文件摘要一致。

所有路径使用包内相对路径，禁止绝对路径、反斜杠、冒号、`.`、`..`、重复路径或符号链接逃逸。摘要为实际文件字节的 SHA-256，修改 JSON 或图像后必须重新计算，不可以手工沿用旧摘要。

### 6.2 舟山标题整理与打包

本次专用脚本：

```sh
python3 '/Users/dream/Documents/project/TravelDiary/舟山/发布准备/prepare_package.py'
```

它整理前缀/版本文字、固定开篇三个页标题、同步 page JSON 和 manifest、重算 files 的字节数与 hash，然后只把 manifest 与 files 索引内容打包。ZIP 使用 ZIP_STORED，因为 WebP/JPG 已压缩。该脚本是舟山专用文件，后续其他手帐应按自己的清单整理标题，不直接套用开篇逻辑。

通用打包方式（完成所有标题修改和索引重算后使用）：

```sh
python3 - <<'PY'
import json, zipfile
from pathlib import Path
root = Path('/路径/手帐.diarypreset')
out = Path('/路径/手帐.diarypreset.zip')
manifest = json.loads((root / 'package.json').read_text())
with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as z:
    z.write(root / 'package.json', 'package.json')
    for f in manifest['files']:
        z.write(root / f['path'], f['path'])
print(out, out.stat().st_size)
PY
```

该段仅用于可信制作目录，不替代路径安全和内容校验；运行前确认输出 ZIP 允许覆盖。

## 7. 发布前校验

```sh
cd /Users/dream/Documents/project/TravelDiary/PSD转换工具
.venv/bin/python validate.py \
  '/Users/dream/Documents/project/TravelDiary/舟山/发布准备/舟山-v1.diarypreset'
```

看到“通过”后仍需查看 `.report.json` 中每页 warnings、照片槽位数、可编辑文字数、智能对象保留/栅格化情况。格式校验通过不等同视觉与 Photoshop 完全一致。

当前发布器还会重新安全解包并检查：ZIP 不超过约定文件数，解压总量最多 2 GiB，单文件最多 100000000 字节，1–100 页，索引与文件集合一致，SHA-256/尺寸一致，能力和 schema 支持，图片可解码，页面与对象依赖可达。实际实现见 `diary_presets/package.py`。Linux 程序不能直接用 PencilKit 验证 Apple 专有绘画数据的全部语义，需 iOS 导入时继续验证。

## 8. 直传 OSS 并登记本机数据库

在后端目录执行：

```sh
cd /Users/dream/Documents/project/Reference/SparkService
.venv/bin/python -u manage.py publish_diary_preset \
  '/Users/dream/Documents/project/TravelDiary/舟山/发布准备/舟山-v1.diarypreset.zip' \
  --series islands \
  --series-title 海岛系列 \
  --title '舟山 · 海风会替我们记得' \
  --template-id 21a8759e-e59f-58a0-b92e-86d41d88848a \
  --report '/Users/dream/Documents/project/TravelDiary/舟山/发布准备/publication.json'
```

`-u` 让重定向日志时及时显示进度。全部参数均需提供，报告父目录须已存在。

| 参数 | 说明 |
|---|---|
| archive | 完整 ZIP，不接受 PSD 或普通文件夹 |
| --series | 目标系列 slug |
| --series-title | 系列不存在时创建的名称，已存在系列不会自动改名 |
| --title | 目标手帐名称 |
| --template-id | 固定模板 UUID；同本更新复用，新本生成新 UUID |
| --report | 成功报告 JSON 输出路径，不应放在运行时资源包中 |

新手帐 UUID 可用 `python3 -c 'import uuid; print(uuid.uuid4())'` 生成一次后记入发布清单。不要每次发版重新生成，否则会成为不同手帐。

### 8.1 命令内部顺序

1. 计算 ZIP SHA-256；若同模板已经成功发布完全相同 ZIP，直接返回 Already published，不新增版本，也不会重新生成报告。
2. 本机解包、校验并计算页面依赖；用 ZIP hash 前 24 位给 page/object/asset ID 和路径增加命名空间，避免不同包合并冲突。
3. 重写后的每个文件计算新 SHA-256，以摘要定位 OSS blob；4 路并发、最多 8 个待处理上传。已存在同 key 的文件跳过上传；本次前提是正式区只有可信发布身份可写，存在性检查不等于再次全量核对远端 hash。
4. 等待所有上传成功，再开启数据库事务，锁定目标模板，检查上传期间是否被其他人修改。
5. 创建或复用系列和模板，生成不可变 Version，保存页序/文件映射/依赖快照，递增 revision 并切换 current 指针。
6. 写 OSS 版本 package.json 并写 source-publish Event，事务提交后输出报告。

OSS 与数据库不是同一事务：若失败可能留下未引用 blob 或 manifest；不要为清理失败发布而直接删除共享资源。该命令是受信工作站直接发布，不会把 ZIP 传到 ECS，也不依赖云端 worker。

### 8.2 源文件与发布字节为何不同

发布器会命名空间化 ID/路径并重新编码 JSON，JSON 大小/hash 与原包不同是正常现象；图片内容保持上传字节。舟山源 files 合计 389371905 字节，发布后 389201720 字节，ZIP 为 390158170 字节。核对时按对应阶段的 manifest，不交叉比较。

## 9. OSS 最终目录、对象权限与数据库记录

舟山 v1 实际目录：

```text
oss://zhaodkdream/traveldiary/presets/blobs/sha256/{文件SHA256}
oss://zhaodkdream/traveldiary/presets/releases/21a8759e-e59f-58a0-b92e-86d41d88848a/1/package.json
```

blobs 使用内容摘要作 key，没有 .webp/.json 后缀也能下载；Content-Type 由发布器写入。多个版本/页面可以复用相同 blob，不能按目录名判断它属于哪一页。真实映射来自 Version.snapshot.keys：包内相对路径 → OSS object key。

**当前命令行流程不上传源 ZIP 到 staging，不生成 reports/ 或 indexes/ 对象。** 这些目录用于另一条后台直传/云处理设计；不要把设计目录当成本次实际生成物。浏览器流程才将源 ZIP 直传 `staging/{upload_session}/source.diarypreset.zip`。

现有 Bucket 为 public-read，但本次写入 blobs 和发布 manifest 显式设置对象 ACL private；单文件签名访问可用，匿名访问应为 403。不要为了模板发布修改整个 Bucket ACL，影响历史附件。

数据库模型：

- Series：系列 slug/title/顺序/启用状态。
- Template：手帐名称、系列、草稿、revision、current 版本指针。
- Version：number 与不可变 JSON snapshot；manifest、页面、各页依赖和 OSS keys 在 snapshot 中。
- Event：publish 与 source-publish 事件，后者记录源 ZIP hash 用于幂等。
- Upload：仅后台上传会话流程使用；本次命令行发布不创建 Upload。
- DownloadPlan：用户请求下载时生成，固定版本/所选页与 7 天授权窗口；发布命令本身不创建。

实现采用 JSON 版本快照，没有把设计文档中的每个 file/page 都建成独立表。不要执行未经确认的 SQL 手工插入页面记录。

## 10. 实际云端验证

```sh
cd /Users/dream/Documents/project/Reference/SparkService
.venv/bin/python -u manage.py verify_diary_preset \
  21a8759e-e59f-58a0-b92e-86d41d88848a \
  --report '/Users/dream/Documents/project/TravelDiary/舟山/发布准备/verification.json'
```

此命令读取当前版本，6 路 HEAD 核对全部唯一资源长度；完整下载第一页依赖并逐文件核对字节数/hash；对最大文件请求前 1024 字节，要求 206；去掉签名匿名请求该文件，要求 403。会产生 OSS 请求/下行流量。它不做全书所有文件的完整下载，也不验证真机渲染。

舟山 v1 实测：

| 项目 | 结果 |
|---|---|
| 发布版本 / 页数 | 1 / 63 |
| 所有对象大小检查 | 1267 个，通过 |
| 首页依赖完整下载 | 30 文件，16070017 字节，hash 全通过 |
| 全书索引大小 | 389201720 字节 |
| HTTP Range | 206 |
| 匿名资源读取 | 403 |
| 相同 ZIP 重复发布 | 未创建新版本 |

报告见 [发布结果](./zhoushan-publication.json) 与 [云端验证结果](./zhoushan-verification.json)。发布成功后报告写失败，也可能意味着数据库已提交；先检查当前版本/Event，再重试，不能看到报告缺失就认为未发布。

## 11. 后台和 iOS 使用

### 11.1 本地后台

地址 `http://localhost:6018/diary-presets`，用本机数据库超级用户登录。左侧选择海岛系列，再选择舟山；可看页缩略图、排序、改页名、删除、设置封面，点击“保存并发布”生成新数据库版本。回滚操作当前实现把旧 snapshot 作为新版本发布，不把版本号倒退。

后台修改后的权威数据是数据库 snapshot；当前后台 publish/rollback 路径没有像命令行一样额外写 releases/package.json。客户端下载计划使用数据库 manifest，故不依赖该额外 OSS manifest；运维不能仅扫描 releases 目录判断数据库所有版本。

Web ZIP 上传虽然已实现直传，上传后自动校验仍依赖独立同地域处理器；当前未部署该实例时，状态会停在 queued。要立即发布使用本文命令行流程；处理器部署说明见 [worker 说明](../../deployment/preset-processor/README.md)。不要将 worker 启动在低带宽 API 主机上。

### 11.2 iOS

预设页 → 云端预设与下载管理 → 海岛系列 → 舟山。列表只请求封面；进入详情按需取页缩略图；大图预览再取该页大图。

- 使用一页：新建本，或从已有本入口进入后加入当前本；只下载该页依赖。
- 整本添加：汇总全部页面依赖并去重，下载完成后一次原子创建本子。
- 下载管理：查看字节进度，暂停、继续、取消；完整 8 MiB 分段保留，继续时重新取得签名。
- 文件校验后才导入，进度到 100% 后仍可能显示校验/添加；作品存储独立于模板缓存。

本地目录 API：GET `/api/v1/diary-presets/catalog/`；详情 GET `/templates/{uuid}/{version}/`；同地址 POST `{"page_ids":["页面ID"]}` 创建单页计划，POST `{}` 创建全本计划；POST `/plans/{plan_uuid}/urls/` 以 `{"paths":["包内路径"]}` 请求签名。上述相对地址均位于 `/api/v1/diary-presets/` 下并要求登录。不要在长期配置或日志中保存签名 URL。

当前 Debug API 由用户配置为局域网地址，手机必须能访问本机 2026 端口；production 地址仍由环境配置决定。iOS 编译通过不等于已完成全部页面真机视觉与下载交互验收。

## 12. 更新、重试与故障定位

| 现象 | 原因与处理 |
|---|---|
| ZIP 缺 package.json | 压缩包多套目录；按第 6 节重打包 |
| hash/大小不匹配 | 修改了文件但未重算 files/assetTable；重新生成索引后校验 |
| 对象引用缺失 | 上传不完整或只传预览；重新输出完整依赖 |
| 智能对象变形失败 | 按页报告评估使用独立图层栅格化并记录限制，不能静默整页合并 |
| OSS SDK 原生库加载失败 | 修复当前虚拟环境的 pycryptodome/Pillow；不要删除项目业务文件 |
| 403 上传 | 检查实际 RAM 身份、Bucket/key 权限和 endpoint；不在日志输出密钥 |
| 浏览器 CORS 失败 | 检查后台 origin、PUT/POST/HEAD 与 SDK 所需头；CORS 不授予 RAM 权限 |
| 上传一半网络失败 | 原 ZIP 不变直接重跑，已存在内容 key 可复用；完整 hash 验证仍需执行 |
| Template changed while uploading | 期间有人改了草稿；刷新检查后重跑；本次不会覆盖并发修改 |
| Already published | 同模板该 ZIP 已成功发布；不代表另一个数据库也已发布 |
| 后台看不到但 OSS 有文件 | 确认数据库目标、series/template 启用状态和 current 指针，检查是否上传后登记失败 |
| 后台上传一直 queued | 独立云处理器未运行或未连控制 API；命令行流程不依赖它 |
| 下载 URL 过期 | 重新请求计划内资源签名；不要直接持久化旧链接 |
| 有报告但线上目录为空 | 本次登记本机数据库；OSS 是共享存储，数据库没有自动同步 |

更新同一本：制作新的资源目录/ZIP，使用相同 `--template-id`，自动产生下一个数据库版本。完全相同 ZIP 已发布过时不会再发；只想把历史内容重新上线时通过后台回滚，不靠换 ZIP 时间戳绕过幂等。

删除模板先逻辑下架；删除页只影响后续版本。blob 可能被历史版本、其他页或有效下载计划共享，未做引用检查前不得执行 OSS 批量删除。

## 13. 一次发布应留存的材料

源选取清单（含排除原因）、最终页序、转换参数/日志、转换能力损失报告、源 ZIP SHA-256、发布报告、验证报告、数据库目标和模板 UUID、执行日期及操作者。真实 AK/SK、数据库密码、STS 凭证与带签名 URL 不进入材料或 Git。

舟山实物输出保存在 `/Users/dream/Documents/project/TravelDiary/舟山/发布准备/`，本手册和脱敏结果记录保存在后端 `docs/diary-presets/`。完成格式校验、OSS 实测后，再执行真机视觉及编辑能力验收。
