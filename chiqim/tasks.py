from celery import shared_task
from django.utils import timezone
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from .models import Bildirishnoma, SmsLog
import phonenumbers
from phonenumbers import PhoneNumberFormat, NumberParseException
import logging
import json
from decimal import Decimal
from django.db.models import Sum
from django.contrib.auth.decorators import login_required
from requests.exceptions import ConnectionError as RequestsConnectionError

logger = logging.getLogger(__name__)

# Twilio client
twilio_client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

# Sozlamalardan olish
DAILY_SMS_LIMIT = getattr(settings, 'DAILY_SMS_LIMIT', 10)
SMS_TEMPLATE = getattr(
    settings,
    'SMS_TEMPLATE',
    (
        "Hurmatli {customer_name},\n"
        "To'lov eslatmasi:\n"
        "Sana: {payment_date}\n"
        "Oylik to'lov: {amount:,.2f} so'm\n"
        "Status: {status}\n"
        "Qoldiq: {remaining_debt:,.2f} so'm\n"
        "Iltimos, o'z vaqtida to'lov qiling!"
    )
)
NOTIFICATION_START_DAYS = getattr(settings, 'NOTIFICATION_START_DAYS', 5)  # SMS 5 kun oldin boshlanadi

class TwilioError(Exception):
    """Twilio xatolarini aniqlash uchun maxsus sinf"""
    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code

def validate_phone_number(phone_number: str) -> str:
    """Telefon raqamini tekshirish va E.164 formatiga o'tkazish"""
    if not phone_number:
        raise ValueError("Telefon raqami mavjud emas")

    try:
        parsed_number = phonenumbers.parse(phone_number, "UZ" if not phone_number.startswith('+') else None)
        if not phonenumbers.is_valid_number(parsed_number):
            raise ValueError(f"Noto'g'ri telefon raqami: {phone_number}")
        return phonenumbers.format_number(parsed_number, PhoneNumberFormat.E164)
    except NumberParseException as e:
        raise ValueError(f"Telefon raqamini tahlil qilishda xato: {str(e)}")

def check_payment_status(bildirishnoma) -> bool:
    """To'lov holatini tekshirish"""
    chiqim = bildirishnoma.chiqim
    monthly_payment = chiqim.oyiga_tolov
    if monthly_payment <= 0 or chiqim.qoldiq_summa <= 0:
        return True  # Agar oylik to'lov 0 yoki qoldiq 0 bo'lsa, to'langan deb hisoblanadi

    # Joriy oy uchun to'langan summa
    paid_for_month = chiqim.tolovlar.filter(
        sana__year=bildirishnoma.tolov_sana.year,
        sana__month=bildirishnoma.tolov_sana.month
    ).aggregate(total=Sum('summa'))['total'] or Decimal('0')

    # Umumiy to'langan summa va qoldiq hisoblash
    total_paid = sum(t.summa for t in chiqim.tolovlar.all())
    previous_months = chiqim.bildirishnomalar.filter(
        tolov_sana__lt=bildirishnoma.tolov_sana
    ).count()
    previous_months_payment = previous_months * monthly_payment
    remaining_payment = total_paid - previous_months_payment

    is_paid = paid_for_month >= monthly_payment or remaining_payment >= monthly_payment
    logger.debug(
        f"To'lov holati: Bildirishnoma ID {bildirishnoma.id}, "
        f"Paid for month: {paid_for_month}, Oylik to'lov: {monthly_payment}, "
        f"Qoldiq to'lov: {remaining_payment}, is_paid={is_paid}"
    )
    return is_paid

def prepare_sms_message(bildirishnoma, days_left: int) -> str:
    """SMS matnini tayyorlash"""
    chiqim = bildirishnoma.chiqim
    payment_date = bildirishnoma.tolov_sana.strftime('%Y-%m-%d')
    status_message = (
        'Bugun to‘lov kuni!' if days_left == 0 else
        f'Muddati o‘tgan ({-days_left} kun)' if days_left < 0 else
        f'Qolgan kunlar: {days_left}'
    )
    return SMS_TEMPLATE.format(
        customer_name=chiqim.xaridor.ism_familiya,
        payment_date=payment_date,
        amount=float(chiqim.oyiga_tolov),
        status=status_message,
        remaining_debt=float(chiqim.qoldiq_summa)
    )

