from _decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import render_to_string
from django.utils import timezone
import calendar
from datetime import timedelta
from django.conf import settings
from twilio.rest import Client
import logging
from django.core.cache import cache
from .models import Bildirishnoma, Chiqim, SmsLog, BoshlangichTolov, TolovTuri
from xaridorlar.models import Xaridor
from .forms import TolovForm, ChiqimForm, BoshlangichTolovForm
from trucks.models import Truck

logger = logging.getLogger(__name__)

CACHE_TIMEOUT = 21600  # 6 hours

def create_bildirishnoma(chiqim, payment_date, days_before=30):
    Bildirishnoma.objects.update_or_create(
        chiqim=chiqim,
        tolov_sana=payment_date,
        defaults={'eslatma': False, 'eslatish_kunlari': int(days_before)}
    )

def update_notifications(chiqim):
    cache_key = f'notifications_chiqim_{chiqim.id}'
    cache.delete(cache_key)  # Har doim keshni o'chirish
    chiqim = Chiqim.objects.prefetch_related('tolovlar', 'bildirishnomalar').get(id=chiqim.id)

    if chiqim.qoldiq_summa <= 0:
        chiqim.bo_lib_tolov_muddat = 0
        chiqim.oyiga_tolov = 0
        chiqim.bildirishnomalar.all().delete()
        chiqim.save()
        cache.set(cache_key, {'status': 'cleared', 'notifications': []}, CACHE_TIMEOUT)
        return {'status': 'cleared', 'notifications': []}

    monthly_payment = chiqim.oyiga_tolov
    total_monthly_paid = chiqim.get_total_monthly_paid()
    total_months = chiqim.bo_lib_tolov_muddat
    start_date = chiqim.tolov_sana
    target_day = start_date.day

    payment_schedule = []
    existing_notifications = chiqim.bildirishnomalar.all()
    existing_dates = set(n.tolov_sana for n in existing_notifications)

    if total_months > 0 and monthly_payment > 0 and chiqim.qoldiq_summa > 0:
        for month in range(total_months):
            next_month = start_date.month + month
            next_year = start_date.year + (next_month - 1) // 12
            next_month = (next_month - 1) % 12 + 1
            last_day_of_month = calendar.monthrange(next_year, next_month)[1]
            payment_day = min(target_day, last_day_of_month)
            payment_date = start_date.replace(year=next_year, month=next_month, day=payment_day)

            paid_amount = sum(
                t.summa for t in chiqim.tolovlar.filter(
                    sana__year=payment_date.year,
                    sana__month=payment_date.month
                )
            )
            is_paid = paid_amount >= monthly_payment
            days_left = (payment_date - timezone.now().date()).days

            if payment_date not in existing_dates:
                Bildirishnoma.objects.create(
                    chiqim=chiqim,
                    tolov_sana=payment_date,
                    eslatma=False,
                    eslatish_kunlari=30,
                    status='pending' if not is_paid else 'paid'
                )
                logger.debug(f"Yangi bildirishnoma yaratildi: {payment_date}")

            payment_schedule.append({
                'date': payment_date,
                'amount': monthly_payment,
                'paid_amount': paid_amount,
                'is_paid': is_paid,
                'days_left': days_left,
                'days_overdue': abs(days_left) if days_left < 0 else 0
            })

    notifications = chiqim.bildirishnomalar.all()
    for notification in notifications:
        notification.update_status()

    cached_data = {
        'status': 'updated',
        'notifications': [
            {
                'id': n.id,
                'tolov_sana': n.tolov_sana,
                'status': n.status,
                'eslatma': n.eslatma,
                'eslatish_kunlari': n.eslatish_kunlari,
                'days_left': n.days_left,
                'days_overdue': n.days_overdue
            } for n in notifications
        ]
    }
    cache.set(cache_key, cached_data, CACHE_TIMEOUT)
    return cached_data

