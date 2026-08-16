from django.urls import path
from . import views

urlpatterns = [
    path('', views.ProjectListView.as_view(), name='project_list'),
    path('new/', views.create_project, name='project_create'),

    path('<slug:slug>/canvas/', views.project_canvas, name='project_canvas'),
    path('<slug:slug>/canvas/data/', views.project_canvas_data, name='project_canvas_data'),
    path('<slug:slug>/canvas/nodes/<int:user_pk>/position/', views.update_canvas_position, name='project_canvas_position'),
    path('<slug:slug>/', views.project_detail, name='project_detail'),
    path('<slug:slug>/join/', views.join_project, name='project_join'),
    path('<slug:slug>/applications/<int:application_pk>/<str:decision>/', views.review_application, name='project_review_application'),
    path('<slug:slug>/leave/', views.leave_project, name='project_leave'),
    path('<slug:slug>/edit/', views.edit_project, name='project_edit'),
    path('<slug:slug>/sections/', views.add_section, name='project_add_section'),
    path('<slug:slug>/sections/<int:section_pk>/delete/', views.delete_section, name='project_delete_section'),

    path('<slug:slug>/members/', views.direct_add_member, name='project_direct_add_member'),
    path('<slug:slug>/members/<int:user_pk>/remove/', views.remove_member, name='project_remove_member'),
    path('<slug:slug>/invite/', views.invite_member, name='project_invite_member'),
    path('<slug:slug>/search-invitable-users/', views.search_invitable_users, name='project_search_invitable_users'),
    path('<slug:slug>/invitations/<int:invitation_pk>/cancel/', views.cancel_invitation, name='project_cancel_invitation'),
    path('invitations/<int:invitation_pk>/respond/', views.respond_to_invitation, name='respond_to_invitation'),

    path('<slug:slug>/tasks/', views.add_task, name='project_add_task'),
    path('<slug:slug>/tasks/<int:task_pk>/', views.task_detail, name='project_task_detail'),
    path('<slug:slug>/tasks/<int:task_pk>/toggle/', views.toggle_task, name='project_toggle_task'),
    path('<slug:slug>/tasks/<int:task_pk>/reopen/', views.reopen_task, name='project_reopen_task'),
    path('<slug:slug>/tasks/<int:task_pk>/edit/', views.edit_task, name='project_edit_task'),
    path('<slug:slug>/tasks/<int:task_pk>/delete/', views.delete_task, name='project_delete_task'),
    path('<slug:slug>/tasks/<int:task_pk>/submit/', views.submit_task, name='project_submit_task'),
    path('<slug:slug>/tasks/<int:task_pk>/review/', views.review_task, name='project_review_task'),

    path('<slug:slug>/milestones/', views.add_milestone, name='project_add_milestone'),
    path('<slug:slug>/milestones/<int:ms_pk>/toggle/', views.toggle_milestone, name='project_toggle_milestone'),
]
