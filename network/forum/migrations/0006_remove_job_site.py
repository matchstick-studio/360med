# Generated by Django 3.1 on 2020-12-01 11:52

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('forum', '0005_remove_event_site'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='job',
            name='site',
        ),
    ]