@login_required
def chiqim_list(request):
    logger.debug('Accessing chiqim_list view')
    if request.user.is_superuser:
        chiqimlar = Chiqim.objects.all().select_related('truck', 'xaridor')
        trucks = Truck.objects.filter(sotilgan=False)
        xaridorlar = Xaridor.objects.all()
    else:
        chiqimlar = Chiqim.objects.filter(
            truck__user=request.user,
            xaridor__user=request.user
        ).select_related('truck', 'xaridor')
        trucks = Truck.objects.filter(user=request.user, sotilgan=False)
        xaridorlar = Xaridor.objects.filter(user=request.user)

    current_date = timezone.now().date()
    notification_days = 30
    tolov_forms = {}

    for chiqim in chiqimlar:
        chiqim.update_totals()
        total_boshlangich_paid = chiqim.get_total_boshlangich_paid()
        total_monthly_paid = chiqim.get_total_monthly_paid()
        remaining_debt = chiqim.qoldiq_summa

        payment_schedule = []
        start_date = chiqim.tolov_sana
        target_day = start_date.day
        monthly_payment = chiqim.oyiga_tolov
        total_months = chiqim.bo_lib_tolov_muddat
        paid_months = int(total_monthly_paid // monthly_payment) if monthly_payment > 0 else 0
        remaining_months = max(0, total_months - paid_months)

        for month in range(paid_months, total_months):
            next_month = start_date.month + month
            next_year = start_date.year + (next_month - 1) // 12
            next_month = (next_month - 1) % 12 + 1
            last_day_of_month = calendar.monthrange(next_year, next_month)[1]
            payment_day = min(target_day, last_day_of_month)
            payment_date = start_date.replace(year=next_year, month=next_month, day=payment_day)

            paid_amount = sum(
                t.summa for t in chiqim.tolovlar.filter(
                    sana__year=payment_date.year,
                    sana__month=payment_date.month
                )
            )
            is_paid = paid_amount >= monthly_payment
            days_left = (payment_date - current_date).days
            carryover = max(0, monthly_payment - paid_amount) if not is_paid else 0
            progress_percentage = ((chiqim.narx - remaining_debt) / chiqim.narx) * 100 if chiqim.narx > 0 else 0
            pending_debt = carryover if not is_paid and days_left >= 0 else 0

            payment_schedule.append({
                'month': payment_date.strftime('%B %Y'),
                'date': payment_date,
                'amount': monthly_payment,
                'paid_amount': paid_amount,
                'is_paid': is_paid,
                'days_left': days_left,
                'carryover': carryover,
                'progress_percentage': progress_percentage,
                'pending_debt': pending_debt,
                'debt_percentage': (remaining_debt / chiqim.narx) * 100 if chiqim.narx > 0 else 0
            })

        chiqim.overdue_notifications = [
            n for n in chiqim.bildirishnomalar.filter(status='overdue').order_by('tolov_sana')
        ]

        next_unpaid_payment = None
        if payment_schedule and remaining_debt > 0:
            next_unpaid_payment = min(
                [p for p in payment_schedule if not p['is_paid']],
                key=lambda x: x['date'],
                default=None
            )

        if next_unpaid_payment:
            days_until_payment = next_unpaid_payment['days_left']
            chiqim.next_payment_date = next_unpaid_payment['date']
            chiqim.days_until_payment = days_until_payment
            chiqim.days_overdue_display = abs(days_until_payment) if days_until_payment < 0 else 0
            chiqim.has_warning = days_until_payment <= notification_days
        else:
            chiqim.has_warning = False
            chiqim.next_payment_date = None
            chiqim.days_until_payment = None
            chiqim.days_overdue_display = 0

        chiqim.boshlangich_qoldiq = chiqim.get_boshlangich_qoldiq()
        tolov_forms[chiqim.id] = TolovForm(initial={'chiqim': chiqim})

    context = {
        'chiqimlar': chiqimlar,
        'trucks': trucks,
        'xaridorlar': xaridorlar,
        'now': timezone.now(),
        'tolov_forms': tolov_forms,
        'today': timezone.now().date(),
    }
    return render(request, 'chiqim/chiqim_list.html', context)

@login_required
def chiqim_detail(request, id):
    logger.debug(f'Accessing chiqim_detail view for Chiqim ID {id} by user {request.user}')
    chiqim = get_object_or_404(
        Chiqim.objects.select_related('truck', 'xaridor').prefetch_related('tolovlar', 'boshlangich_tolovlar', 'bildirishnomalar'),
        id=id
    )

    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        logger.warning(f'Unauthorized access attempt by user {request.user} for Chiqim ID {id}')
        return JsonResponse(
            {'success': False, 'error': "Sizga bu chiqimni ko'rishga ruxsat yo'q!"},
            status=403
        )

    payment_schedule = []
    total_boshlangich_paid = chiqim.get_total_boshlangich_paid()
    total_monthly_paid = chiqim.get_total_monthly_paid()
    remaining_debt = chiqim.qoldiq_summa
    boshlangich_qoldiq = chiqim.get_boshlangich_qoldiq()
    current_date = timezone.now().date()

    if chiqim.qoldiq_summa <= 0:
        chiqim.bo_lib_tolov_muddat = 0
        chiqim.oyiga_tolov = 0
        chiqim.bildirishnomalar.all().delete()
        chiqim.save()
        cache.delete(f'notifications_chiqim_{chiqim.id}')
    elif chiqim.bo_lib_tolov_muddat > 0:
        monthly_payment = chiqim.oyiga_tolov
        start_date = chiqim.tolov_sana or current_date

        if start_date == current_date:
            next_month = start_date.month + 1
            next_year = start_date.year + (next_month - 1) // 12
            next_month = (next_month - 1) % 12 + 1
            last_day_of_month = calendar.monthrange(next_year, next_month)[1]
            payment_day = min(start_date.day, last_day_of_month)
            start_date = start_date.replace(year=next_year, month=next_month, day=payment_day)

        target_day = start_date.day
        remaining_to_distribute = total_monthly_paid
        accumulated_paid = total_boshlangich_paid
        carryover_amount = Decimal('0')

        for month in range(chiqim.bo_lib_tolov_muddat):
            next_month = start_date.month + month
            next_year = start_date.year + (next_month - 1) // 12
            next_month = (next_month - 1) % 12 + 1
            last_day_of_month = calendar.monthrange(next_year, next_month)[1]
            payment_day = min(target_day, last_day_of_month)
            payment_date = start_date.replace(year=next_year, month=next_month, day=payment_day)

            paid_amount_for_month = Decimal('0')
            is_paid = False

            if remaining_to_distribute >= monthly_payment:
                paid_amount_for_month = monthly_payment
                remaining_to_distribute -= monthly_payment
                is_paid = True
                carryover_amount = remaining_to_distribute
            elif remaining_to_distribute > 0:
                paid_amount_for_month = remaining_to_distribute
                remaining_to_distribute = Decimal('0')
                carryover_amount = Decimal('0')
                is_paid = False
            else:
                paid_amount_for_month = Decimal('0')
                carryover_amount = Decimal('0')
                is_paid = False

            accumulated_paid += paid_amount_for_month
            remaining_debt = max(Decimal('0'), chiqim.narx - accumulated_paid)
            progress_percentage = (paid_amount_for_month / monthly_payment * 100) if monthly_payment > 0 else Decimal('0')

            payment_schedule.append({
                'month': f"{next_month:02d}/{next_year}",
                'date': payment_date,
                'amount': float(monthly_payment),
                'paid_amount': float(paid_amount_for_month),
                'is_paid': is_paid,
                'days_left': max(0, (payment_date - current_date).days),
                'carryover': float(carryover_amount),
                'adjusted_payment': float(monthly_payment - paid_amount_for_month) if not is_paid else 0,
                'debt_percentage': float((remaining_debt / chiqim.narx * 100)) if chiqim.narx > 0 else 0,
                'progress_percentage': float(progress_percentage),
                'pending_debt': float(monthly_payment - paid_amount_for_month) if not is_paid else 0,
            })

    context = {
        'chiqim': chiqim,
        'payment_schedule': payment_schedule,
        'total_boshlangich_paid': float(total_boshlangich_paid),
        'total_monthly_paid': float(total_monthly_paid),
        'boshlangich_qoldiq': float(boshlangich_qoldiq),
        'remaining_debt': float(remaining_debt),
        'current_date': current_date,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            html = render_to_string('chiqim/chiqim_detail.html', context, request=request)
            return JsonResponse({'success': True, 'html': html})
        except Exception as e:
            logger.error(f'Error rendering AJAX response for Chiqim ID {id}: {str(e)}')
            return JsonResponse({'success': False, 'error': 'Ichki server xatosi'}, status=500)

    return render(request, 'chiqim/chiqim_detail.html', context)

@login_required
def chiqim_create(request):
    if request.method == 'POST':
        form = ChiqimForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            try:
                with transaction.atomic():
                    chiqim = form.save(commit=True)
                    logger.info(f"New expense created: ID={chiqim.id}, User={request.user.username}")
                    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                        return JsonResponse({
                            'success': True,
                            'message': 'Chiqim muvaffaqiyatli qo\'shildi!',
                            'redirect_url': None
                        })
                    return redirect('chiqim_list')
            except Exception as e:
                logger.error(f"Error saving expense: {str(e)}")
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return JsonResponse({
                        'success': False,
                        'errors': {'__all__': ['Kutilmagan xatolik yuz berdi. Iltimos, qayta urinib ko\'ring.']},
                    }, status=500)
                raise
        else:
            logger.warning(f"Form validation failed: {form.errors.as_json()}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                errors = {field: [error['message'] for error in errors] for field, errors in form.errors.as_data().items()}
                return JsonResponse({
                    'success': False,
                    'errors': errors,
                }, status=400)
    else:
        form = ChiqimForm(user=request.user)

    context = {
        'form': form,
        'today': timezone.now().date(),
    }
    return render(request, 'chiqim/chiqim_form.html', context)

@login_required
def chiqim_update(request, id):
    chiqim = get_object_or_404(Chiqim, id=id)
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': 'Sizga bu chiqimni tahrirlashga ruxsat yo\'q!'}, status=403)

    if request.method == 'POST':
        form = ChiqimForm(request.POST, request.FILES, instance=chiqim, user=request.user)
        if form.is_valid():
            chiqim = form.save(commit=False)
            chiqim.tolov_sana = chiqim.tolov_sana or timezone.now().date()
            chiqim.save()
            chiqim.bildirishnomalar.all().delete()
            cache.delete(f'notifications_chiqim_{chiqim.id}')
            update_notifications(chiqim)
            return JsonResponse({'success': True, 'message': 'Chiqim muvaffaqiyatli yangilandi!', 'reload': True})
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Form errors: {errors}')
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = ChiqimForm(instance=chiqim, user=request.user)
        context = {
            'form': form,
            'chiqim': chiqim,
            'trucks': Truck.objects.filter(user=request.user, sotilgan=False) if not request.user.is_superuser else Truck.objects.filter(sotilgan=False),
            'xaridorlar': Xaridor.objects.filter(user=request.user) if not request.user.is_superuser else Xaridor.objects.all(),
        }
        return render(request, 'chiqim/chiqim_form.html', context)

@login_required
def chiqim_delete(request, id):
    chiqim = get_object_or_404(Chiqim, id=id)
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "Sizga bu chiqimni o'chirishga ruxsat yo'q!"}, status=403)

    if request.method in ['POST', 'DELETE']:
        try:
            with transaction.atomic():
                old_truck = chiqim.truck
                chiqim.bildirishnomalar.all().delete()
                cache.delete(f'notifications_chiqim_{chiqim.id}')
                chiqim.delete()
                old_truck.sotilgan = False
                old_truck.save()
                logger.info(f'Chiqim deleted: ID {id}, truck {old_truck.id} marked unsold')
                return JsonResponse({'success': True, 'message': "Chiqim muvaffaqiyatli o'chirildi!", 'reload': True})
        except Exception as e:
            logger.error(f'Error deleting Chiqim ID {id}: {str(e)}')
            return JsonResponse({'success': False, 'error': "Chiqimni o'chirishda xatolik yuz berdi!"}, status=500)
    else:
        return render(request, 'chiqim/chiqim_delete_form.html', {'chiqim': chiqim})

