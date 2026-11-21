import json

from django.db.models import Q, Sum

import base64
import requests

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db import transaction
from django.utils import timezone
from decimal import Decimal

from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Sum
from .models import Event, EmailOTP, Booking

import secrets

from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.utils import timezone

from .models import Event, EmailOTP
from .forms import RegisterForm


# HOME PAGE
def home(request):
    events = Event.objects.filter(is_published=True)
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')

    if q:
        events = events.filter(
            Q(title__icontains=q) | Q(venue__icontains=q) | Q(description__icontains=q)
        )
    if category:
        events = events.filter(category=category)

    return render(request, 'bookings/home.html', {
        'events': events,
        'q': q,
        'selected_category': category,
        'categories': Event.CATEGORY_CHOICES,
    })


def event_detail(request, event_id):
    event = get_object_or_404(Event, id=event_id, is_published=True)
    reserved = Booking.objects.filter(
        event=event, status__in=['pending', 'paid']
    ).aggregate(total=Sum('quantity'))['total'] or 0
    available = max(event.capacity - reserved, 0)
    return render(request, 'bookings/event_detail.html', {
        'event': event,
        'available': available,
    })

# USER REGISTRATION
def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            otp = str(secrets.randbelow(1000000)).zfill(6)

            EmailOTP.objects.update_or_create(
                user=user,
                defaults={
                    'otp_hash': make_password(otp),
                    'expires_at': timezone.now()
                    + timezone.timedelta(minutes=10),
                    'attempts': 0
                }
            )

            try:
                send_mail(
                    'EventEase Email Verification',
                    f'Your verification code is {otp}. '
                    'It expires in 10 minutes.',
                    None,
                    [user.email],
                    fail_silently=False
                )

                request.session['verification_user_id'] = user.id

                return redirect('verify_otp')

            except Exception as e:
                user.delete()
                messages.error(
                    request,
                    'Unable to send verification email. Try again.'
                )
                print("EMAIL ERROR:", e)

    else:
        form = RegisterForm()

    return render(
        request,
        'bookings/register.html',
        {'form': form}
    )


# VERIFY EMAIL OTP
def verify_otp(request):
    user_id = request.session.get('verification_user_id')

    if not user_id:
        messages.error(request, 'Please register first.')
        return redirect('register')

    try:
        otp_record = EmailOTP.objects.get(user_id=user_id)
    except EmailOTP.DoesNotExist:
        messages.error(request, 'Verification session expired.')
        return redirect('register')

    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()

        if timezone.now() > otp_record.expires_at:
            otp_record.delete()
            messages.error(request, 'OTP expired. Please register again.')
            return redirect('register')

        if otp_record.attempts >= 5:
            otp_record.delete()
            messages.error(request, 'Too many attempts. Please register again.')
            return redirect('register')

        if check_password(entered_otp, otp_record.otp_hash):
            user = otp_record.user
            user.is_active = True
            user.save()

            otp_record.delete()
            request.session.pop('verification_user_id', None)

            messages.success(
                request,
                'Email verified! You can now log in.'
            )

            return redirect('login')

        otp_record.attempts += 1
        otp_record.save()

        messages.error(request, 'Incorrect verification code.')

    return render(request, 'bookings/verify_otp.html')


# USER LOGIN
def user_login(request):
    if request.method == 'POST':
        form = AuthenticationForm(
            request,
            data=request.POST
        )

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            messages.success(request, 'Welcome to EventEase!')

            return redirect('dashboard')

        messages.error(request, 'Invalid username or password.')

    else:
        form = AuthenticationForm()

    return render(
        request,
        'bookings/login.html',
        {'form': form}
    )


# USER DASHBOARD
@login_required(login_url='login')
def dashboard(request):
    return render(request, 'bookings/dashboard.html')
# CREATE A TICKET BOOKING
@login_required(login_url='login')
def book_event(request, event_id):

    event = get_object_or_404(
        Event,
        id=event_id,
        is_published=True
    )

    if request.method == 'POST':

        try:
            quantity = int(request.POST.get('quantity', 0))
        except (ValueError, TypeError):
            messages.error(request, 'Enter a valid ticket quantity.')
            return redirect('book_event', event_id=event.id)

        if quantity < 1:
            messages.error(request, 'Choose at least one ticket.')
            return redirect('book_event', event_id=event.id)

        with transaction.atomic():

            # Lock the event while checking available tickets.
            event = Event.objects.select_for_update().get(
                id=event.id
            )

            reserved = Booking.objects.filter(
                event=event,
                status__in=['pending', 'paid']
            ).aggregate(total=Sum('quantity'))['total'] or 0

            available = event.capacity - reserved

            if quantity > available:
                messages.error(
                    request,
                    f'Only {available} tickets are available.'
                )
                return redirect('book_event', event_id=event.id)

            total = event.ticket_price * quantity

            booking = Booking.objects.create(
                user=request.user,
                event=event,
                quantity=quantity,
                total_amount=total,
                status='pending'
            )

        return redirect(
            'booking_confirmation',
            reference=booking.reference
        )

    reserved = Booking.objects.filter(
        event=event,
        status__in=['pending', 'paid']
    ).aggregate(total=Sum('quantity'))['total'] or 0

    available = event.capacity - reserved

    return render(
        request,
        'bookings/book_event.html',
        {
            'event': event,
            'available': available
        }
    )


