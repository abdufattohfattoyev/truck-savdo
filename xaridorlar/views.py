from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.urls import reverse
from .models import Xaridor, XaridorHujjat
from .forms import XaridorForm
from chiqim.models import Chiqim
from trucks.models import Truck
import os
from datetime import datetime

@login_required
def xaridorlar_list(request):
    query = request.GET.get('q', '')
    sana = request.GET.get('sana', '')

    if request.user.is_superuser:
        xaridorlar = Xaridor.objects.all()
    else:
        xaridorlar = Xaridor.objects.filter(user=request.user)

    if query:
        xaridorlar = xaridorlar.filter(ism_familiya__icontains=query)

    if sana:
        try:
            sana_dt = datetime.strptime(sana, '%Y-%m-%d').date()
            xaridorlar = xaridorlar.filter(sana=sana_dt)
        except ValueError:
            messages.error(request, "Noto'g'ri sana formati. YYYY-MM-DD formatida kiriting.")

    paginator = Paginator(xaridorlar, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'query': query,
        'sana': sana,
        'is_superuser': request.user.is_superuser,
    }
    return render(request, 'xaridorlar/xaridorlar_list.html', context)

@login_required
def xaridor_add(request):
    xaridor_form = XaridorForm(request.POST or None)

    if request.method == 'POST':
        if xaridor_form.is_valid():
            xaridor = xaridor_form.save(commit=False)
            xaridor.user = request.user
            xaridor.save()

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'xaridor_id': xaridor.id,
                    'message': "Xaridor muvaffaqiyatli qo'shildi! Endi hujjatlarni qo'shing."
                })
            messages.success(request, "Xaridor muvaffaqiyatli qo'shildi!")
            return redirect('xaridorlar_list')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                html = render_to_string('xaridorlar/add_xaridor.html', {
                    'xaridor_form': xaridor_form
                }, request=request)
                return JsonResponse({
                    'success': False,
                    'html': html
                })
            messages.error(request, "Iltimos, formani to'g'ri to'ldiring.")

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xaridorlar/add_xaridor.html', {
            'xaridor_form': xaridor_form
        }, request=request)
        return JsonResponse({'html': html})

    return render(request, 'xaridorlar/add_xaridor.html', {
        'xaridor_form': xaridor_form
    })

@login_required
def upload_hujjat(request):
    if request.method == 'POST':
        xaridor_id = request.POST.get('xaridor_id')
        xaridor = get_object_or_404(Xaridor, id=xaridor_id)
        if xaridor.user != request.user and not request.user.is_superuser:
            return JsonResponse({'success': False, 'message': "Bu xaridorga hujjat qo'shishga ruxsatingiz yo'q!"})

        file = request.FILES.get('hujjat')
        if not file:
            return JsonResponse({'success': False, 'message': "Fayl tanlanmagan!"})

        ext = file.name.split('.')[-1].lower()
        if ext not in ['jpg', 'jpeg', 'png', 'pdf', 'doc', 'docx']:
            return JsonResponse({'success': False, 'message': "Faqat JPG, PNG, PDF, DOC, DOCX fayllari qo'llab-quvvatlanadi!"})
        if file.size > 10 * 1024 * 1024:
            return JsonResponse({'success': False, 'message': "Fayl hajmi 10MB dan kichik bo'lishi kerak!"})

        hujjat = XaridorHujjat.objects.create(
            xaridor=xaridor,
            hujjat=file,
            original_file_name=file.name
        )

        hujjatlar = [{
            'id': h.id,
            'original_file_name': h.original_file_name,
            'hujjat_url': h.hujjat.url
        } for h in xaridor.hujjatlar.all()]

        return JsonResponse({
            'success': True,
            'message': "Hujjat muvaffaqiyatli yuklandi!",
            'hujjatlar': hujjatlar
        })

    return JsonResponse({'success': False, 'message': "Faqat POST so'rovlari qabul qilinadi!"})

