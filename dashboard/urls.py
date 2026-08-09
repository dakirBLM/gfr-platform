from django.urls import include, path

from accounts.views import ResearcherDirectoryView, ResearcherProfileView

from . import views

app_name = 'dashboard'

urlpatterns = [
    path('', views.DashboardHomeView.as_view(), name='home'),

    path('profile/', views.profile_editor, name='profile'),
    path('profile/info/', views.save_profile_info, name='save_profile_info'),

    path('profile/avatar/', views.update_avatar, name='update_avatar'),
    path('profile/avatar/remove/', views.remove_avatar, name='remove_avatar'),

    path('profile/education/', views.add_education, name='add_education'),
    path('profile/education/<int:pk>/delete/', views.delete_education, name='delete_education'),

    path('profile/publications/', views.add_publication, name='add_publication'),
    path('profile/publications/<int:pk>/delete/', views.delete_publication, name='delete_publication'),

    path('researchers/', ResearcherDirectoryView.as_view(), name='researcher_directory'),
    path('researchers/<str:username>/', ResearcherProfileView.as_view(), name='researcher_profile'),

    path('journals/', include('journals.urls')),
    path('projects/', include('projects.urls')),
    path('messages/', include('messaging.urls')),
    path('conferences/', include('conferences.urls')),
    path('social/', include('social.urls')),
    path('notifications/', include('notifications.urls')),
]