@login_required
def add_boshlangich_payment(request, chiqim_id):
    chiqim = get_object_or_404(Chiqim, id=chiqim_id)
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse(
            {'success': False, 'error': "Sizga bu chiqim uchun boshlang'ich to'lov qo'shishga ruxsat yo'q!"},
            status=403
        )

    if request.method == 'POST':
        form = BoshlangichTolovForm(request.POST, initial={'chiqim': chiqim})
        if form.is_valid():
            tolov = form.save(commit=False)
            tolov.chiqim = chiqim
            tolov.xaridor = chiqim.xaridor
            tolov.sana = form.cleaned_data['sana'] or timezone.now().date()
            tolov.save()
            chiqim.update_totals()
            chiqim.save()
            cache.delete(f'notifications_chiqim_{chiqim.id}')
            update_notifications(chiqim)
            return JsonResponse({
                'success': True,
                'message': "Boshlang'ich to'lov muvaffaqiyatli qo'shildi!",
                'reload': True,
                'boshlangich_qoldiq': float(chiqim.get_boshlangich_qoldiq()),
                'tolov_summa': float(tolov.summa)
            })
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Initial payment form errors: {errors}')
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = BoshlangichTolovForm(initial={'chiqim': chiqim})
        context = {
            'form': form,
            'chiqim': chiqim,
            'today': timezone.now().date(),
        }
        return render(request, 'chiqim/boshlangich_tolov_form.html', context)

