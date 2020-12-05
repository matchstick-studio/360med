# Generated by Django 3.1 on 2020-11-28 20:17

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import network.accounts.models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('accounts', '0014_auto_20201024_2227'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserVerification',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('licence_img', models.ImageField(blank=True, default=None, max_length=1024, upload_to=network.accounts.models.image_path)),
                ('licence', models.CharField(blank=True, max_length=100, null=True)),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]