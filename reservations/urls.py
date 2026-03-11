from django.urls import path
from . import views

urlpatterns = [
    path('', views.reservation_list, name='reservation_list'),
    path('new/', views.reservation_create, name='reservation_create'),
    path('<int:reservation_id>/', views.reservation_detail, name='reservation_detail'),
    path('<int:reservation_id>/delete/', views.reservation_delete, name='reservation_delete'),
]