@login_required
def update_boshlangich_payment(request, tolov_id):
    tolov = get_object_or_404(BoshlangichTolov, id=tolov_id)
    chiqim = tolov.chiqim
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "Sizga bu boshlang'ich to'lovni tahrirlashga ruxsat yo'q!"}, status=403)

    if request.method == 'POST':
        form = BoshlangichTolovForm(request.POST, instance=tolov, initial={'chiqim': chiqim})
        if form.is_valid():
            tolov = form.save()
            chiqim.update_totals()
            chiqim.save()
            cache.delete(f'notifications_chiqim_{chiqim.id}')
            update_notifications(chiqim)
            return JsonResponse({
                'success': True,
                'message': "Boshlang'ich to'lov muvaffaqiyatli yangilandi!",
                'reload': True,
                'boshlangich_qoldiq': float(chiqim.get_boshlangich_qoldiq()),
                'tolov_summa': float(tolov.summa)
            })
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Initial payment update form errors: {errors}')
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = BoshlangichTolovForm(instance=tolov, initial={'chiqim': chiqim})
        return render(request, 'chiqim/boshlangich_tolov_form.html', {'form': form, 'chiqim': chiqim, 'tolov': tolov})

@login_required
def delete_boshlangich_payment(request, tolov_id):
    tolov = get_object_or_404(BoshlangichTolov, id=tolov_id)
    chiqim = tolov.chiqim
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "Sizga bu boshlang'ich to'lovni o'chirishga ruxsat yo'q!"}, status=403)

    if request.method == 'POST':
        tolov.delete()
        chiqim.update_totals()
        chiqim.save()
        cache.delete(f'notifications_chiqim_{chiqim.id}')
        update_notifications(chiqim)
        return JsonResponse({
            'success': True,
            'message': "Boshlang'ich to'lov muvaffaqiyatli o'chirildi!",
            'reload': True,
            'boshlangich_qoldiq': float(chiqim.get_boshlangich_qoldiq())
        })
    else:
        return render(request, 'chiqim/boshlangich_tolov_delete_form.html', {'tolov': tolov, 'chiqim': chiqim})

