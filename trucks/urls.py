from django.urls import path
from trucks import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('users/', views.user_list, name='user_list'),
    path('users/add/', views.add_user, name='add_user'),
    path('users/edit/<int:user_id>/', views.edit_user, name='edit_user'),
    path('users/delete/<int:user_id>/', views.delete_user, name='delete_user'),
    path('add-truck/', views.add_truck, name='add_truck'),
    path('truck/edit/<int:truck_id>/', views.edit_truck, name='edit_truck'),
    path('delete-truck/<int:truck_id>/', views.delete_truck, name='delete_truck'),
    path('truck-list/', views.trucks_list, name='truck_list'),
]