# BOOKING CONFIRMATION
@login_required(login_url='login')
def booking_confirmation(request, reference):

    booking = get_object_or_404(
        Booking,
        reference=reference,
        user=request.user
    )

    return render(
        request,
        'bookings/booking_confirmation.html',
        {'booking': booking}
    )

def normalize_phone(phone):
    phone = ''.join(filter(str.isdigit, phone))

    if phone.startswith('0') and len(phone) == 10:
        phone = '254' + phone[1:]

    if phone.startswith('254') and len(phone) == 12:
        return phone

    return None


@login_required(login_url='login')
@require_POST
def initiate_mpesa_payment(request, reference):

    booking = get_object_or_404(
        Booking,
        reference=reference,
        user=request.user
    )

    if booking.status != 'pending':
        messages.error(request, 'This booking cannot be paid again.')
        return redirect(
            'booking_confirmation',
            reference=booking.reference
        )

    phone = normalize_phone(request.POST.get('phone', ''))

    if not phone:
        messages.error(request, 'Enter a valid Kenyan phone number.')
        return redirect(
            'booking_confirmation',
            reference=booking.reference
        )

    if not all([
        settings.MPESA_CONSUMER_KEY,
        settings.MPESA_CONSUMER_SECRET,
        settings.MPESA_PASSKEY,
        settings.MPESA_CALLBACK_URL
    ]):
        messages.error(request, 'M-Pesa configuration is incomplete.')
        return redirect(
            'booking_confirmation',
            reference=booking.reference
        )

    amount = int(booking.total_amount)

    if Decimal(amount) != booking.total_amount or amount < 1:
        messages.error(request, 'Invalid payment amount.')
        return redirect(
            'booking_confirmation',
            reference=booking.reference
        )

    timestamp = timezone.localtime().strftime('%Y%m%d%H%M%S')

    password_string = (
        str(settings.MPESA_SHORTCODE)
        + settings.MPESA_PASSKEY
        + timestamp
    )

    password = base64.b64encode(
        password_string.encode()
    ).decode()

    try:
        auth_response = requests.get(
            settings.MPESA_BASE_URL
            + '/oauth/v1/generate?grant_type=client_credentials',
            auth=(
                settings.MPESA_CONSUMER_KEY,
                settings.MPESA_CONSUMER_SECRET
            ),
            timeout=20
        )

        auth_response.raise_for_status()
        access_token = auth_response.json()['access_token']

        payload = {
            "BusinessShortCode": settings.MPESA_SHORTCODE,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": amount,
            "PartyA": phone,
            "PartyB": settings.MPESA_SHORTCODE,
            "PhoneNumber": phone,
            "CallBackURL": settings.MPESA_CALLBACK_URL,
            "AccountReference": "EventEase",
            "TransactionDesc": "Event ticket payment"
        }

        response = requests.post(
            settings.MPESA_BASE_URL
            + '/mpesa/stkpush/v1/processrequest',
            json=payload,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            },
            timeout=30
        )

        response.raise_for_status()
        result = response.json()

        if result.get('ResponseCode') != '0':
            raise ValueError(
                result.get('ResponseDescription', 'STK Push rejected')
            )

        booking.phone_number = phone
        booking.checkout_request_id = result['CheckoutRequestID']
        booking.merchant_request_id = result.get(
            'MerchantRequestID', ''
        )
        booking.save()

        messages.success(
            request,
            'Payment prompt sent. Check your phone.'
        )

    except Exception as error:
        print("MPESA ERROR:", error)
        messages.error(
            request,
            'Could not initiate payment. Check your configuration.'
        )

    return redirect(
        'booking_confirmation',
        reference=booking.reference
    )


@csrf_exempt
@require_POST
def mpesa_callback(request):

    try:
        data = json.loads(request.body)

        callback = data['Body']['stkCallback']

        checkout_id = callback['CheckoutRequestID']
        result_code = callback['ResultCode']

        with transaction.atomic():

            booking = Booking.objects.select_for_update().get(
                checkout_request_id=checkout_id
            )

            if booking.status != 'pending':
                return JsonResponse({
                    'ResultCode': 0,
                    'ResultDesc': 'Callback already processed'
                })

            if result_code == 0:

                items = callback.get(
                    'CallbackMetadata', {}
                ).get('Item', [])

                metadata = {
                    item['Name']: item.get('Value')
                    for item in items
                }

                receipt = metadata.get('MpesaReceiptNumber')
                paid_amount = metadata.get('Amount')
                paid_phone = metadata.get('PhoneNumber')

                if (
                    receipt
                    and paid_amount is not None
                    and Decimal(str(paid_amount)) == booking.total_amount
                    and normalize_phone(str(paid_phone or ''))
                    == booking.phone_number
                ):
                    booking.status = 'paid'
                    booking.mpesa_receipt_number = str(receipt)
                else:
                    print("Payment callback validation failed.")

            else:
                booking.status = 'failed'

            booking.save()

        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Accepted'
        })

    except Exception as error:
        print("CALLBACK ERROR:", error)

        return JsonResponse({
            'ResultCode': 0,
            'ResultDesc': 'Received'
        })
