"""存量库兼容迁移：确保 `AIScenarioModelBinding.display_name` 列存在。

背景（AI-CONFIG-000008）：
- `0001_initial.py` 已经把 `display_name` 写进了迁移状态，因此“全新数据库”从零 migrate
  会在建表阶段直接带上该列。
- 但在 `display_name` 被补进 `0001_initial.py` 之前就已经执行过 `0001_initial` 的数据库，
  不会因为初始迁移文件内容变化而自动新增列，于是 bootstrap 读取 `display_name` 时报
  `Unknown column 'ai_config_aiscenariomodelbinding.display_name'` 并 500。

因此这里用“数据库兼容型”数据迁移而非 schema state 迁移：
- 不向 Django migration state 重复声明字段（字段已在 0001 状态里），避免 fresh migrate 状态冲突；
- 运行时检查列是否存在，缺失才补列，保证幂等。
"""

from django.db import migrations, models


COLUMN = "display_name"
DB_COMMENT = "场景内展示名称；agent可配置业务名称如报告解读助手"


def _existing_columns(connection, table):
    with connection.cursor() as cursor:
        return {col.name for col in connection.introspection.get_table_description(cursor, table)}


def ensure_display_name(apps, schema_editor):
    connection = schema_editor.connection
    Binding = apps.get_model("ai_config", "AIScenarioModelBinding")
    table = Binding._meta.db_table

    if COLUMN in _existing_columns(connection, table):
        return

    field = models.CharField(max_length=128, blank=True, default="", db_comment=DB_COMMENT)
    field.set_attributes_from_name(COLUMN)
    schema_editor.add_field(Binding, field)


class Migration(migrations.Migration):

    # 混合 DDL + 数据回填；MySQL 下 DDL 会隐式提交，关闭原子性避免回滚误判。
    atomic = False

    dependencies = [
        ("ai_config", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(ensure_display_name, migrations.RunPython.noop),
    ]
