from django.urls import path
from . import views

urlpatterns = [
    path('', views.inbox, name='message_inbox'),
    path('new/', views.new_conversation, name='message_new'),
    path('<int:pk>/', views.thread, name='message_thread'),
]
