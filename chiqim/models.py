import calendar
import logging
from django.db import models, transaction
from django.utils import timezone
from trucks.models import Truck
logger = logging.getLogger(__name__)


class Chiqim(models.Model):
    truck = models.ForeignKey(Truck, on_delete=models.CASCADE, related_name='chiqim', verbose_name="Mashina")
    xaridor = models.ForeignKey('xaridorlar.Xaridor', on_delete=models.CASCADE, related_name='chiqim', verbose_name="Xaridor")
    narx = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Umumiy narx")
    tolangan_summa = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Boshlang'ich to'lov")
    qoldiq_summa = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Qoldiq summa")
    hujjatlar = models.FileField(upload_to='chiqim_documents/', blank=True, null=True, verbose_name="Hujjatlar")
    bo_lib_tolov_muddat = models.PositiveIntegerField(default=0, verbose_name="Bo'lib to'lash muddati (oy)")
    oyiga_tolov = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True, verbose_name="Oyiga to'lov")
    tolov_sana = models.DateField(verbose_name="Birinchi to'lov sanasi")
    izoh = models.TextField(blank=True, verbose_name="Izoh")
    sana = models.DateField(auto_now_add=True, verbose_name="Sotish sanasi")

    def get_total_paid(self):
        """Calculate total paid amount: initial payment + all subsequent payments."""
        subsequent_payments = sum(tolov.summa for tolov in self.tolovlar.all())
        return self.tolangan_summa + subsequent_payments

    def update_totals(self):
        """Update the remaining debt without recalculating monthly installment unless necessary."""
        total_paid = self.get_total_paid()
        self.qoldiq_summa = max(0, self.narx - total_paid)
        logger.debug(f"Hisoblandi: total_paid={total_paid}, narx={self.narx}, qoldiq_summa={self.qoldiq_summa}")
        if self.qoldiq_summa <= 0:
            self.bo_lib_tolov_muddat = 0
            self.oyiga_tolov = 0
            self.bildirishnomalar.all().delete()

    def calculate_monthly_payment(self):
        """Calculate the monthly payment based on initial remaining amount."""
        remaining_amount = self.narx - self.tolangan_summa
        if self.bo_lib_tolov_muddat > 0 and remaining_amount > 0:
            self.oyiga_tolov = remaining_amount / self.bo_lib_tolov_muddat
        else:
            self.oyiga_tolov = 0
        self.qoldiq_summa = remaining_amount

    def get_next_unpaid_month(self):
        current_date = timezone.now().date()
        unpaid_notifications = self.bildirishnomalar.filter(
            status__in=['pending', 'warning', 'urgent', 'overdue'],
            tolov_sana__gte=current_date
        ).order_by('tolov_sana')
        return unpaid_notifications.first()

    def update_notifications(self):
        if self.qoldiq_summa <= 0 or not self.tolov_sana or self.bo_lib_tolov_muddat <= 0:
            self.bo_lib_tolov_muddat = 0
            self.oyiga_tolov = 0
            self.bildirishnomalar.all().delete()
            return

        # Har safar bildirishnomalarni to'liq qayta yaratish uchun avval o'chirish
        self.bildirishnomalar.all().delete()

        current_date = timezone.now().date()
        monthly_payment = self.oyiga_tolov
        total_paid = self.get_total_paid()
        remaining_payment = total_paid - self.tolangan_summa  # Only subsequent payments
        total_months = self.bo_lib_tolov_muddat
        start_date = self.tolov_sana
        target_day = start_date.day

        logger.debug(
            f"Update notifications: total_paid={total_paid}, monthly_payment={monthly_payment}, total_months={total_months}, start_date={start_date}"
        )

        # Har bir oy uchun to'lov sanasini hisoblash va bildirishnoma yaratish
        for month in range(total_months):
            next_month = start_date.month + month
            next_year = start_date.year + (next_month - 1) // 12
            next_month = (next_month - 1) % 12 + 1
            last_day_of_month = calendar.monthrange(next_year, next_month)[1]
            payment_day = min(target_day, last_day_of_month)
            payment_date = start_date.replace(year=next_year, month=next_month, day=payment_day)

            notification = Bildirishnoma.objects.create(
                chiqim=self,
                tolov_sana=payment_date,
                eslatish_kunlari=30  # Default eslatish kuni
            )

            days_left = (notification.tolov_sana - current_date).days
            paid_for_month = sum(
                t.summa for t in self.tolovlar.filter(
                    sana__year=payment_date.year,
                    sana__month=payment_date.month
                )
            )
            is_paid = paid_for_month >= monthly_payment or remaining_payment >= monthly_payment

            if is_paid:
                notification.status = 'paid'
                notification.eslatma = True
                remaining_payment -= monthly_payment
            else:
                if days_left < 0:
                    notification.status = 'overdue'
                elif days_left <= 3:
                    notification.status = 'urgent'
                elif days_left <= 7:
                    notification.status = 'warning'
                else:
                    notification.status = 'pending'
                notification.eslatma = days_left <= notification.eslatish_kunlari
            notification.save()
            logger.debug(
                f"To'lov holati: {notification.tolov_sana} -> {notification.status}, qoldi: {days_left} kun, qoldiq to'lov: {remaining_payment}, paid_for_month={paid_for_month}"
            )

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.pk:
                # Yangi Chiqim yaratilmoqda
                if self.truck:
                    self.truck.sotilgan = True
                    self.truck.save()
                self.calculate_monthly_payment()  # Calculate initial monthly payment
                super().save(*args, **kwargs)  # Save first to get PK
                self.update_totals()  # Update totals after getting PK
            else:
                # Mavjud Chiqim yangilanmoqda
                old_instance = Chiqim.objects.get(pk=self.pk)
                old_truck = old_instance.truck

                # Agar truck o'zgargan bo'lsa
                if old_truck != self.truck:
                    # Avvalgi truck sotilgan=False qilinadi
                    old_truck.sotilgan = False
                    old_truck.save()
                    logger.debug(f"Avvalgi truck {old_truck.id} sotilgan=False qilindi")

                    # Yangi truck sotilgan=True qilinadi
                    self.truck.sotilgan = True
                    self.truck.save()
                    logger.debug(f"Yangi truck {self.truck.id} sotilgan=True qilindi")

                # Agar tolangan_summa yoki muddat o'zgargan bo'lsa
                if self.tolangan_summa != old_instance.tolangan_summa or self.bo_lib_tolov_muddat != old_instance.bo_lib_tolov_muddat:
                    self.calculate_monthly_payment()
                    self.bildirishnomalar.all().delete()  # Clear and recreate notifications
                self.update_totals()

            super().save(*args, **kwargs)  # Save again if updated
            self.update_notifications()
            from xaridorlar.models import Xaridor
            self.xaridor.hozirgi_balans = self.qoldiq_summa  # Hozirgi balansni qoldiq summaga tenglashtirish
            self.xaridor.save(update_fields=['hozirgi_balans'])

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            # Explicitly delete related objects to ensure CASCADE works
            self.bildirishnomalar.all().delete()
            self.tolovlar.all().delete()

            # Chiqim o'chirilganda truck sotilgan=False qilinadi
            if self.truck:
                self.truck.sotilgan = False
                self.truck.save()
                logger.debug(f"Chiqim o'chirildi, truck {self.truck.id} sotilgan=False qilindi")
            super().delete(*args, **kwargs)
            from xaridorlar.models import Xaridor
            self.xaridor.hozirgi_balans = 0  # Chiqim o'chirilganda balans 0 ga teng
            self.xaridor.save(update_fields=['hozirgi_balans'])

    def __str__(self):
        return f"{self.truck.make} {self.truck.model} - {self.xaridor.ism_familiya}"

    class Meta:
        verbose_name = "Chiqim"
        verbose_name_plural = "Chiqimlar"
        indexes = [
            models.Index(fields=['sana']),
            models.Index(fields=['tolov_sana']),
        ]

