from _decimal import Decimal
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
import calendar
from datetime import timedelta, datetime
from django.conf import settings
from twilio.rest import Client
import logging
from .models import Bildirishnoma, Chiqim, SmsLog
from config import settings
from xaridorlar.models import Xaridor
from .forms import TolovForm, ChiqimForm
from .models import Chiqim, Truck, Bildirishnoma, TolovTuri

logger = logging.getLogger(__name__)

def create_bildirishnoma(chiqim, payment_date, days_before=30):
    Bildirishnoma.objects.update_or_create(
        chiqim=chiqim,
        tolov_sana=payment_date,
        defaults={'eslatma': False, 'eslatish_kunlari': int(days_before)}
    )

def update_notifications(chiqim):
    current_date = timezone.now().date()

    # Agar qoldiq to'langan bo'lsa, bildirishnomalarni o'chirish
    if chiqim.qoldiq_summa <= 0:
        chiqim.bo_lib_tolov_muddat = 0
        chiqim.oyiga_tolov = 0
        chiqim.bildirishnomalar.all().delete()
        return

    monthly_payment = chiqim.oyiga_tolov
    total_paid = chiqim.get_total_paid()
    remaining_payment = total_paid - chiqim.tolangan_summa
    total_months = chiqim.bo_lib_tolov_muddat

    # Birinchi to'lov sanasidan boshlash
    start_date = chiqim.tolov_sana
    target_day = start_date.day  # Har oy o'sha kun bo'ladi

    logger.debug(
        f"Update notifications: total_paid={total_paid}, monthly_payment={monthly_payment}, total_months={total_months}, start_date={start_date}"
    )

    # Mavjud bildirishnomalarni olish
    notifications = chiqim.bildirishnomalar.order_by('tolov_sana')
    existing_dates = set(n.tolov_sana for n in notifications)

    # Har bir oy uchun to'lov sanasini hisoblash
    for month in range(total_months):
        next_month = start_date.month + month
        next_year = start_date.year + (next_month - 1) // 12
        next_month = (next_month - 1) % 12 + 1
        last_day_of_month = calendar.monthrange(next_year, next_month)[1]
        payment_day = min(target_day, last_day_of_month)  # Oy oxiridagi kundan oshmasligi uchun
        payment_date = start_date.replace(year=next_year, month=next_month, day=payment_day)

        # Faqat kelajakdagi to'lovlarni yaratamiz
        if payment_date not in existing_dates and payment_date >= current_date:
            Bildirishnoma.objects.create(
                chiqim=chiqim,
                tolov_sana=payment_date,
                is_archived=False
            )
            logger.debug(f"Yangi bildirishnoma yaratildi: {payment_date}")

        # Bildirishnoma statusini yangilash
        notification = chiqim.bildirishnomalar.filter(tolov_sana=payment_date).first()
        if not notification:
            logger.warning(f"No Bildirishnoma found for payment_date {payment_date}, skipping.")
            continue

        days_left = (notification.tolov_sana - current_date).days
        paid_for_month = sum(
            t.summa for t in chiqim.tolovlar.filter(
                sana__year=payment_date.year,
                sana__month=payment_date.month
            )
        )
        is_paid = paid_for_month >= monthly_payment or remaining_payment >= monthly_payment

        if is_paid:
            notification.status = 'paid'
            notification.eslatma = True
            remaining_payment -= monthly_payment
        else:
            if days_left < 0:
                notification.status = 'overdue'
            elif days_left <= 3:
                notification.status = 'urgent'
            elif days_left <= 7:
                notification.status = 'warning'
            else:
                notification.status = 'pending'
            notification.eslatma = days_left <= notification.eslatish_kunlari
        notification.save()
        logger.debug(
            f"To'lov holati: {notification.tolov_sana} -> {notification.status}, qoldi: {days_left} kun, qoldiq to'lov: {remaining_payment}, paid_for_month={paid_for_month}"
        )

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

    for chiqim in chiqimlar:
        update_notifications(chiqim)
        next_unpaid_notification = chiqim.bildirishnomalar.filter(
            status__in=['pending', 'warning', 'urgent', 'overdue']
        ).order_by('tolov_sana').first()

        if next_unpaid_notification:
            days_left = (next_unpaid_notification.tolov_sana - current_date).days
            chiqim.has_warning = days_left <= notification_days
            chiqim.next_payment_date = next_unpaid_notification.tolov_sana
            chiqim.days_until_payment = days_left
        else:
            chiqim.has_warning = False
            chiqim.next_payment_date = None
            chiqim.days_until_payment = None

    context = {
        'chiqimlar': chiqimlar,
        'trucks': trucks,
        'xaridorlar': xaridorlar,
        'now': timezone.now(),
    }
    return render(request, 'chiqim/chiqim_list.html', context)

