# Generated by Django 3.1 on 2020-11-26 21:07

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forum', '0012_auto_20201119_2337'),
    ]

    operations = [
        migrations.AlterField(
            model_name='post',
            name='tag_val',
            field=models.CharField(blank=True, default='', max_length=100, verbose_name='Community'),
        ),
        migrations.AlterField(
            model_name='post',
            name='type',
            field=models.IntegerField(choices=[(3, 'Forum'), (0, 'Question'), (5, 'Event'), (2, 'Job'), (1, 'Answer'), (7, 'Comment')], db_index=True),
        ),
    ]