@login_required
def xaridor_edit(request, id):
    xaridor = get_object_or_404(Xaridor, id=id)
    if xaridor.user != request.user and not request.user.is_superuser:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': "Bu xaridorni tahrirlashga ruxsatingiz yo'q!"})
        messages.error(request, "Bu xaridorni tahrirlashga ruxsatingiz yo'q!")
        return redirect('xaridorlar_list')

    if request.method == 'POST':
        xaridor_form = XaridorForm(request.POST, instance=xaridor)
        if xaridor_form.is_valid():
            xaridor_form.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'message': "Xaridor muvaffaqiyatli tahrirlandi!",
                    'redirect_url': reverse('xaridorlar_list')
                })
            messages.success(request, "Xaridor muvaffaqiyatli tahrirlandi!")
            return redirect('xaridorlar_list')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                html = render_to_string('xaridorlar/edit_xaridor.html', {
                    'xaridor_form': xaridor_form,
                    'xaridor': xaridor
                }, request=request)
                return JsonResponse({
                    'success': False,
                    'message': "Forma to'ldirishda xatolik yuz berdi",
                    'html': html
                })
            messages.error(request, "Xatolik yuz berdi. Iltimos, formani to'g'ri to'ldiring.")
    else:
        xaridor_form = XaridorForm(instance=xaridor)

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xaridorlar/edit_xaridor.html', {
            'xaridor_form': xaridor_form,
            'xaridor': xaridor
        }, request=request)
        return JsonResponse({'html': html})

    return render(request, 'xaridorlar/edit_xaridor.html', {
        'xaridor_form': xaridor_form,
        'xaridor': xaridor
    })

@login_required
def xaridor_delete(request, id):
    xaridor = get_object_or_404(Xaridor, id=id)
    if xaridor.user != request.user and not request.user.is_superuser:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': "Bu xaridorni o'chirishga ruxsatingiz yo'q!"})
        messages.error(request, "Bu xaridorni o'chirishga ruxsatingiz yo'q!")
        return redirect('xaridorlar_list')

    if request.method == 'POST':
        chiqimlar = Chiqim.objects.filter(xaridor=xaridor)
        for chiqim in chiqimlar:
            truck = chiqim.truck
            if truck:
                truck.sotilgan = False
                truck.save()

        for hujjat in xaridor.hujjatlar.all():
            if hujjat.hujjat and os.path.exists(hujjat.hujjat.path):
                os.remove(hujjat.hujjat.path)

        xaridor.delete()

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': "Xaridor muvaffaqiyatli o'chirildi va bog'langan mashinalar holati yangilandi!"
            })
        messages.success(request, "Xaridor muvaffaqiyatli o'chirildi va bog'langan mashinalar holati yangilandi!")
        return redirect('xaridorlar_list')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xaridorlar/delete_xaridor.html', {'xaridor': xaridor}, request=request)
        return JsonResponse({'html': html})

    return render(request, 'xaridorlar/delete_xaridor.html', {'xaridor': xaridor})

@login_required
def view_passport(request, id):
    xaridor = get_object_or_404(Xaridor, id=id)
    if xaridor.user != request.user and not request.user.is_superuser:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': "Bu xaridorning hujjatini ko'rishga ruxsatingiz yo'q!"})
        messages.error(request, "Bu xaridorning hujjatini ko'rishga ruxsatingiz yo'q!")
        return redirect('xaridorlar_list')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xaridorlar/view_passport.html', {'xaridor': xaridor}, request=request)
        return JsonResponse({'html': html})

    return render(request, 'xaridorlar/view_passport.html', {'xaridor': xaridor})

@login_required
def delete_hujjat(request, hujjat_id):
    hujjat = get_object_or_404(XaridorHujjat, id=hujjat_id)
    xaridor = hujjat.xaridor
    if xaridor.user != request.user and not request.user.is_superuser:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': False, 'message': "Bu hujjatni o'chirishga ruxsatingiz yo'q!"})
        messages.error(request, "Bu hujjatni o'chirishga ruxsatingiz yo'q!")
        return redirect('xaridorlar_list')

    if request.method == 'POST':
        if hujjat.hujjat and os.path.exists(hujjat.hujjat.path):
            os.remove(hujjat.hujjat.path)
        hujjat.delete()
        hujjatlar = [{
            'id': h.id,
            'original_file_name': h.original_file_name,
            'hujjat_url': h.hujjat.url
        } for h in xaridor.hujjatlar.all()]
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'message': "Hujjat muvaffaqiyatli o'chirildi!",
                'hujjatlar': hujjatlar
            })
        messages.success(request, "Hujjat muvaffaqiyatli o'chirildi!")
        return redirect('xaridorlar_list')

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xaridorlar/delete_hujjat.html', {'hujjat': hujjat, 'xaridor': xaridor}, request=request)
        return JsonResponse({'html': html})

    return render(request, 'xaridorlar/delete_hujjat.html', {'hujjat': hujjat, 'xaridor': xaridor})