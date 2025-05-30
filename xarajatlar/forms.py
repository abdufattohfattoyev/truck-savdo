from django import forms
from .models import Xarajat

class XarajatForm(forms.ModelForm):
    class Meta:
        model = Xarajat
        fields = ['truck', 'xarajat_turi', 'miqdor', 'izoh', 'sana']
        widgets = {
            'truck': forms.Select(attrs={'class': 'form-control'}),
            'xarajat_turi': forms.Select(attrs={'class': 'form-control'}),
            'miqdor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'izoh': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'sana': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
        labels = {
            'truck': 'Mashina',
            'xarajat_turi': 'Xarajat turi',
            'miqdor': 'Miqdor (Summa)',
            'izoh': 'Izoh',
            'sana': 'Sana',
        }

    def clean(self):
        cleaned_data = super().clean()
        miqdor = cleaned_data.get('miqdor')
        if miqdor is not None and miqdor < 0:
            self.add_error('miqdor', 'Xarajat miqdori salbiy bo‘lmasligi kerak.')
        return cleaned_data