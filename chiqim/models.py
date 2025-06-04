from decimal import Decimal

import calendar
import logging
import uuid
from django.db import models, transaction
from django.utils import timezone
from trucks.models import Truck
from django.utils.text import slugify
import os

logger = logging.getLogger(__name__)

def generate_unique_chiqim_filename(instance, filename):
    """Fayl nomini noyob qilish uchun truck_id asosida papkada saqlash."""
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4()}{ext}"
    truck_id = instance.truck.id if instance.truck else 'unknown'
    return os.path.join(f'chiqim_documents/{truck_id}/', slugify(unique_name))



class Chiqim(models.Model):
    truck = models.ForeignKey(
        Truck,
        on_delete=models.CASCADE,
        related_name='chiqim',
        verbose_name="Mashina"
    )
    xaridor = models.ForeignKey(
        'xaridorlar.Xaridor',
        on_delete=models.CASCADE,
        related_name='chiqim',
        verbose_name="Xaridor"
    )
    narx = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Umumiy narx"
    )
    boshlangich_summa = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Boshlang'ich to'lov (rejalashtirilgan)"
    )
    qoldiq_summa = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        verbose_name="Qoldiq summa"
    )
    hujjatlar = models.FileField(
        upload_to=generate_unique_chiqim_filename,
        blank=True,
        null=True,
        verbose_name="Hujjatlar"
    )
    bo_lib_tolov_muddat = models.PositiveIntegerField(
        default=0,
        verbose_name="Bo'lib to'lash muddati (oy)"
    )
    oyiga_tolov = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name="Oyiga to'lov"
    )
    tolov_sana = models.DateField(verbose_name="Birinchi to'lov sanasi")
    izoh = models.TextField(blank=True, verbose_name="Izoh")
    sana = models.DateField(auto_now_add=True, verbose_name="Sotish sanasi")

    def get_total_boshlangich_paid(self):
        if not self.pk:
            return Decimal('0')
        return sum(tolov.summa for tolov in self.boshlangich_tolovlar.all()) or Decimal('0')

    def get_total_monthly_paid(self):
        if not self.pk:
            return Decimal('0')
        return sum(tolov.summa for tolov in self.tolovlar.all()) or Decimal('0')

    def get_boshlangich_qoldiq(self):
        """Calculate the remaining initial payment."""
        return max(Decimal('0'), self.boshlangich_summa - self.get_total_boshlangich_paid())

    def calculate_monthly_payment(self):
        remaining_amount = self.narx - self.boshlangich_summa
        self.oyiga_tolov = (remaining_amount / self.bo_lib_tolov_muddat) if self.bo_lib_tolov_muddat > 0 and remaining_amount > 0 else Decimal('0')

    def update_totals(self, save=True):
        if not self.pk:
            return

        total_boshlangich_paid = self.get_total_boshlangich_paid()
        total_monthly_paid = self.get_total_monthly_paid()
        total_paid = total_boshlangich_paid + total_monthly_paid
        self.qoldiq_summa = max(Decimal('0'), self.narx - total_paid)
        self.calculate_monthly_payment()

        if self.qoldiq_summa <= 0:
            self.bo_lib_tolov_muddat = 0
            self.oyiga_tolov = Decimal('0')
            self.bildirishnomalar.all().delete()
        else:
            if self.bo_lib_tolov_muddat <= 0 and total_monthly_paid > 0:
                remaining_amount = self.qoldiq_summa
                self.oyiga_tolov = self.oyiga_tolov if self.oyiga_tolov else remaining_amount
                self.bo_lib_tolov_muddat = int(remaining_amount // self.oyiga_tolov) if self.oyiga_tolov > 0 else 0

        if save:
            super(Chiqim, self).save(update_fields=['qoldiq_summa', 'oyiga_tolov', 'bo_lib_tolov_muddat'])

    @property
    def tolangan_summa(self):
        return self.get_total_boshlangich_paid() + self.get_total_monthly_paid()

    def get_next_unpaid_month(self):
        current_date = timezone.now().date()
        return self.bildirishnomalar.filter(
            status__in=['pending', 'warning', 'urgent', 'overdue'],
            tolov_sana__gte=current_date
        ).order_by('tolov_sana').first()

    def save(self, *args, **kwargs):
        with transaction.atomic():
            is_new = not self.pk
            old_truck = None
            if not is_new:
                old_instance = Chiqim.objects.get(pk=self.pk)
                old_truck = old_instance.truck if old_instance.truck != self.truck else None
                if old_instance.boshlangich_summa != self.boshlangich_summa or old_instance.bo_lib_tolov_muddat != self.bo_lib_tolov_muddat or old_instance.narx != self.narx:
                    self.calculate_monthly_payment()

            if is_new:
                self.qoldiq_summa = self.narx
                self.calculate_monthly_payment()
                if self.truck:
                    self.truck.sotilgan = True
                    self.truck.save()

            super(Chiqim, self).save(*args, **kwargs)
            self.update_totals(save=False)

            if old_truck and old_truck != self.truck:
                old_truck.sotilgan = False
                old_truck.save()
                self.truck.sotilgan = True
                self.truck.save()

            self.xaridor.update_financials()

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            self.bildirishnomalar.all().delete()
            self.tolovlar.all().delete()
            self.boshlangich_tolovlar.all().delete()
            if self.truck:
                self.truck.sotilgan = False
                self.truck.save()
            super().delete(*args, **kwargs)
            self.xaridor.update_financials()

    def __str__(self):
        return f"{self.truck.make} {self.truck.model} - {self.xaridor.ism_familiya}"

    class Meta:
        verbose_name = "Chiqim"
        verbose_name_plural = "Chiqimlar"
        indexes = [models.Index(fields=['sana']), models.Index(fields=['tolov_sana'])]

class BoshlangichTolov(models.Model):
    TOLOV_TURLARI = (
        ('zelle', 'Zelle'),
        ('wire_transfer', "Wire Transfer"),
        ('cash', 'Naqd'),
        ('button', 'Button'),
    )
    chiqim = models.ForeignKey(
        Chiqim,
        on_delete=models.CASCADE,
        related_name='boshlangich_tolovlar',
        verbose_name="Chiqim"
    )
    xaridor = models.ForeignKey(
        'xaridorlar.Xaridor',
        on_delete=models.CASCADE,
        verbose_name="Xaridor"
    )
    tolov_turi = models.CharField(
        max_length=20,
        choices=TOLOV_TURLARI,
        verbose_name="Tolov turi"
    )
    summa = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Tolov summasi"
    )
    firma_nomi = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Firma nomi"
    )
    bank = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Tolov qilingan bank"
    )
    izoh = models.TextField(
        blank=True,
        verbose_name="Izoh"
    )
    sana = models.DateField(
        verbose_name="To'lov sanasi"
    )
    is_partial = models.BooleanField(
        default=False,
        verbose_name="Qisman to'lov"
    )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.chiqim.update_totals()
            self.xaridor.update_financials()

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            chiqim = self.chiqim
            super().delete(*args, **kwargs)
            chiqim.update_totals()
            self.xaridor.update_financials()

    def __str__(self):
        return f"{self.xaridor.ism_familiya} - Boshlang'ich {self.tolov_turi} ({self.summa})"

    class Meta:
        verbose_name = "Boshlang'ich To'lov"
        verbose_name_plural = "Boshlang'ich To'lovlar"
        indexes = [
            models.Index(fields=['sana']),
        ]

