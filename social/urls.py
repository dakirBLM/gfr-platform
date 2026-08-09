from django.urls import path
from . import views

urlpatterns = [
    path('feed/', views.feed_page, name='social_feed_page'),
    path('post/', views.create_post, name='social_post_create'),
    path('post/<int:pk>/delete/', views.delete_post, name='social_post_delete'),
    path('post/<int:pk>/like/', views.toggle_like, name='social_post_like'),
    path('post/<int:pk>/comment/', views.add_comment, name='social_post_comment'),
    path('follow/<str:username>/', views.toggle_follow, name='social_follow'),
]
