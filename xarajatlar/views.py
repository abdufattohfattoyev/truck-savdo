from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.template.loader import render_to_string
from .models import Xarajat
from .forms import XarajatForm
from trucks.models import Truck
import json

@login_required
def xarajatlar_list(request):
    truck_id = request.GET.get('truck_id')
    if request.user.is_superuser:
        if truck_id:
            xarajatlar = Xarajat.objects.filter(truck__id=truck_id, truck__sotilgan=False).order_by('-sana')
            selected_truck = get_object_or_404(Truck, id=truck_id, sotilgan=False)
        else:
            xarajatlar = Xarajat.objects.filter(truck__sotilgan=False).order_by('-sana')
            selected_truck = None
        trucks = Truck.objects.filter(sotilgan=False)
    else:
        if truck_id:
            xarajatlar = Xarajat.objects.filter(truck__id=truck_id, truck__user=request.user, truck__sotilgan=False).order_by('-sana')
            selected_truck = get_object_or_404(Truck, id=truck_id, user=request.user, sotilgan=False)
        else:
            xarajatlar = Xarajat.objects.filter(truck__user=request.user, truck__sotilgan=False).order_by('-sana')
            selected_truck = None
        trucks = Truck.objects.filter(user=request.user, sotilgan=False)

    total_xarajat = xarajatlar.aggregate(Sum('miqdor'))['miqdor__sum'] or 0
    context = {
        'xarajatlar': xarajatlar,
        'trucks': trucks,
        'selected_truck': selected_truck,
        'total_xarajat': total_xarajat,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xarajatlar/xarajatlar_list.html', context, request=request)
        return JsonResponse({'success': True, 'html': html})

    return render(request, 'xarajatlar_list.html', context)

@login_required
def xarajat_add(request):
    if request.method == 'POST':
        form = XarajatForm(request.POST)
        if form.is_valid():
            xarajat = form.save(commit=False)
            if not request.user.is_superuser:
                if xarajat.truck.user != request.user:
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({'success': False, 'message': "Siz faqat o'z mashinalaringiz uchun xarajat qo'sha olasiz!"}, status=403)
                    messages.error(request, "Siz faqat o'z mashinalaringiz uchun xarajat qo'sha olasiz!")
                    return redirect('xarajatlar_list')
            # Tekshirish: Faqat sotilmagan mashinalar uchun xarajat qo'shish
            if xarajat.truck.sotilgan:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': "Sotilgan mashina uchun xarajat qo'shish mumkin emas!"}, status=403)
                messages.error(request, "Sotilgan mashina uchun xarajat qo'shish mumkin emas!")
                return redirect('xarajatlar_list')
            xarajat.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': f"Xarajat muvaffaqiyatli qo'shildi! (ID: {xarajat.id})", 'reload': True})
            messages.success(request, f"Xarajat muvaffaqiyatli qo'shildi! (ID: {xarajat.id})")
            return redirect('xarajatlar_list')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                errors = form.errors.as_json()
                return JsonResponse({'success': False, 'errors': json.loads(errors)}, status=400)
            messages.error(request, "Iltimos, xatolarni tuzating!")
            return render(request, 'xarajat_form.html', {'form': form, 'action': 'add'})
    else:
        form = XarajatForm()
        if not request.user.is_superuser:
            form.fields['truck'].queryset = Truck.objects.filter(user=request.user, sotilgan=False)

    return render(request, 'xarajat_form.html', {'form': form, 'action': 'add'})

@login_required
def xarajat_edit(request, xarajat_id):
    if request.user.is_superuser:
        xarajat = get_object_or_404(Xarajat, id=xarajat_id)
    else:
        xarajat = get_object_or_404(Xarajat, id=xarajat_id, truck__user=request.user)

    if request.method == 'POST':
        form = XarajatForm(request.POST, instance=xarajat)
        if form.is_valid():
            xarajat = form.save(commit=False)
            # Tekshirish: Faqat sotilmagan mashinalar uchun xarajat tahrirlash
            if xarajat.truck.sotilgan:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': "Sotilgan mashina uchun xarajatni tahrirlash mumkin emas!"}, status=403)
                messages.error(request, "Sotilgan mashina uchun xarajatni tahrirlash mumkin emas!")
                return redirect('xarajatlar_list')
            xarajat.save()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': "Xarajat muvaffaqiyatli tahrirlandi!", 'reload': True})
            messages.success(request, "Xarajat muvaffaqiyatli tahrirlandi!")
            return redirect('xarajatlar_list')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                errors = form.errors.as_json()
                return JsonResponse({'success': False, 'errors': json.loads(errors)}, status=400)
            messages.error(request, "Iltimos, xatolarni tuzating!")
            return render(request, 'xarajat_form.html', {'form': form, 'action': 'edit', 'xarajat_id': xarajat_id})
    else:
        form = XarajatForm(instance=xarajat)
        if not request.user.is_superuser:
            form.fields['truck'].queryset = Truck.objects.filter(user=request.user, sotilgan=False)

    return render(request, 'xarajat_form.html', {'form': form, 'action': 'edit', 'xarajat_id': xarajat_id})

@login_required
def xarajat_delete(request, xarajat_id):
    if request.user.is_superuser:
        xarajat = get_object_or_404(Xarajat, id=xarajat_id)
    else:
        xarajat = get_object_or_404(Xarajat, id=xarajat_id, truck__user=request.user)

    if request.method == 'POST':
        if request.POST.get('confirm_delete'):
            # Tekshirish: Faqat sotilmagan mashinalar uchun xarajat o'chirish
            if xarajat.truck.sotilgan:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({'success': False, 'message': "Sotilgan mashina uchun xarajatni o'chirish mumkin emas!"}, status=403)
                messages.error(request, "Sotilgan mashina uchun xarajatni o'chirish mumkin emas!")
                return redirect('xarajatlar_list')
            xarajat.delete()
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': "Xarajat muvaffaqiyatli o'chirildi!", 'closeSidebar': True, 'reload': True})
            messages.success(request, "Xarajat muvaffaqiyatli o'chirildi!")
            return redirect('xarajatlar_list')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                html = render_to_string('xarajat_delete.html', {
                    'xarajat_id': xarajat_id,
                    'xarajat': xarajat
                }, request=request)
                return JsonResponse({'html': html})

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        html = render_to_string('xarajat_delete.html', {
            'xarajat_id': xarajat_id,
            'xarajat': xarajat
        }, request=request)
        return JsonResponse({'html': html})

    return render(request, 'xarajat_delete.html', {
        'xarajat_id': xarajat_id,
        'xarajat': xarajat
    })