class TolovTuri(models.Model):
    TOLOV_TURLARI = (
        ('zelle', 'Zelle'),
        ('wire_transfer', "Wire Transfer"),
        ('cash', 'Naqd'),
        ('button', 'Button'),
    )
    chiqim = models.ForeignKey(
        Chiqim,
        on_delete=models.CASCADE,
        related_name='tolovlar',
        verbose_name="Chiqim"
    )
    xaridor = models.ForeignKey(
        'xaridorlar.Xaridor',
        on_delete=models.CASCADE,
        verbose_name="Xaridor"
    )
    tolov_turi = models.CharField(
        max_length=20,
        choices=TOLOV_TURLARI,
        verbose_name="Tolov turi"
    )
    summa = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        verbose_name="Tolov summasi"
    )
    firma_nomi = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Firma nomi"
    )
    bank = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Tolov qilingan bank"
    )
    izoh = models.TextField(
        blank=True,
        verbose_name="Izoh"
    )
    sana = models.DateField(
        verbose_name="To'lov sanasi"
    )
    is_partial = models.BooleanField(
        default=False,
        verbose_name="Qisman to'lov"
    )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            super().save(*args, **kwargs)
            self.chiqim.update_totals()
            self.xaridor.update_financials()

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            chiqim = self.chiqim
            super().delete(*args, **kwargs)
            chiqim.update_totals()
            self.xaridor.update_financials()

    def __str__(self):
        return f"{self.xaridor.ism_familiya} - {self.tolov_turi} ({self.summa})"

    class Meta:
        verbose_name = "To'lov"
        verbose_name_plural = "To'lovlar"
        indexes = [
            models.Index(fields=['sana']),
        ]

class BildirishnomaManager(models.Manager):
    def active(self, user=None):
        current_date = timezone.now().date()
        queryset = self.filter(
            chiqim__qoldiq_summa__gt=0,
            status__in=['pending', 'warning', 'urgent', 'overdue']
        )
        if user and not user.is_superuser:
            queryset = queryset.filter(
                chiqim__truck__user=user,
                chiqim__xaridor__user=user
            )
        return queryset

    def next_unpaid_for_chiqim(self, chiqim_id, user=None):
        current_date = timezone.now().date()
        queryset = self.filter(
            chiqim_id=chiqim_id,
            status__in=['pending', 'warning', 'urgent', 'overdue']
        )
        if user and not user.is_superuser:
            queryset = queryset.filter(
                chiqim__truck__user=user,
                chiqim__xaridor__user=user
            )
        return queryset.order_by('tolov_sana').first()

