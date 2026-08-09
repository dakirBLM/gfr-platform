from django.urls import path
from . import views

urlpatterns = [
    path('', views.ConferenceListView.as_view(), name='conference_list'),
    path('<slug:slug>/', views.conference_detail, name='conference_detail'),
    path('<slug:slug>/register/', views.register, name='conference_register'),
    path('<slug:slug>/unregister/', views.unregister, name='conference_unregister'),
    path('<slug:slug>/abstract/', views.submit_abstract, name='conference_submit_abstract'),
]
