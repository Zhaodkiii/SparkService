from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="medicinebox",
            name="member",
            field=models.ForeignKey(
                blank=True,
                db_comment="所属家庭成员 ID，可为空；为空表示家庭公共药品",
                db_index=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="medicine_boxes",
                to="medical.member",
            ),
        ),
    ]
