from django.contrib import admin
from .models import Xarajat

@admin.register(Xarajat)
class XarajatAdmin(admin.ModelAdmin):
    list_display = ('truck', 'xarajat_turi', 'miqdor', 'sana', 'izoh')
    list_filter = ('xarajat_turi', 'sana', 'truck')
    search_fields = ('truck__make', 'truck__model', 'xarajat_turi', 'izoh')
    date_hierarchy = 'sana'