@login_required
def chiqim_detail(request, id):
    logger.debug(f'Accessing chiqim_detail view for Chiqim ID {id} by user {request.user}')
    chiqim = get_object_or_404(
        Chiqim.objects.select_related('truck', 'xaridor').prefetch_related('tolovlar'),
        id=id
    )

    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        logger.warning(f'Unauthorized access attempt by user {request.user} for Chiqim ID {id}')
        return JsonResponse(
            {'success': False, 'error': "Sizga bu chiqimni ko'rishga ruxsat yo'q!"},
            status=403
        )

    payment_schedule = []
    total_paid = chiqim.get_total_paid()
    remaining_debt = chiqim.qoldiq_summa
    current_date = timezone.now().date()

    if chiqim.qoldiq_summa <= 0:
        chiqim.bo_lib_tolov_muddat = 0
        chiqim.oyiga_tolov = 0
        chiqim.bildirishnomalar.all().delete()
        chiqim.save()
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
        tolovlar = chiqim.tolovlar.all().order_by('sana')
        subsequent_payments = sum(tolov.summa for tolov in tolovlar)
        remaining_to_distribute = subsequent_payments
        accumulated_paid = chiqim.tolangan_summa
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
        'total_paid': float(total_paid),
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
    logger.debug(f'chiqim_create view called with method: {request.method}')
    if request.method == 'POST':
        form = ChiqimForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            chiqim = form.save()
            if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
                chiqim.delete()
                return JsonResponse({'success': False, 'error': 'Siz faqat o\'zingizning truck va xaridoringiz uchun chiqim qo\'shishingiz mumkin!'}, status=403)
            return JsonResponse({'success': True, 'message': 'Chiqim muvaffaqiyatli qo\'shildi!', 'reload': True})
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            logger.warning(f'Form errors: {errors}')
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = ChiqimForm(user=request.user)
        context = {
            'form': form,
            'trucks': Truck.objects.filter(user=request.user, sotilgan=False) if not request.user.is_superuser else Truck.objects.filter(sotilgan=False),
            'xaridorlar': Xaridor.objects.filter(user=request.user) if not request.user.is_superuser else Xaridor.objects.all(),
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
            old_truck = chiqim.truck
            chiqim = form.save(commit=False)
            chiqim.tolov_sana = chiqim.tolov_sana or timezone.now().date()
            chiqim.save()
            chiqim.bildirishnomalar.all().delete()
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
        return JsonResponse({'success': False, 'error': 'Sizga bu chiqimni o\'chirishga ruxsat yo\'q!'}, status=403)

    if request.method == 'POST':
        old_truck = chiqim.truck
        chiqim.bildirishnomalar.all().delete()
        chiqim.delete()
        old_truck.sotilgan = False
        old_truck.save()
        logger.info(f'Chiqim deleted: ID {id}, truck {old_truck.id} marked unsold')
        return JsonResponse({'success': True, 'message': 'Chiqim muvaffaqiyatli o\'chirildi!'})
    else:
        return render(request, 'chiqim/chiqim_delete_form.html', {'chiqim': chiqim})

@login_required
def add_payment(request, chiqim_id):
    chiqim = get_object_or_404(Chiqim, id=chiqim_id)
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse(
            {'success': False, 'error': "You do not have permission to add a payment for this expense!"},
            status=403
        )

    if request.method == 'POST':
        form = TolovForm(request.POST, initial={'chiqim': chiqim})
        if form.is_valid():
            tolov = form.save(commit=False)
            tolov.chiqim = chiqim
            tolov.xaridor = chiqim.xaridor
            tolov.save()
            chiqim.update_totals()
            chiqim.save()
            update_notifications(chiqim)
            return JsonResponse({
                'success': True,
                'message': "Payment successfully added!",
                'reload': True
            })
        else:
            errors = {field: [str(error) for error in errors] for field, errors in form.errors.items()}
            return JsonResponse({'success': False, 'errors': errors}, status=400)
    else:
        form = TolovForm(initial={'chiqim': chiqim})
        return render(request, 'chiqim/tolov_form.html', {'form': form, 'chiqim': chiqim})

@login_required
def update_payment(request, tolov_id):
    tolov = get_object_or_404(TolovTuri, id=tolov_id)
    chiqim = tolov.chiqim
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        return JsonResponse({'success': False, 'error': "You do not have permission to edit this payment!"}, status=403)

    if request.method == 'POST':
        form = TolovForm(request.POST, instance=tolov, initial={'chiqim': chiqim})
        if form.is_valid():
            tolov = form.save()
            chiqim.update_totals()
            chiqim.save()
            update_notifications(chiqim)
            return JsonResponse({'success': True, 'message': "Payment successfully updated!", 'reload': True})
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
        return JsonResponse({'success': False, 'error': "You do not have permission to delete this payment!"}, status=403)

    if request.method == 'POST':
        tolov.delete()
        chiqim.update_totals()
        chiqim.save()
        update_notifications(chiqim)
        return JsonResponse({'success': True, 'message': "Payment successfully deleted!", 'reload': True})
    else:
        return render(request, 'chiqim/tolov_delete_form.html', {'tolov': tolov, 'chiqim': chiqim})

@login_required
def bildirishnoma_list(request):
    logger.debug('Accessing bildirishnoma_list view')
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
        update_notifications(chiqim)
        unpaid_notifications = chiqim.bildirishnomalar.filter(
            tolov_sana__gte=current_date,
            status__in=['pending', 'warning', 'urgent', 'overdue']
        ).order_by('tolov_sana')

        if unpaid_notifications.exists():
            latest_unpaid = unpaid_notifications.first()
            days_left = (latest_unpaid.tolov_sana - current_date).days
            if days == 0 or days_left <= days:
                latest_unpaid_notifications.append(latest_unpaid.id)

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
        bildirishnoma.summa = bildirishnoma.chiqim.oyiga_tolov
        setattr(bildirishnoma, 'custom_days_left', max(0, (bildirishnoma.tolov_sana - current_date).days))

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

    # Foydalanuvchi ruxsatini tekshirish
    if not request.user.is_superuser and (chiqim.truck.user != request.user or chiqim.xaridor.user != request.user):
        logger.warning(f"Unauthorized attempt to send SMS for notification ID {bildirishnoma_id} by user {request.user}")
        return JsonResponse({'success': False, 'error': "Sizga bu bildirishnoma uchun SMS yuborishga ruxsat yo'q!"}, status=403)

    # Telefon raqamini tekshirish
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

    # SMS limitini tekshirish: Bir xaridorga kuniga faqat 1 SMS
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

    # SMS matnini tayyorlash
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
        f"Iltimos, o'z vaqtida to'lovni amalga oshiring!"
    )

    # Agar to'lov qilingan bo'lsa, SMS yuborishni to'xtatish
    if bildirisnoma.status == 'paid':
        return JsonResponse({
            'success': False,
            'error': "Bu oy uchun to'lov qilingan, SMS yuborish shart emas!"
        }, status=400)

    # SMS yuborish
    try:
        client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
        message = client.messages.create(
            body=message_body,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        logger.info(f"SMS sent to {xaridor.ism_familiya}, Phone: {phone_number}, Message SID: {message.sid}")

        # SMS logini saqlash
        SmsLog.objects.create(
            bildirishnoma=bildirisnoma,
            xaridor=xaridor,
            message=message_body,
            status='sent'
        )

        bildirisnoma.sms_sent = True
        bildirisnoma.save()
        return JsonResponse({
            'success': True,
            'message': 'SMS muvaffaqiyatli yuborildi!',
            'notification': 'SMS yuborildi!'
        })

    except Exception as e:
        logger.error(f"Error sending SMS to {phone_number}: {str(e)}")

        # Xato bo'lsa, logga xato sifatida saqlash
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

    # Xaridorning barcha SMS loglarini olish
    sms_logs = SmsLog.objects.filter(xaridor=xaridor).order_by('-sent_at')

    html = "<div class='sms-history-list'>"
    if sms_logs.exists():
        html += "<ul>"
        for log in sms_logs:
            # Har bir SMS uchun bildirishnoma sanasi va statusini qo‘shish
            bildirishnoma_date = log.bildirishnoma.tolov_sana.strftime('%Y-%m-%d') if log.bildirishnoma else 'Noma’lum'
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