@login_required
def add_payment(request, chiqim_id):
    chiqim = get_object_or_404(Chiqim, id=chiqim_id)
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse(
            {'success': False, 'error': "Sizga bu chiqim uchun to'lov qo'shishga ruxsat yo'q!"},
            status=403
        )

    if request.method == 'POST':
        form = TolovForm(request.POST, initial={'chiqim': chiqim})
        if form.is_valid():
            tolov = form.save(commit=False)
            tolov.chiqim = chiqim
            tolov.xaridor = chiqim.xaridor
            tolov.sana = form.cleaned_data['sana'] or timezone.now().date()
            tolov.save()
            chiqim.update_totals()
            chiqim.save()
            cache.delete(f'notifications_chiqim_{chiqim.id}')
            update_notifications(chiqim)
            return JsonResponse({
                'success': True,
                'message': "To'lov muvaffaqiyatli qo'shildi!",
                'reload': True
            })
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Payment form errors: {errors}')
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = TolovForm(initial={'chiqim': chiqim})
        context = {
            'form': form,
            'chiqim': chiqim,
            'today': timezone.now().date(),
        }
        return render(request, 'chiqim/tolov_form.html', context)

@login_required
def update_payment(request, tolov_id):
    tolov = get_object_or_404(TolovTuri, id=tolov_id)
    chiqim = tolov.chiqim
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "Sizga bu to'lovni tahrirlashga ruxsat yo'q!"}, status=403)

    if request.method == 'POST':
        form = TolovForm(request.POST, instance=tolov, initial={'chiqim': chiqim})
        if form.is_valid():
            tolov = form.save()
            chiqim.update_totals()
            chiqim.save()
            cache.delete(f'notifications_chiqim_{chiqim.id}')
            update_notifications(chiqim)
            return JsonResponse({
                'success': True,
                'message': "To'lov muvaffaqiyatli yangilandi!",
                'reload': True
            })
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Payment update form errors: {errors}')
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = TolovForm(instance=tolov, initial={'chiqim': chiqim})
        return render(request, 'chiqim/tolov_form.html', {'form': form, 'chiqim': chiqim, 'tolov': tolov})

