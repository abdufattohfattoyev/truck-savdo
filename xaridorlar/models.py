from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, FileExtensionValidator
import os
import uuid
import phonenumbers
from django.core.exceptions import ValidationError
from django.db.models import Sum


def generate_unique_filename(instance, filename):
    """Fayl nomini noyob qilish uchun UUID ishlatamiz, lekin asl nom saqlanadi."""
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4()}{ext}"
    return os.path.join('passports/', unique_name)

class Xaridor(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='xaridorlar', verbose_name="Foydalanuvchi")
    ism_familiya = models.CharField(max_length=100, verbose_name="Ism va Familiya")
    telefon_raqam = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        verbose_name="Telefon Raqam",
    )
    hozirgi_balans = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Hozirgi Balans",
        blank=True
    )
    sana = models.DateField(verbose_name="Sana")
    izoh = models.TextField(verbose_name="Izoh", blank=True, null=True)
    created_date = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan sana")

    def clean(self):
        """Telefon raqamini validatsiya qilish."""
        if self.telefon_raqam:
            try:
                parsed_number = phonenumbers.parse(self.telefon_raqam, None)
                if not phonenumbers.is_valid_number(parsed_number):
                    raise ValidationError("Telefon raqami to'g'ri formatda emas!")
                self.telefon_raqam = phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
            except phonenumbers.NumberParseException:
                raise ValidationError("Telefon raqami noto'g'ri formatda!")

    def update_financials(self):
        """Hozirgi balansni yangilash: agar xarid bo'lmasa 0, aks holda qoldiq_summa summasi."""
        from chiqim.models import Chiqim
        chiqimlar = Chiqim.objects.filter(xaridor=self)
        if not chiqimlar.exists():
            self.hozirgi_balans = 0  # Xarid bo'lmasa 0
        else:
            total_debt = chiqimlar.aggregate(total=Sum('qoldiq_summa'))['total'] or 0
            self.hozirgi_balans = total_debt  # Qoldiq summaga teng
        self.save(update_fields=['hozirgi_balans'])

    @property
    def total_debt(self):
        from chiqim.models import Chiqim
        chiqimlar = Chiqim.objects.filter(xaridor=self)
        if not chiqimlar.exists():
            return 0  # Xarid bo'lmasa 0
        return chiqimlar.aggregate(total=Sum('qoldiq_summa'))['total'] or 0

    def __str__(self):
        return f"{self.ism_familiya} - {self.user.username}"

    class Meta:
        verbose_name = "Xaridor"
        verbose_name_plural = "Xaridorlar"

class XaridorHujjat(models.Model):
    xaridor = models.ForeignKey(Xaridor, on_delete=models.CASCADE, related_name='hujjatlar')
    hujjat = models.FileField(
        upload_to='xaridor_hujjatlar/',
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx'])
        ],
        verbose_name="Hujjat fayli"
    )
    original_file_name = models.CharField(max_length=255, verbose_name="Asl fayl nomi")
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Yuklangan vaqt")

    def save(self, *args, **kwargs):
        if not self.original_file_name:
            self.original_file_name = self.hujjat.name
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.xaridor.ism_familiya} - {self.original_file_name}"

    class Meta:
        verbose_name = "Xaridor hujjati"
        verbose_name_plural = "Xaridor hujjatlari"