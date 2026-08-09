from django.urls import path
from . import views

urlpatterns = [
    path('<int:pk>/read/', views.mark_read, name='notif_read'),
    path('read-all/', views.mark_all_read, name='notif_read_all'),
]