@login_required
def delete_payment(request, tolov_id):
    tolov = get_object_or_404(TolovTuri, id=tolov_id)
    chiqim = tolov.chiqim
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "Sizga bu to'lovni o'chirishga ruxsat yo'q!"}, status=403)

    if request.method == 'POST':
        tolov.delete()
        chiqim.update_totals()
        chiqim.save()
        cache.delete(f'notifications_chiqim_{chiqim.id}')
        update_notifications(chiqim)
        return JsonResponse({
            'success': True,
            'message': "To'lov muvaffaqiyatli o'chirildi!",
            'reload': True
        })
    else:
        return render(request, 'chiqim/tolov_delete_form.html', {'tolov': tolov, 'chiqim': chiqim})

@login_required
def bildirisnoma_list(request):
    logger.debug('Accessing bildirisnoma_list view')
    current_date = timezone.now().date()

    days_filter = request.GET.get('days', '0')
    sort_by = request.GET.get('sort', 'days_left')
    page = request.GET.get('page', '1')

    try:
        days = int(days_filter)
        if days not in [0, 1, 5, 7, 30]:
            days = 0
    except ValueError:
        days = 0

    if request.user.is_superuser:
        chiqimlar = Chiqim.objects.filter(qoldiq_summa__gt=0).select_related('xaridor', 'truck')
    else:
        chiqimlar = Chiqim.objects.filter(
            truck__user=request.user,
            xaridor__user=request.user,
            qoldiq_summa__gt=0
        ).select_related('xaridor', 'truck')

    latest_unpaid_notifications = []
    for chiqim in chiqimlar:
        chiqim.update_totals()
        cached_data = update_notifications(chiqim)
        unpaid_notifications = [
            n for n in cached_data['notifications']
            if n['status'] in ['pending', 'warning', 'urgent', 'overdue']
        ]
        if unpaid_notifications:
            latest_unpaid = min(unpaid_notifications, key=lambda x: x['tolov_sana'])
            days_left = (latest_unpaid['tolov_sana'] - current_date).days
            if days == 0 or (days_left <= days and days_left >= 0) or (days_left < 0 and days == 0):
                latest_unpaid_notifications.append(latest_unpaid['id'])

    bildirisnomalar = Bildirishnoma.objects.filter(
        id__in=latest_unpaid_notifications
    ).select_related('chiqim__xaridor', 'chiqim__truck')

    notification_count = Bildirishnoma.objects.filter(
        id__in=latest_unpaid_notifications,
        tolov_sana__lte=current_date + timedelta(days=5),
        status__in=['warning', 'urgent', 'overdue']
    ).count()

    if sort_by == 'customer':
        bildirisnomalar = bildirisnomalar.order_by('chiqim__xaridor__ism_familiya', 'tolov_sana')
    else:
        bildirisnomalar = bildirisnomalar.order_by('tolov_sana')

    for bildirishnoma in bildirisnomalar:
        setattr(bildirishnoma, 'custom_days_left', bildirishnoma.days_left)
        setattr(bildirishnoma, 'abs_days_left', bildirishnoma.days_overdue)

    paginator = Paginator(bildirisnomalar, 10)
    try:
        page_obj = paginator.page(page)
    except Exception:
        page_obj = paginator.page(1)

    context = {
        'bildirisnomalar': page_obj,
        'current_filter': days_filter,
        'current_sort': sort_by,
        'page_obj': page_obj,
        'paginator': paginator,
        'notification_count': notification_count,
    }

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        try:
            html = render_to_string('chiqim/bildirishnoma_list_partial.html', context, request=request)
            return JsonResponse({
                'html': html,
                'current_page': page_obj.number,
                'num_pages': paginator.num_pages,
                'notification_count': notification_count,
            })
        except Exception as e:
            logger.error(f'Error rendering AJAX response: {str(e)}')
            return JsonResponse({'success': False, 'error': 'Ichki server xatosi'}, status=500)

    return render(request, 'chiqim/bildirishnomalar.html', context)

