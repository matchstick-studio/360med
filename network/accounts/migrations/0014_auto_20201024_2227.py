# Generated by Django 3.1 on 2020-10-24 19:27

from django.db import migrations, models
import phonenumber_field.modelfields


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0013_date_joined'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='profile',
            name='scholar',
        ),
        migrations.RemoveField(
            model_name='profile',
            name='twitter',
        ),
        migrations.RemoveField(
            model_name='profile',
            name='website',
        ),
        migrations.AddField(
            model_name='profile',
            name='affiliations',
            field=models.CharField(blank=True, default='', max_length=10000),
        ),
        migrations.AddField(
            model_name='profile',
            name='alt_email_a',
            field=models.EmailField(blank=True, max_length=10000, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='alt_email_b',
            field=models.EmailField(blank=True, max_length=10000, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='expertise',
            field=models.CharField(blank=True, default='', max_length=10000),
        ),
        migrations.AddField(
            model_name='profile',
            name='gender',
            field=models.IntegerField(choices=[(0, 'Male'), (1, 'Female'), (2, 'Other')], default=0),
        ),
        migrations.AddField(
            model_name='profile',
            name='occupation',
            field=models.IntegerField(choices=[(0, 'Medical Doctor'), (1, 'Nurse'), (2, 'Dentist'), (3, 'Clinical Officer'), (4, 'Pharmacist'), (5, 'Laboratory Scientist')], default=0),
        ),
        migrations.AddField(
            model_name='profile',
            name='phone',
            field=phonenumber_field.modelfields.PhoneNumberField(blank=True, max_length=128, region=None),
        ),
        migrations.AddField(
            model_name='profile',
            name='qualifications',
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AlterField(
            model_name='profile',
            name='date_joined',
            field=models.DateTimeField(auto_now_add=True, max_length=255),
        ),
        migrations.AlterField(
            model_name='profile',
            name='text',
            field=models.TextField(blank=True, default='No bio available yet', max_length=10000, null=True),
        ),
    ]
