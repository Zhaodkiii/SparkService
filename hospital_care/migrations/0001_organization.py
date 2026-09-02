import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("file_manager", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Hospital",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=64, unique=True)),
                ("name", models.CharField(max_length=128)),
                ("short_name", models.CharField(blank=True, default="", max_length=64)),
                ("grade", models.CharField(blank=True, default="", max_length=32)),
                ("province_code", models.CharField(blank=True, default="", max_length=16)),
                ("city_code", models.CharField(blank=True, default="", max_length=16)),
                ("district_code", models.CharField(blank=True, default="", max_length=16)),
                ("address", models.CharField(max_length=255)),
                ("service_phone", models.CharField(blank=True, default="", max_length=32)),
                ("emergency_phone", models.CharField(blank=True, default="", max_length=32)),
                ("website_url", models.CharField(blank=True, default="", max_length=512)),
                ("introduction", models.TextField(blank=True, default="")),
                ("registration_redirect_url", models.CharField(blank=True, default="", max_length=512)),
                ("service_mode", models.CharField(choices=[("demo", "Demo"), ("redirect", "Redirect"), ("integrated", "Integrated")], default="demo", max_length=16)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("suspended", "Suspended")], db_index=True, default="draft", max_length=16)),
                ("version", models.BigIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("logo_file", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="hospital_logos", to="file_manager.managedfile")),
            ],
        ),
        migrations.CreateModel(
            name="HospitalDepartment",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=128)),
                ("short_name", models.CharField(blank=True, default="", max_length=64)),
                ("description", models.TextField(blank=True, default="")),
                ("sort_order", models.IntegerField(default=0)),
                ("status", models.CharField(choices=[("active", "Active"), ("hidden", "Hidden")], default="active", max_length=16)),
                ("hospital", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="departments", to="hospital_care.hospital")),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="children", to="hospital_care.hospitaldepartment")),
            ],
        ),
        migrations.CreateModel(
            name="HospitalStaffMembership",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("role", models.CharField(choices=[("hospital_admin", "Hospital Admin"), ("doctor", "Doctor"), ("nurse", "Nurse"), ("auditor", "Auditor")], max_length=32)),
                ("employee_no", models.CharField(blank=True, default="", max_length=64)),
                ("status", models.CharField(choices=[("invited", "Invited"), ("active", "Active"), ("suspended", "Suspended")], default="invited", max_length=16)),
                ("valid_from", models.DateTimeField(blank=True, null=True)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                ("joined_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("hospital", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="staff_memberships", to="hospital_care.hospital")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="hospital_staff_memberships", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name="DoctorProfile",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("display_name", models.CharField(max_length=64)),
                ("title", models.CharField(blank=True, default="", max_length=64)),
                ("specialties", models.JSONField(blank=True, default=list)),
                ("introduction", models.TextField(blank=True, default="")),
                ("license_status", models.CharField(choices=[("unverified", "Unverified"), ("verified", "Verified"), ("suspended", "Suspended")], default="unverified", max_length=16)),
                ("profile_status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("hidden", "Hidden")], default="draft", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("avatar_file", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="doctor_avatars", to="file_manager.managedfile")),
                ("staff_membership", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name="doctor_profile", to="hospital_care.hospitalstaffmembership")),
            ],
        ),
        migrations.CreateModel(
            name="DoctorDepartmentMembership",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("is_primary", models.BooleanField(default=False)),
                ("sort_order", models.IntegerField(default=0)),
                ("status", models.CharField(choices=[("active", "Active"), ("hidden", "Hidden")], default="active", max_length=16)),
                ("department", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="doctor_memberships", to="hospital_care.hospitaldepartment")),
                ("doctor", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="department_memberships", to="hospital_care.doctorprofile")),
            ],
        ),
        migrations.AddIndex(
            model_name="hospital",
            index=models.Index(fields=["status", "name"], name="idx_hospital_status_name"),
        ),
        migrations.AddConstraint(
            model_name="hospitaldepartment",
            constraint=models.UniqueConstraint(fields=("hospital", "code"), name="uniq_hospital_department_code"),
        ),
        migrations.AddIndex(
            model_name="hospitaldepartment",
            index=models.Index(fields=["hospital", "status", "sort_order"], name="idx_dept_hospital_status"),
        ),
        migrations.AddConstraint(
            model_name="hospitalstaffmembership",
            constraint=models.UniqueConstraint(fields=("hospital", "user"), name="uniq_hospital_staff_user"),
        ),
        migrations.AddIndex(
            model_name="hospitalstaffmembership",
            index=models.Index(fields=["user", "status"], name="idx_hospital_staff_user_status"),
        ),
        migrations.AddConstraint(
            model_name="doctordepartmentmembership",
            constraint=models.UniqueConstraint(fields=("doctor", "department"), name="uniq_doctor_department"),
        ),
    ]
