from django.db import models
from trucks.models import Truck
from django.utils import timezone
import os

def xarajat_document_upload_path(instance, filename):
    """Generate upload path for document with original filename."""
    return f'xarajat_documents/{instance.truck.id}/{filename}'

class Xarajat(models.Model):
    EXPENSE_TYPES = (
        ('repair', 'Repair'),
        ('fuel', 'Fuel'),
        ('insurance', 'Insurance'),
        ('parts', 'Spare Parts'),
        ('other', 'Other'),
    )

    truck = models.ForeignKey(
        Truck,
        on_delete=models.CASCADE,
        related_name='expenses',
        verbose_name="Truck"
    )
    expense_type = models.CharField(
        max_length=50,
        choices=EXPENSE_TYPES,
        verbose_name="Expense Type"
    )
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Amount"
    )
    description = models.TextField(
        blank=True,
        verbose_name="Description"
    )
    date = models.DateField(
        verbose_name="Date",
        default=timezone.now  # Updated to use dynamic current date
    )
    document = models.FileField(
        upload_to=xarajat_document_upload_path,
        blank=True,
        null=True,
        verbose_name="Document"
    )

    def __str__(self):
        return f"{self.truck.make} - {self.expense_type} - {self.amount} ({self.date})"

    def get_document_name(self):
        """Return the original document name if it exists."""
        if self.document:
            return os.path.basename(self.document.name)
        return None

    class Meta:
        verbose_name = "Expense"
        verbose_name_plural = "Expenses"
        ordering = ['-date']