from django.db import models
from trucks.models import Truck


class Xarajat(models.Model):
    XARAJAT_TURLARI = (
        ('ta’mir', 'Ta’mir'),
        ('yoqilgi', 'Yoqilg‘i'),
        ('sug‘urta', 'Sug‘urta'),
        ('qismlar', 'Ehtiyot qismlar'),
        ('boshqa', 'Boshqa'),
    )

    truck = models.ForeignKey(
        Truck,
        on_delete=models.CASCADE,
        related_name='xarajatlar',
        verbose_name="Mashina"
    )
    xarajat_turi = models.CharField(
        max_length=50,
        choices=XARAJAT_TURLARI,
        verbose_name="Xarajat turi"
    )
    miqdor = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Miqdor (Summa)"
    )
    izoh = models.TextField(
        blank=True,
        verbose_name="Izoh"
    )
    sana = models.DateField(
        verbose_name="Sana"
    )

    def __str__(self):
        return f"{self.truck.make} uchun {self.xarajat_turi} - {self.miqdor} ({self.sana})"

    class Meta:
        verbose_name = "Xarajat"
        verbose_name_plural = "Xarajatlar"
        ordering = ['-sana']