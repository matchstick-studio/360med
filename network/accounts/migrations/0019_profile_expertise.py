# Generated by Django 3.1 on 2020-09-23 22:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0018_auto_20200924_0135'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='expertise',
            field=models.CharField(blank=True, default='', max_length=10000),
        ),
    ]