class Bildirishnoma(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('paid', "To'langan"),
        ('overdue', 'Qarz'),
        ('urgent', 'Tez kunda'),
        ('warning', 'Ogohlantirish'),
    ]

    chiqim = models.ForeignKey(
        'Chiqim',
        on_delete=models.CASCADE,
        related_name='bildirishnomalar',
        verbose_name="Chiqim"
    )
    tolov_sana = models.DateField(verbose_name="To'lov sanasi")
    eslatma = models.BooleanField(default=False, verbose_name="Eslatildi")
    eslatish_kunlari = models.PositiveIntegerField(default=30, verbose_name="Eslatishdan oldin kunlar")
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Holati"
    )
    sana = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Yaratilgan sana"
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        verbose_name="Oxirgi yangilanish"
    )
    is_archived = models.BooleanField(
        default=False,
        verbose_name="Arxivlangan"
    )
    sms_sent = models.BooleanField(
        default=False,
        verbose_name="SMS Yuborildi"
    )

    objects = BildirishnomaManager()

    def update_status(self):
        current_date = timezone.now().date()
        days_left = (self.tolov_sana - current_date).days
        paid_for_month = sum(
            t.summa for t in self.chiqim.tolovlar.filter(
                sana__year=self.tolov_sana.year,
                sana__month=self.tolov_sana.month
            )
        )
        monthly_payment = self.chiqim.oyiga_tolov
        is_paid = paid_for_month >= monthly_payment or self.chiqim.qoldiq_summa <= 0

        if is_paid:
            self.status = 'paid'
            self.eslatma = True
        elif days_left < 0:
            self.status = 'overdue'
        elif days_left <= 3:
            self.status = 'urgent'
        elif days_left <= 7:
            self.status = 'warning'
        else:
            self.status = 'pending'

        try:
            eslatish_kunlari = int(self.eslatish_kunlari)
        except (ValueError, TypeError):
            logger.warning(f"Invalid eslatish_kunlari for Bildirishnoma ID {self.id}: {self.eslatish_kunlari}. Defaulting to 30.")
            eslatish_kunlari = 30
            self.eslatish_kunlari = eslatish_kunlari

        self.eslatma = days_left <= eslatish_kunlari and not is_paid
        self.save()

    @property
    def days_left(self):
        return (self.tolov_sana - timezone.now().date()).days

    @property
    def days_overdue(self):
        """Returns the number of days overdue if the payment date has passed."""
        days_left = self.days_left
        return abs(days_left) if days_left < 0 else 0

    @property
    def progress_percentage(self):
        if self.chiqim.narx == 0:
            return 0
        return ((self.chiqim.narx - self.chiqim.qoldiq_summa) / self.chiqim.narx) * 100

    @property
    def pending_debt(self):
        if self.status in ['pending', 'warning', 'urgent', 'overdue'] and self.tolov_sana >= timezone.now().date():
            return self.chiqim.oyiga_tolov - sum(
                t.summa for t in self.chiqim.tolovlar.filter(
                    sana__year=self.tolov_sana.year,
                    sana__month=self.tolov_sana.month
                )
            )
        return 0

    @property
    def is_active(self):
        return self.status != 'paid' and self.tolov_sana >= timezone.now().date()

    def __str__(self):
        return f"{self.chiqim.xaridor} - {self.tolov_sana} ({self.get_status_display()})"

    class Meta:
        verbose_name = "Bildirishnoma"
        verbose_name_plural = "Bildirishnomalar"
        ordering = ['tolov_sana']
        indexes = [
            models.Index(fields=['tolov_sana']),
            models.Index(fields=['status']),
        ]

class SmsLog(models.Model):
    STATUS_CHOICES = [
        ('sent', "Yuborildi"),
        ('failed', "Xato"),
    ]

    bildirishnoma = models.ForeignKey(
        Bildirishnoma,
        on_delete=models.CASCADE,
        related_name='sms_logs',
        verbose_name="Bildirishnoma"
    )
    xaridor = models.ForeignKey(
        'xaridorlar.Xaridor',
        on_delete=models.CASCADE,
        related_name='sms_logs',
        verbose_name="Xaridor"
    )
    message = models.TextField(verbose_name="SMS Matni")
    sent_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Yuborilgan Vaqt"
    )
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='sent',
        verbose_name="Holati"
    )
    error_message = models.TextField(
        blank=True,
        null=True,
        verbose_name="Xato Xabari"
    )

    def __str__(self):
        return f"{self.xaridor.ism_familiya} - {self.sent_at} ({self.get_status_display()})"

    class Meta:
        verbose_name = "SMS Tarixi"
        verbose_name_plural = "SMS Tarixlari"
        ordering = ['-sent_at']
