import bleach
from django import forms
from django.utils import timezone

from trucks.models import Truck
from xaridorlar.models import Xaridor
from .models import Chiqim, TolovTuri
import logging
from django.db import transaction

logger = logging.getLogger(__name__)

class ChiqimForm(forms.ModelForm):
    class Meta:
        model = Chiqim
        fields = ['truck', 'xaridor', 'narx', 'tolangan_summa', 'hujjatlar', 'bo_lib_tolov_muddat', 'tolov_sana', 'izoh']
        widgets = {
            'tolov_sana': forms.DateInput(attrs={'type': 'date'}),
            'hujjatlar': forms.ClearableFileInput(),
        }

    def __init__(self, *args, user=None, instance=None, **kwargs):
        self.initial_instance = instance
        self.initial_truck = instance.truck if instance else None
        super().__init__(*args, instance=instance, **kwargs)
        if user:
            if not user.is_superuser:
                self.fields['truck'].queryset = Truck.objects.filter(user=user, sotilgan=False)
                self.fields['xaridor'].queryset = Xaridor.objects.filter(user=user)
            else:
                self.fields['truck'].queryset = Truck.objects.filter(sotilgan=False)
                self.fields['xaridor'].queryset = Xaridor.objects.all()
        else:
            self.fields['truck'].queryset = Truck.objects.none()
            self.fields['xaridor'].queryset = Xaridor.objects.none()

        if instance and instance.truck:
            self.fields['truck'].queryset = (self.fields['truck'].queryset | Truck.objects.filter(id=instance.truck.id)).distinct()
        self.fields['truck'].label_from_instance = lambda obj: f"{obj.make} {obj.model} {'(Series: ' + str(obj.seriya) + ')' if obj.seriya else ''}"
        logger.debug(f"Truck queryset: {self.fields['truck'].queryset.values('id', 'make', 'model', 'sotilgan')}")
        logger.debug(f"Customer queryset: {self.fields['xaridor'].queryset.values('id', 'ism_familiya', 'user__username')}")

        # Make tolov_sana field required
        self.fields['tolov_sana'].required = True

    def save(self, commit=True):
        chiqim = super().save(commit=False)
        old_truck = self.initial_truck
        if commit:
            with transaction.atomic():
                if not self.initial_instance:
                    chiqim.truck.sotilgan = True
                    chiqim.truck.save()
                elif old_truck and old_truck != chiqim.truck:
                    old_truck.sotilgan = False
                    old_truck.save()
                    chiqim.truck.sotilgan = True
                    chiqim.truck.save()
                chiqim.save()
                chiqim.qoldiq_summa = chiqim.narx - chiqim.tolangan_summa
                if chiqim.bo_lib_tolov_muddat and chiqim.qoldiq_summa > 0:
                    chiqim.oyiga_tolov = chiqim.qoldiq_summa / chiqim.bo_lib_tolov_muddat
                chiqim.save()
        return chiqim

    def clean(self):
        cleaned_data = super().clean()
        narx = cleaned_data.get('narx')
        tolangan_summa = cleaned_data.get('tolangan_summa', 0)
        truck = cleaned_data.get('truck')
        xaridor = cleaned_data.get('xaridor')
        tolov_sana = cleaned_data.get('tolov_sana')
        user = self.initial.get('user')

        if narx and tolangan_summa > narx:
            raise forms.ValidationError("The paid amount cannot exceed the price!")
        if truck and truck.sotilgan and (not self.initial_instance or truck != self.initial_instance.truck):
            raise forms.ValidationError("This vehicle has already been sold!")
        if user and not user.is_superuser and xaridor and xaridor.user != user:
            raise forms.ValidationError("This customer does not belong to you!")
        if tolov_sana and tolov_sana < timezone.now().date():
            raise forms.ValidationError("The first payment date cannot be in the past!")
        return cleaned_data


class TolovForm(forms.ModelForm):
    class Meta:
        model = TolovTuri
        fields = ['tolov_turi', 'summa', 'firma_nomi', 'bank', 'izoh']

    def clean_firma_nomi(self):
        firma_nomi = self.cleaned_data.get('firma_nomi')
        if firma_nomi:
            firma_nomi = bleach.clean(firma_nomi, tags=[], strip=True)
        return firma_nomi

    def clean_bank(self):
        bank = self.cleaned_data.get('bank')
        if bank:
            bank = bleach.clean(bank, tags=[], strip=True)
        return bank

    def clean_izoh(self):
        izoh = self.cleaned_data.get('izoh')
        if izoh:
            izoh = bleach.clean(izoh, tags=[], strip=True)
        return izoh

    def clean(self):
        cleaned_data = super().clean()
        summa = cleaned_data.get('summa')
        chiqim = self.initial.get('chiqim')  # Chiqim must be passed when the form is created
        if chiqim and summa:
            if summa > chiqim.qoldiq_summa:
                raise forms.ValidationError(
                    f"The payment amount cannot exceed the remaining balance (${chiqim.qoldiq_summa:,.2f})!"
                )
        return cleaned_data