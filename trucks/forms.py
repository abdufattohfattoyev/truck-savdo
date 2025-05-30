from django import forms
from .models import Truck
from django.contrib.auth.models import User


class TruckForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self.is_edit = kwargs.get('instance', None) is not None

        if user and not user.is_superuser:
            self.fields['user'].widget = forms.HiddenInput()
            self.fields['user'].required = False
        else:
            self.fields['user'].queryset = User.objects.all()
            self.fields['user'].widget.attrs.update({
                'class': 'form-control',
                'placeholder': 'Foydalanuvchi tanlang'
            })

        for field in self.fields:
            if field != 'user':
                self.fields[field].widget.attrs.update({
                    'class': 'form-control',
                    'placeholder': f"{self.fields[field].label.lower()} ni kiriting"
                })

            required_fields = ['make', 'model', 'year', 'horsepower', 'price', 'company', 'location']
            if field in required_fields:
                self.fields[field].required = True
                self.fields[field].widget.attrs['required'] = 'required'

        self.fields['year'].widget.attrs.update({
            'min': 1900,
            'max': 2100
        })
        self.fields['horsepower'].widget.attrs.update({
            'min': 0
        })
        self.fields['price'].widget.attrs.update({
            'step': '0.01'
        })
        self.fields['seriya'].widget.attrs.update({
            'min': 0
        })
        self.fields['description'].widget.attrs.update({
            'rows': 3,
            'style': 'resize: none;'
        })
        self.fields['documents'].widget.attrs.update({
            'class': 'form-control file-upload',
        })
        self.fields['image'].widget.attrs.update({
            'class': 'form-control file-upload',
            'accept': 'image/*',
        })

        self.fields['documents'].help_text = 'Majburiy - PDF, DOC, DOCX'
        self.fields['image'].help_text = 'Ixtiyoriy - Tavsiya etilgan o‘lcham: 800x600px'
        self.fields['seriya'].help_text = 'Ixtiyoriy - Mashina seriya raqami'

    class Meta:
        model = Truck
        fields = [
            'user', 'make', 'model', 'year', 'horsepower', 'price', 'company',
            'location', 'documents', 'description', 'image', 'seriya'
        ]
        labels = {
            'user': 'Foydalanuvchi',
            'make': 'Brend',
            'model': 'Model',
            'year': 'Ishlab chiqarilgan yil',
            'horsepower': 'Dvigatel kuchi (HP)',
            'price': 'Narx ($)',
            'company': 'Kompaniya nomi',
            'location': 'Hozirgi joylashuvi',
            'documents': 'Mashina hujjatlari',
            'image': 'Mashina rasmi',
            'description': 'Qo\'shimcha izohlar',
            'seriya': 'Seriya raqami'
        }
        help_texts = {
            'year': '1900-2100 oralig‘ida',
            'horsepower': 'Minimal 0 HP',
            'price': 'AQSh dollarida',
            'company': 'Kompaniya nomi',
            'location': 'Mashinaning hozirgi joylashuvi',
            'seriya': 'Mashina seriya raqami (ixtiyoriy)'
        }

    def clean(self):
        cleaned_data = super().clean()
        year = cleaned_data.get('year')
        horsepower = cleaned_data.get('horsepower')
        price = cleaned_data.get('price')
        make = cleaned_data.get('make')
        model = cleaned_data.get('model')
        company = cleaned_data.get('company')
        location = cleaned_data.get('location')
        seriya = cleaned_data.get('seriya')

        if year and (year < 1900 or year > 2100):
            self.add_error('year', 'Yil 1900 va 2100 oralig‘ida bo‘lishi kerak.')
        if horsepower is not None and horsepower < 0:
            self.add_error('horsepower', 'Dvigatel kuchi salbiy bo‘lmasligi kerak.')
        if price is not None and price < 0:
            self.add_error('price', 'Narx salbiy bo‘lmasligi kerak.')
        if make and len(make.strip()) < 2:
            self.add_error('make', 'Brend nomi kamida 2 belgidan iborat bo‘lishi kerak.')
        if model and len(model.strip()) < 2:
            self.add_error('model', 'Model nomi kamida 2 belgidan iborat bo‘lishi kerak.')
        if company and len(company.strip()) < 2:
            self.add_error('company', 'Kompaniya nomi kamida 2 belgidan iborat bo‘lishi kerak.')
        if location and len(location.strip()) < 2:
            self.add_error('location', 'Joylashuv kamida 2 belgidan iborat bo‘lishi kerak.')
        if seriya is not None and seriya < 0:
            self.add_error('seriya', 'Seriya raqami salbiy bo‘lmasligi kerak.')

        return cleaned_data