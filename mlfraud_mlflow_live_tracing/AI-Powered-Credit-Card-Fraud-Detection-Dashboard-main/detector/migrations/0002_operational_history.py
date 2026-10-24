from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("detector", "0001_initial")]
    operations = [
        migrations.RenameField(
            model_name="predictionlog",
            old_name="reconstruction_error",
            new_name="score",
        ),
        migrations.AlterField(
            model_name="predictionlog",
            name="mode",
            field=models.CharField(default="heuristic_demo", max_length=80),
        ),
        migrations.AddIndex(
            model_name="predictionlog",
            index=models.Index(fields=["-created_at"], name="predlog_created_desc_idx"),
        ),
        migrations.AddIndex(
            model_name="predictionlog",
            index=models.Index(fields=["flagged"], name="detector_pr_flagged_8d2d7c_idx"),
        ),
    ]
