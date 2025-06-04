from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, FileExtensionValidator
from django.core.exceptions import ValidationError
import os
import uuid
import re
from django.utils.text import slugify

def generate_unique_truck_filename(instance, filename):
    """Fayl nomini unikal qilib, truck_id asosida papkada saqlash."""
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4()}{ext}"
    truck_id = instance.truck.po_id if instance.truck else 'unknown'
    return os.path.join(f'truck_hujjatlar/{truck_id}/', slugify(unique_name))

class Truck(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='trucks',
        verbose_name="Foydalanuvchi"
    )
    po_id = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="PO raqami",
        help_text="PO-{raqam} formatida kiriting, masalan, PO-12345"
    )
    make = models.CharField(max_length=100, verbose_name="Marka")
    model = models.CharField(max_length=100, verbose_name="Model")
    year = models.PositiveIntegerField(
        verbose_name="Yil",
        validators=[MinValueValidator(1886)]
    )
    horsepower = models.PositiveIntegerField(
        verbose_name="Ot kuchi (HP)",
        validators=[MinValueValidator(1)]
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Narx",
        validators=[MinValueValidator(0.01)]
    )
    company = models.CharField(max_length=200, blank=True, verbose_name="Kompaniya nomi")
    location = models.CharField(max_length=100, verbose_name="Joylashuv")
    sotilgan = models.BooleanField(default=False, verbose_name="Sotilgan")
    description = models.TextField(blank=True, verbose_name="Tavsif")
    purchase_date = models.DateField(auto_now_add=True, verbose_name="Sotib olingan sana")
    created_date = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan sana")
    image = models.ImageField(
        upload_to='trucks/',
        blank=True,
        null=True,
        verbose_name="Rasm"
    )
    seriya = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name="Seriya raqami",
        unique=True
    )

    def clean(self):
        """po_id formatini tekshirish."""
        po_id = self.po_id.strip()
        if not po_id.startswith("PO-"):
            po_id = f"PO-{po_id}"
            self.po_id = po_id
        if not re.match(r'^PO-\d+$', po_id):
            raise ValidationError({"po_id": "PO raqami 'PO-' bilan boshlanib, faqat raqamlar bilan davom etishi kerak!"})
        if Truck.objects.filter(po_id=po_id).exclude(id=self.id).exists():
            raise ValidationError({"po_id": "Bu PO-ID allaqachon band qilingan"})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.po_id}: {self.make} {self.model} ({self.year}) - {self.user.username}"

    class Meta:
        verbose_name = "Yuk mashinasi"
        verbose_name_plural = "Yuk mashinalari"
        indexes = [
            models.Index(fields=['po_id']),
            models.Index(fields=['user', 'sotilgan']),
        ]
        ordering = ['-created_date']

class TruckHujjat(models.Model):
    truck = models.ForeignKey(
        Truck,
        on_delete=models.CASCADE,
        related_name='hujjatlar',
        verbose_name="Yuk mashinasi"
    )
    hujjat = models.FileField(
        upload_to=generate_unique_truck_filename,
        validators=[
            FileExtensionValidator(allowed_extensions=['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx'])
        ],
        verbose_name="Hujjat fayli"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True, verbose_name="Yuklangan sana")

    def __str__(self):
        return f"{self.truck.po_id} - {os.path.basename(self.hujjat.name)}"

    class Meta:
        verbose_name = "Yuk mashinasi hujjati"
        verbose_name_plural = "Yuk mashinasi hujjatlari"
        indexes = [
            models.Index(fields=['truck']),
        ]