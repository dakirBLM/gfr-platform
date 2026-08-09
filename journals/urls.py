from django.urls import path

from . import views

# IMPORTANT: static paths (manuscripts/, review/, editor/) must come BEFORE
# the slug patterns — otherwise <slug:slug>/ matches those as journal slugs.
urlpatterns = [
    path('', views.JournalListView.as_view(), name='journal_list'),

    path('manuscripts/', views.manuscript_list, name='manuscript_list'),
    path('manuscripts/<int:pk>/', views.manuscript_detail, name='manuscript_detail'),
    path('manuscripts/<int:pk>/revise/', views.submit_revision, name='manuscript_revise'),

    path('review/', views.review_queue, name='review_queue'),
    path('review/<int:pk>/', views.review_detail, name='review_detail'),

    path('editor/', views.editor_queue, name='editor_queue'),
    path('editor/<int:pk>/', views.editor_manuscript, name='editor_manuscript'),

    path('<slug:slug>/', views.JournalDetailView.as_view(), name='journal_detail'),
    path('<slug:slug>/submit/', views.submit_manuscript, name='journal_submit'),
]