def send_sms(phone_number: str, message: str) -> str:
    """SMS yuborish"""
    logger.debug(f"Sending SMS to {phone_number} with body: {message}")
    try:
        message_obj = twilio_client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=phone_number
        )
        logger.debug(f"SMS sent successfully. SID: {message_obj.sid}")
        return message_obj.sid
    except TwilioRestException as e:
        logger.error(f"Twilio error: Code={e.code}, Message={str(e)}")
        if e.code in [21610, 30003]:
            raise TwilioError("Twilio balansida mablag‘ yetishmayapti", e.code)
        raise TwilioError(f"SMS yuborishda xato: {str(e)}", e.code)
    except RequestsConnectionError as e:
        logger.error(f"Network error during SMS sending: {str(e)}, Phone: {phone_number}")
        raise


def send_notification(bildirishnoma, force_resend: bool = False, user=None) -> dict:
    """Umumiy SMS yuborish funksiyasi"""
    chiqim = bildirishnoma.chiqim
    xaridor = chiqim.xaridor
    current_date = timezone.now().date()
    days_left = (bildirishnoma.tolov_sana - current_date).days

    result = {'bildirishnoma_id': bildirishnoma.id, 'status': None, 'reason': None}

    # Foydalanuvchi ruxsatini tekshirish (qo'lda yuborish uchun)
    if user and not user.is_superuser and (chiqim.truck.user != user or chiqim.xaridor.user != user):
        logger.warning(f"Unauthorized attempt by user {user} for Bildirishnoma ID {bildirishnoma.id}")
        result.update({'status': 'skipped', 'reason': "Sizga bu bildirishnoma uchun SMS yuborishga ruxsat yo'q!"})
        return result

    # To'lov sanasi 5 kun qolganda yoki o'tgan bo'lsa tekshirish
    if days_left > NOTIFICATION_START_DAYS:
        logger.info(f"Bildirishnoma ID {bildirishnoma.id} uchun SMS yuborish erta (days_left={days_left})")
        result.update({
            'status': 'skipped',
            'reason': f"To'lov sanasiga {days_left} kun qoldi. SMS faqat {NOTIFICATION_START_DAYS} kun qolganda yoki o'tgan bo'lsa yuboriladi!"
        })
        return result

    # Telefon raqamini tekshirish
    try:
        phone_number = validate_phone_number(xaridor.telefon_raqam)
    except ValueError as e:
        logger.warning(f"Telefon raqami xatosi: Xaridor ID {xaridor.id}, Sabab: {str(e)}")
        result.update({'status': 'skipped', 'reason': str(e)})
        return result

    # SMS limitini tekshirish
    today = timezone.now().date()
    sms_count_today = SmsLog.objects.filter(
        xaridor=xaridor,
        sent_at__date=today,
        status='sent'
    ).count()
    if sms_count_today >= DAILY_SMS_LIMIT and not force_resend:
        logger.info(f"Xaridor ID {xaridor.id} uchun SMS limiti ({DAILY_SMS_LIMIT}) oshdi")
        result.update({
            'status': 'skipped',
            'reason': f"Kunlik SMS limiti ({DAILY_SMS_LIMIT}) oshdi"
        })
        return result

    # To'lov holatini tekshirish
    if check_payment_status(bildirishnoma):
        bildirishnoma.status = 'paid'
        bildirishnoma.eslatma = True
        bildirishnoma.save()
        logger.info(f"Bildirishnoma ID {bildirishnoma.id} to'langan, SMS yuborilmaydi.")
        result.update({
            'status': 'skipped',
            'reason': "Bu oy uchun to'lov qilingan yoki qoldiq summa 0"
        })
        return result

    # SMS matnini tayyorlash
    try:
        message_body = prepare_sms_message(bildirishnoma, days_left)
    except Exception as e:
        logger.error(f"SMS matnini tayyorlashda xato: Bildirishnoma ID {bildirishnoma.id}, Xato: {str(e)}")
        result.update({'status': 'skipped', 'reason': f"SMS matnini tayyorlashda xato: {str(e)}"})
        return result

    # SMS yuborish
    try:
        message_sid = send_sms(phone_number, message_body)
        logger.info(
            f"SMS yuborildi: Xaridor: {xaridor.ism_familiya}, Telefon: {phone_number}, Message SID: {message_sid}"
        )
        SmsLog.objects.create(
            bildirishnoma=bildirishnoma,
            xaridor=xaridor,
            message=message_body,
            status='sent',
            sent_at=timezone.now()
        )
        bildirishnoma.eslatma = True
        bildirishnoma.save()
        result.update({'status': 'sent', 'message_sid': message_sid})
    except TwilioError as e:
        logger.error(f"SMS yuborishda xato: Xaridor ID {xaridor.id}, Telefon: {phone_number}, Xato: {str(e)}")
        SmsLog.objects.create(
            bildirishnoma=bildirishnoma,
            xaridor=xaridor,
            message=message_body,
            status='failed',
            sent_at=timezone.now(),
            error_message=str(e)
        )
        result.update({'status': 'failed', 'reason': str(e)})
    except RequestsConnectionError as e:
        logger.error(f"Network error during SMS sending: {str(e)}, Phone: {phone_number}")
        result.update({'status': 'failed', 'reason': f"Network error: {str(e)}"})
        raise  # Re-raise to trigger Celery retry

    return result

