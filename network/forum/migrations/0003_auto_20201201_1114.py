# Generated by Django 3.1 on 2020-12-01 08:14

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forum', '0002_job'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='external_link',
            field=models.URLField(blank=True, default='', null=True),
        ),
        migrations.AlterField(
            model_name='job',
            name='external_link',
            field=models.URLField(blank=True, default='', null=True),
        ),
    ]