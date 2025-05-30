from django.db import models
from django.contrib.auth.models import User
from trucks.models import Truck


class Qarz(models.Model):
    lender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_qarzlar', verbose_name="Qarz beruvchi")
    borrower = models.ForeignKey(User, on_delete=models.CASCADE, related_name='taken_qarzlar', verbose_name="Qarz oluvchi")
    truck = models.ForeignKey(Truck, on_delete=models.SET_NULL, null=True, blank=True, related_name='qarzlar', verbose_name="Mashina")
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Qarz miqdori")
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Qoldiq miqdor")
    given_date = models.DateField(verbose_name="Qarz berilgan sana", auto_now_add=True)
    payment_due_date = models.DateField(verbose_name="To‘lov muddati", null=True, blank=True)
    description = models.TextField(verbose_name="Izoh", blank=True, null=True)
    is_paid = models.BooleanField(default=False, verbose_name="To‘langanmi?")
    created_date = models.DateTimeField(auto_now_add=True, verbose_name="Yaratilgan sana")
    updated_date = models.DateTimeField(auto_now=True, verbose_name="O‘zgartirilgan sana")

    def __str__(self):
        return f"{self.lender.username} -> {self.borrower.username}: {self.amount} (Qoldiq: {self.remaining_amount})"

    class Meta:
        verbose_name = "Qarz"
        verbose_name_plural = "Qarzlar"
        ordering = ['-given_date']

    def save(self, *args, **kwargs):
        if not self.pk:  # Yangi qarz yaratilganda
            self.remaining_amount = self.amount
        if self.is_paid:
            self.remaining_amount = 0
        super().save(*args, **kwargs)

    @property
    def percentage_paid(self):
        if self.amount > 0:
            return (1 - self.remaining_amount / self.amount) * 100
        return 0

    def get_paid_amount(self):
        return self.amount - self.remaining_amount


class Payment(models.Model):
    qarz = models.ForeignKey(Qarz, on_delete=models.CASCADE, related_name='payments', verbose_name="Qarz")
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="To‘lov miqdori")
    payment_date = models.DateField(verbose_name="To‘lov sanasi", auto_now_add=True)
    description = models.TextField(verbose_name="Izoh", blank=True, null=True)

    def __str__(self):
        return f"{self.qarz} uchun {self.amount} to‘lov ({self.payment_date})"

    class Meta:
        verbose_name = "To‘lov"
        verbose_name_plural = "To‘lovlar"
        ordering = ['-payment_date']

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        total_payments = self.qarz.payments.aggregate(models.Sum('amount'))['amount__sum'] or 0
        self.qarz.remaining_amount = self.qarz.amount - total_payments
        if self.qarz.remaining_amount <= 0:
            self.qarz.is_paid = True
            self.qarz.remaining_amount = 0
        else:
            self.qarz.is_paid = False
        self.qarz.save()