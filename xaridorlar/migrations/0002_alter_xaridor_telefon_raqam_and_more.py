# Generated by Django 5.2 on 2025-05-28 12:33

import django.core.validators
import xaridorlar.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('xaridorlar', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='xaridor',
            name='telefon_raqam',
            field=models.CharField(max_length=20, verbose_name='Telefon Raqam'),
        ),
        migrations.AlterField(
            model_name='xaridorhujjat',
            name='hujjat',
            field=models.FileField(upload_to=xaridorlar.models.generate_unique_filename, validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx'])], verbose_name='Hujjat fayli'),
        ),
    ]