@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_daily_payment_reminders(self):
    """Kunlik to'lov eslatmalarini yuborish"""
    try:
        current_date = timezone.now().date()
        logger.info(f"Task boshlandi. Hozirgi sana: {current_date}")

        # Bildirishnomalarni olish: to'lov qilinmaganlar, qoldiq summa > 0, va to'lov sanasi 5 kun qolganda yoki o'tgan
        notifications = Bildirishnoma.objects.filter(
            tolov_sana__lte=current_date + timezone.timedelta(days=NOTIFICATION_START_DAYS),
            status__in=['pending', 'warning', 'urgent', 'overdue'],
            chiqim__qoldiq_summa__gt=0
        ).select_related('chiqim__xaridor', 'chiqim__truck').prefetch_related('chiqim__tolovlar')

        logger.info(f"Topilgan bildirishnomalar soni: {notifications.count()}")

        sent_count = 0
        failed_count = 0
        skipped_count = 0
        results = []

        for bildirishnoma in notifications:
            result = send_notification(bildirishnoma)
            if result['status'] == 'sent':
                sent_count += 1
            elif result['status'] == 'failed':
                failed_count += 1
            else:
                skipped_count += 1
            results.append(result)

        summary = (
            f"Task tugadi. Jami {sent_count} SMS muvaffaqiyatli yuborildi, "
            f"{failed_count} SMS yuborishda xatolik yuz berdi, {skipped_count} SMS o'tkazib yuborildi."
        )
        logger.info(summary)
        logger.debug(f"Tafsilotlar: {json.dumps(results, indent=2, default=str)}")

        return {
            'summary': summary,
            'sent_count': sent_count,
            'failed_count': failed_count,
            'skipped_count': skipped_count,
            'details': results
        }
    except RequestsConnectionError as exc:
        logger.warning(f"Retrying task due to connection error: {str(exc)}")
        raise self.retry(exc=exc)

@login_required
def send_payment_reminder_sms(request, bildirishnoma_id):
    """Qo'lda SMS yuborish funksiyasi"""
    if request.method != 'POST':
        logger.warning(f"Invalid request method: {request.method} for bildirishnoma ID {bildirishnoma_id}")
        return JsonResponse({'success': False, 'error': "Faqat POST so'rovlari qabul qilinadi"}, status=400)

    bildirishnoma = get_object_or_404(Bildirishnoma, id=bildirishnoma_id)
    force_resend = request.POST.get('force_resend', 'false').lower() == 'true'

    result = send_notification(bildirishnoma, force_resend=force_resend, user=request.user)

    if result['status'] == 'sent':
        return JsonResponse({
            'success': True,
            'message': 'SMS muvaffaqiyatli yuborildi!',
            'notification': 'SMS yuborildi!'
        })
    else:
        return JsonResponse({
            'success': False,
            'error': result['reason']
        }, status=400 if result['status'] == 'skipped' else 500)