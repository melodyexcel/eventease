from django.urls import path
from django.contrib.auth.views import LogoutView
from . import views

urlpatterns = [
    path('', views.home, name='home'),

    path('register/', views.register, name='register'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('login/', views.user_login, name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),

    path('dashboard/', views.dashboard, name='dashboard'),
    
    path(
    'pay/<uuid:reference>/',
    views.initiate_mpesa_payment,
    name='initiate_mpesa_payment'
),

path(
    'mpesa/callback/',
    views.mpesa_callback,
    name='mpesa_callback'
),

    path('events/', views.home, name='events'),
    path(
    'book/<int:event_id>/',
    views.book_event,
    name='book_event'
),

path(
    'booking/<uuid:reference>/',
    views.booking_confirmation,
    name='booking_confirmation'
),
]
