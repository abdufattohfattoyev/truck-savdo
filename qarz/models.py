from django.db import models
from django.contrib.auth.models import User
from trucks.models import Truck


class Qarz(models.Model):
    lender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='given_loans', verbose_name="Lender")
    borrower_name = models.CharField(max_length=100, verbose_name="Borrower Name")
    truck = models.ForeignKey(Truck, on_delete=models.SET_NULL, null=True, blank=True, related_name='loans', verbose_name="Truck")
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Loan Amount")
    remaining_amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Remaining Amount")
    given_date = models.DateField(verbose_name="Loan Issued Date", auto_now_add=True)
    payment_due_date = models.DateField(verbose_name="Payment Due Date", null=True, blank=True)
    description = models.TextField(verbose_name="Description", blank=True, null=True)
    is_paid = models.BooleanField(default=False, verbose_name="Is Paid?")
    created_date = models.DateTimeField(auto_now_add=True, verbose_name="Created Date")
    updated_date = models.DateTimeField(auto_now=True, verbose_name="Updated Date")

    def __str__(self):
        return f"{self.lender.username} -> {self.borrower_name}: ${self.amount} (Remaining: ${self.remaining_amount})"

    class Meta:
        verbose_name = "Loan"
        verbose_name_plural = "Loans"
        ordering = ['-given_date']

    def save(self, *args, **kwargs):
        if not self.pk:  # When creating a new loan
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
    qarz = models.ForeignKey(Qarz, on_delete=models.CASCADE, related_name='payments', verbose_name="Loan")
    amount = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Payment Amount")
    payment_date = models.DateField(verbose_name="Payment Date")
    description = models.TextField(verbose_name="Description", blank=True, null=True)

    def __str__(self):
        return f"Payment of ${self.amount} for {self.qarz} ({self.payment_date})"

    class Meta:
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
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