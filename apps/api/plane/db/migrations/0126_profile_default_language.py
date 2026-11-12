from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("db", "0125_reset_project_deploy_board_identity")]

    operations = [
        migrations.AlterField(
            model_name="profile",
            name="language",
            field=models.CharField(default="zh-CN", max_length=255),
        ),
    ]