class TolovTuri(models.Model):
    TOLOV_TURLARI = (
        ('zelle', 'Zelle'),
        ('wire_transfer', "Wire Transfer"),
        ('cash', 'Naqd'),
        ('button', 'Button'),
    )
    chiqim = models.ForeignKey(Chiqim, on_delete=models.CASCADE, related_name='tolovlar', verbose_name="Chiqim")
    xaridor = models.ForeignKey('xaridorlar.Xaridor', on_delete=models.CASCADE, verbose_name="Xaridor")
    tolov_turi = models.CharField(max_length=20, choices=TOLOV_TURLARI, verbose_name="Tolov turi")
    summa = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Tolov summasi")
    firma_nomi = models.CharField(max_length=200, blank=True, verbose_name="Firma nomi")
    bank = models.CharField(max_length=100, blank=True, verbose_name="Tolov qilingan bank")
    izoh = models.TextField(blank=True, verbose_name="Izoh")
    sana = models.DateField(auto_now_add=True, verbose_name="To'lov sanasi")
    is_partial = models.BooleanField(default=False, verbose_name="Qisman to'lov")

    def save(self, *args, **kwargs):
        with transaction.atomic():
            logger.debug(f"Saving TolovTuri: chiqim_id={self.chiqim_id}, summa={self.summa}, sana={self.sana}")
            super().save(*args, **kwargs)
            self.chiqim.update_totals()
            self.chiqim.save()
            self.chiqim.update_notifications()
            from xaridorlar.models import Xaridor
            self.xaridor.hozirgi_balans = self.chiqim.qoldiq_summa  # Hozirgi balansni qoldiq summaga tenglashtirish
            self.xaridor.save(update_fields=['hozirgi_balans'])

    def delete(self, *args, **kwargs):
        with transaction.atomic():
            chiqim = self.chiqim
            from xaridorlar.models import Xaridor
            xaridor = self.xaridor
            super().delete(*args, **kwargs)
            chiqim.update_totals()
            chiqim.save()
            chiqim.update_notifications()
            xaridor.hozirgi_balans = chiqim.qoldiq_summa  # Balansni yangilangan qoldiq summaga tenglashtirish
            xaridor.save(update_fields=['hozirgi_balans'])

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
        if user and not user.is_superuser:
            return self.filter(
                chiqim__truck__user=user,
                chiqim__xaridor__user=user,
                tolov_sana__gte=current_date,
                chiqim__qoldiq_summa__gt=0,
                status__in=['pending', 'warning', 'urgent', 'overdue']
            )
        return self.filter(
            tolov_sana__gte=current_date,
            chiqim__qoldiq_summa__gt=0,
            status__in=['pending', 'warning', 'urgent', 'overdue']
        )

    def next_unpaid_for_chiqim(self, chiqim_id, user=None):
        current_date = timezone.now().date()
        if user and not user.is_superuser:
            return self.filter(
                chiqim_id=chiqim_id,
                chiqim__truck__user=user,
                chiqim__xaridor__user=user,
                tolov_sana__gte=current_date,
                status__in=['pending', 'warning', 'urgent', 'overdue']
            ).order_by('tolov_sana').first()
        return self.filter(
            chiqim_id=chiqim_id,
            tolov_sana__gte=current_date,
            status__in=['pending', 'warning', 'urgent', 'overdue']
        ).order_by('tolov_sana').first()

