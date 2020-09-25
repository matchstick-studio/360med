# Generated by Django 3.1 on 2020-09-21 19:47

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0015_profile_phone'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='occupation',
            field=models.IntegerField(choices=[(0, 'Medical Doctor'), (1, 'Nurse'), (2, 'Dentist'), (3, 'Clinical Officer'), (4, 'Pharmacist'), (5, 'Laboratory Scientist')], default=0),
        ),
    ]