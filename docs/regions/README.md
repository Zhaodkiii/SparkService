# 行政地区库实施与运维

实现日期：2026-10-27。服务端 `regions` 是公共地区模块；iOS 与服务端共用 `regions/data/mainland-regions.json` 发布产物。

## 初始数据与配置

首版来自高德实际成功请求，经标准化包含 31 个大陆省级节点、333 个地级节点、2846 个县级节点，共 3210 个真实行政节点。香港、澳门、台湾不在本期配送库中。移除直辖市的展示分组，将省直辖县级单位归到真实县级，无区县城市保留合法城市叶子，不将街道和重复 adcode 当作区县。

初始文件约 394 KB，版本及 SHA-256 见 `regions/data/manifest.json`。版本 ID 日期部分来自生成时 UTC 日期，不表示行政区划生效日期。source_as_of 未由上游提供，保留 null。客户端文件必须与导出文件逐字节相同。

`.env` 配置：

```dotenv
AMAP_WEB_SERVICE_KEY=在服务端配置真实值
REGIONS_SYNC_ENABLED=true
REGIONS_SYNC_DAYS=30
REGIONS_CLIENT_CHECK_DAYS=7
REGIONS_DAILY_REQUEST_BUDGET=4
REGIONS_CDN_BASE_URL=
```

实际 Key 已维护在本机服务端 `.env`，该文件被 Git 忽略；请通过部署密钥配置将它提供给正式服务、worker 和 beat。Key 不出现在客户端、地区文件或本说明中。

## 部署与首次初始化

在服务端虚拟环境执行：

```sh
python manage.py migrate regions
python manage.py regions bootstrap
```

bootstrap 校验仓库内置文件摘要与完整性，幂等导入；仅在没有当前正式版本时发布，不覆盖运行中的新版本。保留原数据抓取时间，按抓取时间计算下次检查。新环境可先利用内置库启动，不需要首次启动就调用高德。

Web 服务、Celery worker 与 beat 必须加载更新后的代码和配置。beat 每小时检查是否达到更新周期；真正的高德请求默认 30 天一次全量检查。运行时版本只在数据库中发布，不会自动替换 Git 或已发布 App 的内置文件。

## 检查、发布与回滚

```sh
python manage.py regions sync
python manage.py regions sync --force
python manage.py regions list
python manage.py regions publish --dataset-version 候选版本 --reason '已核验差异和特殊地区'
python manage.py regions export --dataset-version 正式版本 --file /目标路径/版本.json
```

`--force` 跳过时间间隔，仍遵守任务锁和每日预算。每次检查只发送一个全国三级查询，本次已验证返回覆盖完整；出现根结果分页异常或地区数量/归属校验不通过时停止，不将残缺数据发布。默认每日最多 4 次上游尝试，网络失败也计数。失败后按 1h/6h/24h 退避；认证/权限类错误延长暂停并记录错误码。没有 Key 时不请求上游。

内容无变化只更新检查时间。变化进入 candidate，全部需要核验后发布。Django admin 可查看候选差异、同步记录、当前状态及发布审计，可触发后台同步和审核发布。选择此前 published 版本重新发布即回滚；release_sequence 递增，原文件不覆盖。

目前采用自有公共下载接口分发，适合放在现有 CDN 反向缓存后面。可选 `REGIONS_CDN_BASE_URL` 指向部署方已上传并核验的版本文件目录；使用它时，发布前必须先导出并上传相同字节的文件，不能仅设置域名。默认留空不会依赖外部 OSS 上传步骤。

## 客户端与接口

- `GET /api/v1/regions/manifest/`：匿名、小体积，ETag / 304，声明 `structured_print_address_v1` 能力。
- `GET /api/v1/regions/datasets/{version}.json`：只公开已发布版本，长缓存、不可变。
- 客户端内置、有效缓存、上一份有效缓存回退；7 天检查一次自有 manifest，失败 1h/6h/24h 退避，无强制时间失效。
- 已打开滚轮持有原数据快照；更新后下次打开再使用新库。
- 文件大小、SHA-256、schema、节点关系和地区覆盖不通过时不安装。
- 结构化地址进入原打印报价/建单接口，服务端按真实路径验证并推导配送范围；旧客户端和旧上传任务仍允许原地址格式。
- 地区错误使用现有错误封装：`data.region_error` 和 `data.recovery`。客户端受限强制检查更新并要求重新选择，不静默改写个人地址。
- 建单先核对原请求幂等，再规范化新地址；已经创建的订单在地区更名后重试仍返回原名称快照。

## 验证

```sh
python manage.py test regions.tests print_orders.tests --settings=regions.test_settings --noinput
```

客户端在 TravelDiaryClient 仓库执行 `python3 scripts/test_print_orders.py`，包含地区仓库、三列联动和已有打印/支付回归。测试替身不调用高德；本次真实 Key 验证与种子采集共用一份成功响应，没有为客户端操作重复访问上游。

上线检查：应用迁移成功、bootstrap 有正式版本、manifest 200/304、文件摘要一致、worker/beat 任务可发现、Key 已配置、每日预算正确。先部署服务端再更新 App。未部署新 API 的环境通过旧地址序列化兼容，但不具备结构化服务端校验。
