# Generated by Django 3.1 on 2020-12-12 18:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_auto_20201212_2056'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='profile',
            name='med_verified',
        ),
        migrations.AlterField(
            model_name='profile',
            name='licence',
            field=models.CharField(max_length=100, null=True),
        ),
    ]