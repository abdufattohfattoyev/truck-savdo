from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.utils.text import slugify
import os
from phonenumber_field.modelfields import PhoneNumberField
from django.core.exceptions import ValidationError
from django.conf import settings

def generate_unique_filename(instance, filename):
    """Generate a filename preserving the original name, with a suffix if needed."""
    base, ext = os.path.splitext(filename)
    slug = slugify(base)
    new_filename = f"{slug}{ext}"
    upload_dir = 'xaridor_hujjatlar/'
    full_path = os.path.join(upload_dir, new_filename)

    counter = 1
    while os.path.exists(os.path.join(settings.MEDIA_ROOT, full_path)):
        new_filename = f"{slug}_{counter}{ext}"
        full_path = os.path.join(upload_dir, new_filename)
        counter += 1

    return full_path

def validate_file_size(value):
    """File size validator (10MB limit)."""
    limit = 10 * 1024 * 1024  # 10MB in bytes
    if value.size > limit:
        raise ValidationError("Fayl hajmi 10MB dan kichik bo‘lishi kerak.")

class Xaridor(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='xaridorlar',
        verbose_name="Foydalanuvchi"
    )
    ism_familiya = models.CharField(
        max_length=100,
        verbose_name="Ism va Familiya"
    )
    telefon_raqam = PhoneNumberField(
        blank=True,
        null=True,
        verbose_name="Telefon Raqam",
        help_text="Masalan: +998901234567"
    )
    hozirgi_balans = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Hozirgi Balans",
        blank=True
    )
    sana = models.DateField(verbose_name="Sana")
    izoh = models.TextField(
        verbose_name="Izoh",
        blank=True,
        null=True
    )
    created_date = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Yaratilgan sana"
    )

    def update_financials(self):
        """Update current balance."""
        from chiqim.models import Chiqim
        total_debt = Chiqim.objects.filter(xaridor=self).aggregate(total=models.Sum('qoldiq_summa'))['total'] or 0
        self.hozirgi_balans = total_debt
        self.save(update_fields=['hozirgi_balans'])

    @property
    def total_debt(self):
        """Calculate total debt."""
        from chiqim.models import Chiqim
        return Chiqim.objects.filter(xaridor=self).aggregate(total=models.Sum('qoldiq_summa'))['total'] or 0

    def __str__(self):
        return f"{self.ism_familiya} - {self.user.username}"

    class Meta:
        verbose_name = "Xaridor"
        verbose_name_plural = "Xaridorlar"
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['ism_familiya']),
        ]

class XaridorHujjat(models.Model):
    xaridor = models.ForeignKey(
        Xaridor,
        on_delete=models.CASCADE,
        related_name='hujjatlar',
        verbose_name="Xaridor"
    )
    hujjat = models.FileField(
        upload_to=generate_unique_filename,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']),
            validate_file_size
        ],
        verbose_name="Hujjat fayli"
    )
    original_filename = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Asl fayl nomi"
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Yuklangan vaqt"
    )

    def save(self, *args, **kwargs):
        """Save the original filename before saving the file."""
        if self.hujjat and not self.original_filename:
            self.original_filename = self.hujjat.name  # Store original name
        super().save(*args, **kwargs)  # Call parent save method

    def __str__(self):
        return f"{self.xaridor.ism_familiya} - {self.original_filename or os.path.basename(self.hujjat.name)}"

    class Meta:
        verbose_name = "Xaridor hujjati"
        verbose_name_plural = "Xaridor hujjatlari"
        indexes = [
            models.Index(fields=['xaridor']),
        ]