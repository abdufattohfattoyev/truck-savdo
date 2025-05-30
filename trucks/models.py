from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator  # MinValueValidator import qilindi

class Truck(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='trucks',
        verbose_name="Foydalanuvchi"
    )
    make = models.CharField(max_length=100, verbose_name="Mashina nomi (Make)")
    model = models.CharField(max_length=100, verbose_name="Mashina nusxasi (Model)")
    year = models.PositiveIntegerField(
        verbose_name="Yili (Year)",
        validators=[MinValueValidator(1886)]  # 1886 yildan kichik bo‘lmasligi kerak
    )
    horsepower = models.PositiveIntegerField(
        verbose_name="Ot kuchi (HP)",
        validators=[MinValueValidator(1)]  # 1 dan kichik bo‘lmasligi kerak
    )
    price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Narxi (Price)",
        validators=[MinValueValidator(0.01)]  # 0.01 dan kichik bo‘lmasligi kerak
    )
    company = models.CharField(max_length=200, blank=True, verbose_name="Kompaniya nomi")
    location = models.CharField(max_length=100, verbose_name="Shtat (Location)")
    documents = models.FileField(
        upload_to='documents/',
        blank=True,
        null=True,
        verbose_name="Dokumentlar"
    )
    sotilgan = models.BooleanField(default=False, verbose_name="Sotilgan")
    description = models.TextField(blank=True, verbose_name="Izoh")
    purchase_date = models.DateField(auto_now_add=True, verbose_name="Sotib olingan sana")
    created_date = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan sana")
    image = models.ImageField(
        upload_to='trucks/',
        blank=True,
        null=True,
        verbose_name="Rasm"
    )
    seriya = models.IntegerField(
        blank=True,
        null=True,
        verbose_name="Seriya raqami",
        unique=True  # Seriya raqami noyob bo‘lishi uchun
    )

    def __str__(self):
        return f"{self.make} {self.model} ({self.year}) - {self.user.username}"

    class Meta:
        verbose_name = "Truck"
        verbose_name_plural = "Trucks"
        indexes = [
            models.Index(fields=['user', 'sotilgan', '-created_date']),
            models.Index(fields=['make', 'model']),
            models.Index(fields=['seriya']),
        ]
        ordering = ['-created_date']