@login_required
def mark_notification(request, bildirishnoma_id):
    if request.method == 'POST':
        bildirisnoma = get_object_or_404(Bildirishnoma, id=bildirishnoma_id)
        if not request.user.is_superuser and (bildirisnoma.chiqim.truck.user != request.user or bildirisnoma.chiqim.xaridor.user != request.user):
            logger.warning(f'Unauthorized attempt to mark notification ID {bildirishnoma_id} by user {request.user}')
            return JsonResponse({'success': False, 'error': 'Sizga bu bildirisnomani o\'zgartirishga ruxsat yo\'q!'}, status=403)
        if bildirisnoma.eslatma:
            return JsonResponse({'success': False, 'error': 'Bu bildirisnoma allaqachon belgilangan!'}, status=400)
        bildirisnoma.eslatma = True
        bildirisnoma.save()
        cache.delete(f'notifications_chiqim_{bildirisnoma.chiqim.id}')
        logger.info(f'Notification marked as notified: ID {bildirishnoma_id}')
        return JsonResponse({'success': True, 'message': 'Bildirisnoma muvaffaqiyatli belgilandi!'})
    return JsonResponse({'success': False, 'error': 'Faqat POST so\'rovlari qabul qilinadi'}, status=400)

@login_required
def send_payment_reminder_sms(request, bildirishnoma_id):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': "Faqat POST so'rovlari qabul qilinadi"}, status=400)

    bildirisnoma = get_object_or_404(Bildirishnoma, id=bildirishnoma_id)
    chiqim = bildirisnoma.chiqim
    xaridor = chiqim.xaridor

    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        logger.warning(f"Unauthorized attempt to send SMS for notification ID {bildirishnoma_id} by user {request.user}")
        return JsonResponse({'success': False, 'error': "Sizga bu bildirishnoma uchun SMS yuborishga ruxsat yo'q!"}, status=403)

    phone_number = xaridor.telefon_raqam
    if not phone_number:
        logger.warning(f"No phone number for Xaridor ID {xaridor.id}")
        return JsonResponse({'success': False, 'error': "Xaridorning telefon raqami mavjud emas!"}, status=400)

    phone_number = phone_number.strip()
    if not phone_number.startswith('+'):
        if phone_number.startswith('998') or len(phone_number) == 9:
            phone_number = f"+998{phone_number.lstrip('998')}"
        else:
            logger.warning(f"Invalid phone number format for Xaridor ID {xaridor.id}: {phone_number}")
            return JsonResponse({'success': False, 'error': "Telefon raqami noto'g'ri formatda!"}, status=400)

    today = timezone.now().date()
    sms_count_today = SmsLog.objects.filter(
        xaridor=xaridor,
        sent_at__date=today,
        status='sent'
    ).count()
    if sms_count_today >= 2 and not request.POST.get('force_resend', False):
        return JsonResponse({
            'success': False,
            'error': "Bu xaridorga bugun allaqachon SMS yuborilgan! Qayta yuborish uchun 'force_resend' ni tasdiqlang."
        }, status=400)

    current_date = timezone.now().date()
    days_left = max(0, (bildirisnoma.tolov_sana - current_date).days)
    payment_amount = chiqim.oyiga_tolov
    payment_date = bildirisnoma.tolov_sana.strftime('%Y-%m-%d')
    message_body = (
        f"Hurmatli {xaridor.ism_familiya},\n"
        f"Sizning to'lovingiz haqida eslatma:\n"
        f"To'lov sanasi: {payment_date}\n"
        f"Oylik to'lov: {payment_amount:,.2f} so'm\n"
        f"Qolgan kunlar: {days_left if days_left > 0 else 'Bugun tolov kuni!'}\n"
        f"Qoldiq summa: {chiqim.qoldiq_summa:,.2f} so'm\n"
        f"Boshlang'ich to'lov qoldig'i: {chiqim.get_boshlangich_qoldiq():,.2f} so'm\n"
        f"Iltimos, o'z vaqtida to'lovni amalga oshiring!"
    )

    if bildirisnoma.status == 'paid':
        return JsonResponse({
            'success': False,
            'error': "Bu oy uchun to'lov qilingan, SMS yuborish shart emas!"
        }, status=400)

    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=message_body,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        logger.info(f"SMS sent to {xaridor.ism_familiya}, Phone: {phone_number}, Message SID: {message.sid}")

        SmsLog.objects.create(
            bildirishnoma=bildirisnoma,
            xaridor=xaridor,
            message=message_body,
            status='sent'
        )

        bildirisnoma.sms_sent = True
        bildirisnoma.save()
        cache.delete(f'notifications_chiqim_{chiqim.id}')
        return JsonResponse({
            'success': True,
            'message': 'SMS muvaffaqiyatli yuborildi!',
            'notification': 'SMS yuborildi!'
        })

    except Exception as e:
        logger.error(f"Error sending SMS to {phone_number}: {str(e)}")
        SmsLog.objects.create(
            bildirishnoma=bildirisnoma,
            xaridor=xaridor,
            message=message_body,
            status='failed',
            error_message=str(e)
        )
        return JsonResponse({'success': False, 'error': f"SMS yuborishda xatolik: {str(e)}"}, status=500)

