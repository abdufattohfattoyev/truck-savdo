from django import forms
from .models import Xaridor, XaridorHujjat
import phonenumbers
from django.core.exceptions import ValidationError

class MultiFileInput(forms.ClearableFileInput):
    """Ko'p fayl yuklashni qo'llab-quvvatlaydigan maxsus widget."""
    allow_multiple_selected = True

    def __init__(self, attrs=None):
        if attrs is not None:
            attrs = attrs.copy()
            attrs['multiple'] = True
        else:
            attrs = {'multiple': True}
        super().__init__(attrs)

class XaridorForm(forms.ModelForm):
    class Meta:
        model = Xaridor
        fields = ['ism_familiya', 'telefon_raqam', 'hozirgi_balans', 'sana', 'izoh']
        widgets = {
            'ism_familiya': forms.TextInput(attrs={
                'class': 'form-control',
                'required': True,
                'placeholder': 'Ism va Familiya (masalan, Ali Valiyev)',
            }),
            'telefon_raqam': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+12025550123 (har qanday davlat kodi bilan)',
                'pattern': '[+][0-9]{1,15}',
            }),
            'hozirgi_balans': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
                'readonly': True,
            }),
            'sana': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
                'required': True,
            }),
            'izoh': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': "Qo'shimcha izohlar (ixtiyoriy)",
            }),
        }
        labels = {
            'ism_familiya': "Ism va Familiya",
            'telefon_raqam': "Telefon Raqam",
            'hozirgi_balans': "Hozirgi Balans",
            'sana': "Sana",
            'izoh': "Izoh (ixtiyoriy)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hozirgi_balans'].disabled = True
        if self.instance and self.instance.pk:
            self.instance.update_financials()
            self.fields['hozirgi_balans'].initial = self.instance.hozirgi_balans

    def clean_telefon_raqam(self):
        telefon_raqam = self.cleaned_data.get('telefon_raqam')
        if not telefon_raqam:
            raise ValidationError("Telefon raqami majburiy!")
        try:
            parsed_number = phonenumbers.parse(telefon_raqam, None)
            if not phonenumbers.is_valid_number(parsed_number):
                raise ValidationError(
                    "Telefon raqami to'g'ri formatda emas! Iltimos, + va davlat kodi bilan kiriting (masalan, +998901234567)."
                )
            return phonenumbers.format_number(parsed_number, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            raise ValidationError(
                "Telefon raqami noto'g'ri formatda! Iltimos, + va davlat kodi bilan kiriting (masalan, +998901234567)."
            )

    def clean_ism_familiya(self):
        ism_familiya = self.cleaned_data.get('ism_familiya')
        if not ism_familiya or len(ism_familiya.strip()) < 3:
            raise ValidationError("Ism va familiya kamida 3 harfdan iborat bo'lishi kerak!")
        return ism_familiya

    def clean_sana(self):
        sana = self.cleaned_data.get('sana')
        if not sana:
            raise ValidationError("Sana majburiy!")
        from datetime import date
        if sana > date.today():
            raise ValidationError("Sana kelajakdagi sana bo'lishi mumkin emas!")
        return sana

class XaridorHujjatForm(forms.ModelForm):
    class Meta:
        model = XaridorHujjat
        fields = ['hujjat']
        widgets = {
            'hujjat': MultiFileInput(attrs={
                'class': 'form-control',
                'accept': '.jpg,.jpeg,.png,application/pdf,.doc,.docx',
                'multiple': True,
                'id': 'hujjat-input',
            }),
        }
        labels = {
            'hujjat': "Hujjat yoki Rasm (JPG, PNG, PDF, DOC, DOCX, ko'p fayl yuklash mumkin)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['hujjat'].required = False

    def clean_hujjat(self):
        """Hujjat fayllarini validatsiya qilish."""
        hujjatlar = self.cleaned_data.get('hujjat')
        if hujjatlar:
            if isinstance(hujjatlar, list):
                for file in hujjatlar:
                    if file.size > 10 * 1024 * 1024:
                        raise ValidationError("Har bir fayl hajmi 10MB dan kichik bo'lishi kerak!")
                    ext = file.name.split('.')[-1].lower()
                    if ext not in ['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']:
                        raise ValidationError("Faqat JPG, PNG, PDF, DOC yoki DOCX fayllari qo'llab-quvvatlanadi!")
            else:
                if hujjatlar.size > 10 * 1024 * 1024:
                    raise ValidationError("Fayl hajmi 10MB dan kichik bo'lishi kerak!")
                ext = hujjatlar.name.split('.')[-1].lower()
                if ext not in ['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']:
                    raise ValidationError("Faqat JPG, PNG, PDF, DOC yoki DOCX fayllari qo'llab-quvvatlanadi!")
        return hujjatlar