class Bildirishnoma(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Kutilmoqda'),
        ('paid', "To'langan"),
        ('overdue', 'Qarz'),
        ('urgent', 'Tez kunda'),
        ('warning', 'Ogohlantirish'),
    ]

    chiqim = models.ForeignKey(Chiqim, on_delete=models.CASCADE, related_name='bildirishnomalar', verbose_name="Chiqim")
    tolov_sana = models.DateField(verbose_name="To'lov sanasi")
    eslatma = models.BooleanField(default=False, verbose_name="Eslatildi")
    eslatish_kunlari = models.PositiveIntegerField(default=30, verbose_name="Eslatishdan oldin kunlar")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending', verbose_name="Holati")
    sana = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan sana")
    last_updated = models.DateTimeField(auto_now=True, verbose_name="Oxirgi yangilanish")
    is_archived = models.BooleanField(default=False, verbose_name="Arxivlangan")
    sms_sent = models.BooleanField(default=False, verbose_name="SMS Yuborildi")

    objects = BildirishnomaManager()

    def save(self, *args, **kwargs):
        current_date = timezone.now().date()
        days_left = (self.tolov_sana - current_date).days

        paid_for_month = sum(
            t.summa for t in self.chiqim.tolovlar.filter(
                sana__year=self.tolov_sana.year,
                sana__month=self.tolov_sana.month
            )
        )
        monthly_payment = self.chiqim.oyiga_tolov
        total_paid = self.chiqim.get_total_paid() - self.chiqim.tolangan_summa
        previous_months = self.chiqim.bildirishnomalar.filter(
            tolov_sana__lt=self.tolov_sana
        ).count()
        previous_months_payment = previous_months * monthly_payment
        remaining_payment = total_paid - previous_months_payment
        is_paid = paid_for_month >= monthly_payment or remaining_payment >= monthly_payment or self.chiqim.qoldiq_summa <= 0

        logger.debug(
            f"To'lov hisoblandi: {paid_for_month} / {monthly_payment} for {self.tolov_sana}, is_paid={is_paid}"
        )

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
        except (ValueError, TypeError) as e:
            logger.warning(
                f"Invalid eslatish_kunlari for Bildirishnoma ID {self.id}: {self.eslatish_kunlari}. Defaulting to 30."
            )
            eslatish_kunlari = 30
            self.eslatish_kunlari = eslatish_kunlari

        if days_left <= eslatish_kunlari and not is_paid:
            self.eslatma = True

        super().save(*args, **kwargs)

    @property
    def days_left(self):
        days = (self.tolov_sana - timezone.now().date()).days
        return max(0, days)

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

    bildirishnoma = models.ForeignKey('Bildirishnoma', on_delete=models.CASCADE, related_name='sms_logs', verbose_name="Bildirishnoma")
    xaridor = models.ForeignKey('xaridorlar.Xaridor', on_delete=models.CASCADE, related_name='sms_logs', verbose_name="Xaridor")
    message = models.TextField(verbose_name="SMS Matni")
    sent_at = models.DateTimeField(auto_now_add=True, verbose_name="Yuborilgan Vaqt")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='sent', verbose_name="Holati")
    error_message = models.TextField(blank=True, null=True, verbose_name="Xato Xabari")

    def __str__(self):
        return f"{self.xaridor.ism_familiya} - {self.sent_at} ({self.get_status_display()})"

    class Meta:
        verbose_name = "SMS Tarixi"
        verbose_name_plural = "SMS Tarixlari"
        ordering = ['-sent_at']

    def save(self, *args, **kwargs):
        if not self.pk and hasattr(self, 'bildirishnoma') and self.bildirishnoma:
            # Faqat ruxsatli foydalanuvchi uchun saqlash
            if not self.bildirishnoma.chiqim.truck.user.is_superuser and self.bildirishnoma.chiqim.truck.user != self.xaridor.user:
                raise ValueError("Sizga bu SMS tarixini saqlashga ruxsat yo'q!")
        super().save(*args, **kwargs)
