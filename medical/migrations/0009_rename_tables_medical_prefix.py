# Generated manually: unify physical table names under medical_ prefix.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("medical", "0008_alter_examinationreport_organization_name_nullable"),
    ]

    operations = [
        migrations.AlterModelTable(
            name="examinationreport",
            table="medical_examination_report",
        ),
        migrations.AlterModelTable(
            name="healthexamreport",
            table="medical_health_exam_report",
        ),
        migrations.AlterModelTable(
            name="medexamdetail",
            table="medical_med_exam_detail",
        ),
        migrations.AlterModelTable(
            name="prescriptionbatch",
            table="medical_prescription_batch",
        ),
        migrations.AlterModelTable(
            name="medication",
            table="medical_medication",
        ),
        migrations.AlterModelTable(
            name="medicationtakenrecord",
            table="medical_medication_taken_record",
        ),
        migrations.AlterModelTable(
            name="modelchangelog",
            table="medical_model_change_log",
        ),
    ]
