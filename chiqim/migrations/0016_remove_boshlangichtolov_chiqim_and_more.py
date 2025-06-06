# Generated by Django 5.2 on 2025-06-03 04:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('chiqim', '0015_boshlangichtolov_alter_smslog_options_and_more'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='boshlangichtolov',
            name='chiqim',
        ),
        migrations.RemoveField(
            model_name='boshlangichtolov',
            name='xaridor',
        ),
        migrations.AlterModelOptions(
            name='smslog',
            options={'ordering': ['-sent_at'], 'verbose_name': 'SMS Tarixi', 'verbose_name_plural': 'SMS Tarixlari'},
        ),
        migrations.RemoveIndex(
            model_name='bildirishnoma',
            name='chiqim_bild_chiqim__1dc9aa_idx',
        ),
        migrations.RemoveIndex(
            model_name='chiqim',
            name='chiqim_chiq_xaridor_4174d9_idx',
        ),
        migrations.RemoveIndex(
            model_name='smslog',
            name='chiqim_smsl_sent_at_214f53_idx',
        ),
        migrations.RemoveIndex(
            model_name='smslog',
            name='chiqim_smsl_bildiri_5727f1_idx',
        ),
        migrations.RemoveIndex(
            model_name='tolovturi',
            name='chiqim_tolo_chiqim__1e18de_idx',
        ),
        migrations.RemoveField(
            model_name='chiqim',
            name='boshlangich_qarzdorlik',
        ),
        migrations.RemoveField(
            model_name='chiqim',
            name='boshlangich_tolov',
        ),
        migrations.AlterField(
            model_name='bildirishnoma',
            name='sms_sent',
            field=models.BooleanField(default=False, verbose_name='SMS Yuborildi'),
        ),
        migrations.AlterField(
            model_name='chiqim',
            name='tolangan_summa',
            field=models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name="Boshlang'ich to'lov"),
        ),
        migrations.AlterField(
            model_name='smslog',
            name='error_message',
            field=models.TextField(blank=True, null=True, verbose_name='Xato Xabari'),
        ),
        migrations.AlterField(
            model_name='smslog',
            name='message',
            field=models.TextField(verbose_name='SMS Matni'),
        ),
        migrations.AlterField(
            model_name='smslog',
            name='sent_at',
            field=models.DateTimeField(auto_now_add=True, verbose_name='Yuborilgan Vaqt'),
        ),
        migrations.AlterField(
            model_name='tolovturi',
            name='bank',
            field=models.CharField(blank=True, max_length=100, verbose_name='Tolov qilingan bank'),
        ),
        migrations.AlterField(
            model_name='tolovturi',
            name='sana',
            field=models.DateField(auto_now_add=True, verbose_name="To'lov sanasi"),
        ),
        migrations.AlterField(
            model_name='tolovturi',
            name='summa',
            field=models.DecimalField(decimal_places=2, max_digits=15, verbose_name='Tolov summasi'),
        ),
        migrations.AlterField(
            model_name='tolovturi',
            name='tolov_turi',
            field=models.CharField(choices=[('zelle', 'Zelle'), ('wire_transfer', 'Wire Transfer'), ('cash', 'Naqd'), ('button', 'Button')], max_length=20, verbose_name='Tolov turi'),
        ),
        migrations.DeleteModel(
            name='BoshlangichTolov',
        ),
    ]