@login_required
def sms_statistics(request):
    total_sms = SmsLog.objects.count()
    successful_sms = SmsLog.objects.filter(status='sent').count()
    failed_sms = SmsLog.objects.filter(status='failed').count()

    return JsonResponse({
        'total': total_sms,
        'successful': successful_sms,
        'failed': failed_sms
    })

@login_required
def sms_history(request, bildirishnoma_id):
    bildirisnoma = get_object_or_404(Bildirishnoma, id=bildirishnoma_id)
    xaridor = bildirisnoma.chiqim.xaridor

    sms_logs = SmsLog.objects.filter(xaridor=xaridor).order_by('-sent_at')

    html = "<div class='sms-history-list'>"
    if sms_logs.exists():
        html += "<ul>"
        for log in sms_logs:
            bildirishnoma_date = log.bildirishnoma.tolov_sana.strftime('%Y-%m-%d') if log.bildirishnoma else 'Noma\'lum'
            html += (
                f"<li><strong>{log.sent_at.strftime('%Y-%m-%d %H:%M:%S')} "
                f"({log.get_status_display()} - To'lov sanasi: {bildirishnoma_date}):</strong><br>{log.message}</li>"
            )
            if log.status == 'failed' and log.error_message:
                html += f"<p style='color: red;'>Xato: {log.error_message}</p>"
        html += "</ul>"
    else:
        html += "<p>Bu xaridor uchun hech qanday SMS yuborilmagan.</p>"
    html += "</div>"

    return JsonResponse({'html': html})