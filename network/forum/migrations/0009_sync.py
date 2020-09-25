# Generated by Django 3.0.2 on 2020-05-14 14:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("forum", "0008_spam_score"),
    ]

    operations = [
        migrations.CreateModel(
            name="Sync",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("last_synced", models.DateTimeField(null=True)),
            ],
        ),
        migrations.AlterField(
            model_name="post",
            name="spam",
            field=models.IntegerField(
                choices=[
                    (0, "Spam"),
                    (1, "Not spam"),
                    (3, "Quarantine"),
                    (2, "Default"),
                ],
                default=2,
            ),
        ),
    ]
