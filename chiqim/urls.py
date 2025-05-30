from django.urls import path
from . import views


urlpatterns = [
    path('chiqim/', views.chiqim_list, name='chiqim_list'),
    path('add/', views.chiqim_create, name='chiqim_add'),
    path('edit/<int:id>/', views.chiqim_update, name='chiqim_edit'),
    path('delete/<int:id>/', views.chiqim_delete, name='chiqim_delete'),
    path('detail/<int:id>/', views.chiqim_detail, name='chiqim_detail'),
    path('payment/add/<int:chiqim_id>/', views.add_payment, name='add_payment_chiqim'),
    path('payment/edit/<int:tolov_id>/', views.update_payment, name='update_payment'),
    path('payment/delete/<int:tolov_id>/', views.delete_payment, name='delete_payment'),
    path('bildirishnoma_list/', views.bildirishnoma_list, name='bildirishnomalar'),
    path('bildirishnoma/mark/<int:bildirishnoma_id>/', views.mark_notification, name='mark_notification'),
    path('bildirishnoma/send-sms/<int:bildirishnoma_id>/', views.send_payment_reminder_sms, name='send_payment_reminder_sms'),
    path('sms-statistics/', views.sms_statistics, name='sms_statistics'),
    path('bildirishnoma/sms-history/<int:bildirishnoma_id>/', views.sms_history, name='sms_history'),
]