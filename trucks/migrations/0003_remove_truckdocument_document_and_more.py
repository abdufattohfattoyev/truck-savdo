# Generated by Django 5.2 on 2025-05-31 21:19

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('trucks', '0002_truckdocument_truckimage_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='truckdocument',
            name='document',
        ),
        migrations.RemoveField(
            model_name='truckdocument',
            name='document_name',
        ),
        migrations.AddField(
            model_name='truckdocument',
            name='file',
            field=models.FileField(default=1, help_text='Upload documents (PDF, DOC, DOCX) or images (JPG, PNG, JPEG)', upload_to='truck_documents/', verbose_name='File'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='truckdocument',
            name='file_name',
            field=models.CharField(blank=True, help_text='Name of the file as it will appear', max_length=200, verbose_name='File Name'),
        ),
        migrations.AddField(
            model_name='truckdocument',
            name='is_image',
            field=models.BooleanField(default=False, help_text='Check if the uploaded file is an image', verbose_name='Is Image'),
        ),
        migrations.AlterField(
            model_name='truck',
            name='truck_id',
            field=models.CharField(help_text='Unique identifier for the truck (auto-generated)', max_length=50, unique=True, verbose_name='Truck ID'),
        ),
    ]
