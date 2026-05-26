# ZhaodkDream → SparkService 分批迁移脚本

从旧库 **ZhaodkDream** 只读迁移到空库 **sparkservice**。按序号**手动逐条**执行 Django 管理命令。

## 环境准备

数据库连接已在 [`run_all_migration.sh`](run_all_migration.sh) 与 [`zdk_migration/lib/old_db.py`](../../zdk_migration/lib/old_db.py) 中**写死**（本机迁移）：

| | 新库 sparkservice | 旧库 ZhaodkDream |
|--|-------------------|------------------|
| Host | 127.0.0.1 | 127.0.0.1 |
| Port | 3306 | 3306 |
| User | root | root |
| Password | Zhao1029* | Zhao1029* |

```bash
cd /Users/hua/Downloads/Reference/SparkService
source .venv/bin/activate

python manage.py migrate
python manage.py zdk_migrate_00_check
```

若需 AI Provider Key 解密，另设 `AI_PROVIDER_KEY_ENCRYPTION_KEY`（与旧 ZhaodkDream 环境一致）。

## 一键执行（全部步骤）

```bash
cd /Users/hua/Downloads/Reference/SparkService
chmod +x scripts/migration/run_all_migration.sh

# 正式迁移（00 → 18 → 99，日志写入 logs/migration/）
./scripts/migration/run_all_migration.sh

# 试跑，不写新库
./scripts/migration/run_all_migration.sh --dry-run

# 从第 6 步续跑（例如 01 已手动跑过）
./scripts/migration/run_all_migration.sh --from 6

# 只跑某一段
./scripts/migration/run_all_migration.sh --from 6 --to 13
```

脚本会自动 `source .venv`、导出写死的数据库配置，任一步失败即停止（`set -e`）。

## 执行顺序（手动逐条）

| 序号 | 命令 | 说明 |
|------|------|------|
| 00 | `python manage.py zdk_migrate_00_check` | 预检：连通性、行数、孤立 FK |
| 01 | `python manage.py zdk_migrate_01_auth_users` | auth_user（**保留 id**） |
| 02 | `python manage.py zdk_migrate_02_account_profiles` | user_profile → AccountProfile + phone SocialIdentity |
| 03 | `python manage.py zdk_migrate_03_social_identities` | auth_identity（apple/google/phone） |
| 04 | `python manage.py zdk_migrate_04_trusted_devices` | trusted_device |
| 05 | `python manage.py zdk_migrate_05_account_audit` | login_audit + 销户记录 |
| 06 | `python manage.py zdk_migrate_06_members` | Patient → Member + Binding |
| 07 | `python manage.py zdk_migrate_07_medical_cases` | MedicalRecord → MedicalCase |
| 08 | `python manage.py zdk_migrate_08_clinical_children` | 症状/就诊/手术/随访 |
| 09 | `python manage.py zdk_migrate_09_exam_reports` | 检查报告 + 明细合并 |
| 10 | `python manage.py zdk_migrate_10_health_exams` | 体检报告 + AI 结果写入 extra |
| 11 | `python manage.py zdk_migrate_11_prescriptions` | 处方批次 |
| 12 | `python manage.py zdk_migrate_12_medication_plans` | 用药计划 + 药箱 |
| 13 | `python manage.py zdk_migrate_13_medication_records` | 服药打卡记录 |
| 14 | `python manage.py zdk_migrate_14_files` | OSS 元数据 → ManagedFile |
| 15 | `python manage.py zdk_migrate_15_ai_config` | 试用/Provider/策略 |
| 16 | `python manage.py zdk_migrate_16_chat` | 聊天历史 → chat_sync |
| 17 | `python manage.py zdk_migrate_17_app_version` | 版本配置与日志 |
| 18 | `python manage.py zdk_migrate_18_notifications` | 通知发送日志（尽力映射） |
| 99 | `python manage.py zdk_migrate_99_verify` | 数量校验 |

每条命令支持：

```bash
python manage.py zdk_migrate_06_members --dry-run   # 试跑，不写库
python manage.py zdk_migrate_06_members --batch-size 200
```

## ID 映射

跨批次 ID 映射保存在：

```
scripts/migration/state/id_map.json
```

该文件已加入 `.gitignore`，**不在数据库建新表**。重复执行同一命令时会跳过已映射记录（幂等）。

## 明确不迁移

| 旧数据 | 原因 |
|--------|------|
| `authtoken_token` | 新版 JWT，用户需重新登录 |
| `email_otp` / `phone_otp` | 让用户重新获取验证码 |
| `apple_s2s_log` | 新版无对应表 |
| `aera_ai_usage_log` / `aera_ai_analysis` / `aera_ai_config` | 新版无用户级/日志表 |
| `messaging_conversation_participant` | 新版无对应表 |
| `qa_api_test_*` | 测试数据 |
| OSS 对象本体 | 仅迁元数据；需 bucket/object_key 不变 |

## 故障排查

1. **FK 失败**：检查前序命令是否已执行，`id_map.json` 是否包含对应映射。
2. **重复执行**：命令幂等，已映射/已存在记录会 skip。
3. **Provider Key 乱码**：确认 `AI_PROVIDER_KEY_ENCRYPTION_KEY` 与旧 ZhaodkDream 环境一致。
4. **文件无法访问**：确认 OSS bucket 与 `object_key` 未变，仅元数据迁移。

## 相关文档

- 字段级对照手册：`Health/ZhaodkDream/数据迁移手册-ZhaodkDream到SparkService.md`
- 迁移代码：`zdk_migration/management/commands/`
