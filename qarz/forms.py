from django import forms
from .models import Qarz, Payment
from django.contrib.auth.models import User
from trucks.models import Truck

class QarzForm(forms.ModelForm):
    borrower = forms.ModelChoiceField(queryset=User.objects.all(), label="Qarz Oluvchi", widget=forms.Select(attrs={'class': 'form-select'}))
    truck = forms.ModelChoiceField(queryset=Truck.objects.all(), label="Mashina (Ixtiyoriy)", required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    payment_due_date = forms.DateField(label="To‘lov Muddat", required=False, widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    amount = forms.DecimalField(label="Qarz Miqdori ($)", widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}))
    description = forms.CharField(label="Izoh", required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))
    is_paid = forms.BooleanField(label="To‘langan", required=False, widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}))

    class Meta:
        model = Qarz
        fields = ['borrower', 'truck', 'amount', 'payment_due_date', 'description', 'is_paid']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['borrower'].queryset = User.objects.exclude(id=user.id)
            self.fields['truck'].queryset = Truck.objects.filter(user=user)

class PaymentForm(forms.ModelForm):
    amount = forms.DecimalField(label="To‘lov Miqdori ($)", widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}))
    description = forms.CharField(label="Izoh", required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}))

    class Meta:
        model = Payment
        fields = ['amount', 'description']