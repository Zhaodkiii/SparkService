# TravelDiary 发布流程

唯一入口为 `scripts/deploy_sparkservice.sh`，目标仍为 `root@39.106.39.110`，默认服务器模板为 `deployment/server`。直接运行原来的命令即可发布：

```sh
bash scripts/deploy_sparkservice.sh
```

只检查本地配置和依赖，不连接服务器、不构建或上传：

```sh
bash scripts/deploy_sparkservice.sh --preflight
```

## 避免数据库认证失败

本地 `.env` 默认随发布同步。发布入口先制作权限为 600 的配置快照，校验与上传使用同一份快照，避免构建期间配置被改动。配置上传到独立候选目录，不立即覆盖服务器 `.deploy.env`。允许按生产配置使用 root；本地校验仍拒绝空密码、错误数据库地址/库名、错误生产域名及端口，密码必须通过服务器实际认证检查。

服务器使用候选配置启动一次性新版本容器，执行实际数据库认证、`SELECT 1` 和 Redis PING，再执行 Django 检查。端口可连接不作为数据库认证通过的依据。若密码错误，在迁移和正式配置切换前退出，保留原生产配置、前端目录及 current，并恢复原服务器模板。

不需要同步本地配置时，仍可使用 `SYNC_DEPLOY_ENV=0 bash scripts/deploy_sparkservice.sh`。此时复制服务器现有配置作为候选，也必须通过数据库认证检查。

## 发布顺序

1. 校验 Git 与 SSH 最终目标、本地配置、依赖和模板文件。
2. 在本机构建管理后台，打包源码并生成 SHA-256、分支/提交/工作区状态记录。
3. 将模板、候选环境及前端上传到独立 `uploads/<release-id>/`，上传中断不会覆盖正式文件。
4. 获取服务器部署锁；锁被占用时直接失败，不取消其他部署。校验源码包完整性、可用磁盘及前端文件。
5. 备份原模板，构建本次独立版本标签的后端镜像、确保前端镜像可用（缺失时拉取），并检查候选数据库和 Redis 连接及迁移文件。
6. 用宿主机 `mysqldump --single-transaction --routines --triggers sparkservice` 备份数据库，验证 gzip 完整性，再执行迁移和 collectstatic。
7. 备份并切换正式配置、前端，重建 web、celery_worker、celery_beat、frontend。
8. 检查四个新容器；web/frontend 必须 healthy，两个 Celery 容器必须运行，内部 API/前端健康接口必须成功。检查 Worker ping、任务注册、队列及迁移状态。
9. 全部通过后更新 current，输出 Release complete。后端镜像标签写入 `.deploy.env` 的 `SPARK_BACKEND_IMAGE`，后续 compose 操作会继续使用该版本。

服务器需要 `docker compose`（兼容 Podman Compose）、`flock`、`timeout`、`python3`、`sha256sum`、`mysqldump`、`gzip` 和 `curl`。备份依赖宿主机现有数据库管理员认证，不向命令行传递数据库密码。缺少工具、可用空间不足 1 GiB、备份失败时均停止发布。Python 环境需要项目已有的 python-dotenv；优先使用 `.venv/bin/python`，可用 `PYTHON_BIN` 覆盖。

## 失败与诊断

失败输出包含阶段与远端诊断目录。`uploads/<release-id>/result.txt` 记录退出码、阶段及是否进入切换；`release.txt` 记录提交、分支及工作区是否包含未提交修改。

正式切换前失败会恢复模板，不覆盖正式 `.deploy.env`、前端和 current。数据库迁移及 collectstatic 已执行的变更不会自动逆转。正式切换后失败保留诊断材料和实际服务状态，不宣告成功，也不自动回退数据库或 current。

数据库备份位于 `shared/backups/pre_release_<release-id>.sql.gz`。原环境文件及原前端分别保留为候选目录内的 `previous.env`、`previous-frontend/`，原模板保留在 `previous-template/`。配置和诊断目录由受限权限保护，凭证不输出到检查结果。失败包、历史镜像和备份保留供诊断，定期按运维保留策略审查磁盘空间。

普通入口不再接受 `CANCEL_RUNNING_DEPLOY=1` 或 `RESET_DATABASE_NAME`；取消任务和清库需分别诊断、审查后操作。`SYNC_DEPLOY_ENV`、`BUILD_FRONTEND_LOCAL`、`USE_RSYNC` 仍支持 0/1；关闭前端构建时服务器必须已有可用管理后台。发布后仍可运行发版技能的 `post_release_audit.sh` 验证实际 HTTPS 域名及最新日志。

本地隔离回归，不连接数据库、Docker 或 SSH 服务器：

```sh
.venv/bin/python -m unittest discover -s scripts/tests -p 'test_release_target.py' -v
.venv/bin/python -m unittest discover -s scripts/tests -p 'test_deploy_safety.py' -v
```
