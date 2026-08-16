from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.decorators.http import require_POST
import json

from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.views.generic import ListView

from accounts.models import Role
from messaging.utils import get_or_create_project_chat, sync_member_to_project_chat
from notifications.models import NotifType, notify
from .forms import (
    AddMemberForm, InviteMemberForm, MilestoneForm, ProjectForm,
    ProjectApplicationForm, ProjectSectionForm, TaskForm, TaskReviewForm, TaskSubmitForm,
)
from .models import (
    InvitationStatus, Milestone, MemberRole, Project, ProjectApplication,
    ProjectInvitation, ProjectMembership, ProjectSection, ProjectStatus, ReviewStatus,
    Task, TaskStatus,
)

MAX_TASKS_PER_PROJECT = 20


class ProjectListView(LoginRequiredMixin, ListView):
    model = Project
    template_name = 'projects/list.html'
    context_object_name = 'projects'
    paginate_by = 12

    def get_queryset(self):
        qs = Project.objects.select_related('created_by').prefetch_related('members')
        tab = self.request.GET.get('tab', 'all')
        if tab == 'mine':
            qs = qs.filter(members=self.request.user)
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        status = self.request.GET.get('status', '').strip()
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_section'] = 'projects'
        ctx['tab'] = self.request.GET.get('tab', 'all')
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['status_choices'] = ProjectStatus.choices
        ctx['my_project_ids'] = set(
            self.request.user.projects.values_list('pk', flat=True)
        )
        memberships = ProjectMembership.objects.filter(user=self.request.user)
        ctx['owned_project_ids'] = set(
            memberships.filter(role=MemberRole.OWNER).values_list('project_id', flat=True)
        )
        ctx['managed_project_ids'] = set(
            memberships.filter(role=MemberRole.MANAGER).values_list('project_id', flat=True)
        )
        return ctx


@login_required
def project_detail(request, slug):
    project = get_object_or_404(Project, slug=slug)
    membership = ProjectMembership.objects.filter(project=project, user=request.user).first()
    is_member = membership is not None
    is_manager = is_member and membership.role in (MemberRole.OWNER, MemberRole.MANAGER)
    is_owner = is_member and membership.role == MemberRole.OWNER
    application = ProjectApplication.objects.filter(project=project, applicant=request.user).first()

    tasks = project.tasks.select_related('assigned_to', 'section').all()
    milestones = project.milestones.all()
    team = project.memberships.select_related('user').all()

    # Tasks submitted by members awaiting manager review.
    pending_review = tasks.filter(review_status=ReviewStatus.SUBMITTED) if is_manager else None
    add_member_form = InviteMemberForm(project=project) if is_manager else None

    return render(request, 'projects/detail.html', {
        'project': project,
        'membership': membership,
        'is_member': is_member,
        'is_manager': is_manager,
        'is_owner': is_owner,
        'project_chat': get_or_create_project_chat(project) if is_member else None,
        'application': application,
        'tasks': tasks,
        'milestones': milestones,
        'team': team,
        'pending_review': pending_review,
        'task_form': TaskForm(project=project) if is_manager else None,
        'project_form': ProjectForm(instance=project, exclude_user=request.user, include_initial_members=False) if is_manager else None,
        'section_form': ProjectSectionForm() if is_manager else None,
        'sections': project.sections.prefetch_related('tasks').all(),
        'applications': project.applications.select_related('applicant').filter(status=ProjectApplication.Status.PENDING) if is_manager else None,
        'application_form': ProjectApplicationForm(question=project.application_question) if not is_member and not application else None,
        'milestone_form': MilestoneForm() if is_manager else None,
        'add_member_form': add_member_form,
        'available_members': add_member_form.fields['user'].queryset if add_member_form else None,
        'pending_invitations': (
            project.invitations.filter(status=InvitationStatus.PENDING)
            .select_related('invitee', 'invited_by')
            if is_manager else None
        ),
        'todo_count': tasks.filter(status=TaskStatus.TODO).count(),
        'done_count': tasks.filter(status=TaskStatus.DONE).count(),
        'pending_count': tasks.filter(review_status=ReviewStatus.SUBMITTED).count(),
        'active_section': 'projects',
    })


def _project_canvas_payload(project, membership):
    """Return the collaboration information used by the interactive canvas."""
    memberships = list(project.memberships.select_related('user').all())
    memberships.sort(key=lambda item: (item.user_id != project.created_by_id, item.joined_at))

    # Older demo data can theoretically have a creator without an owner membership.
    # The project still needs its owner represented on the canvas in that case.
    if not any(item.user_id == project.created_by_id for item in memberships):
        memberships.insert(0, type('OwnerMembership', (), {
            'user': project.created_by,
            'user_id': project.created_by_id,
            'role': MemberRole.OWNER,
            'canvas_x': None,
            'canvas_y': None,
        })())

    by_user = {
        item.user_id: {
            'id': item.user_id,
            'name': item.user.display_name,
            'avatar': item.user.avatar_url,
            'profile_url': reverse('dashboard:researcher_profile', args=[item.user.username]),
            'role': 'Project owner' if item.user_id == project.created_by_id else item.get_role_display(),
            'is_owner': item.user_id == project.created_by_id,
            'position': {'x': item.canvas_x, 'y': item.canvas_y},
            # The canvas is a shared workspace: every project member may arrange
            # any node, and the saved arrangement is visible to the whole team.
            'can_drag': True,
            'tasks': [],
            'completed_tasks': [],
            'done_count': 0,
            'in_progress_count': 0,
        }
        for item in memberships
    }
    for task in project.tasks.select_related('assigned_to').exclude(assigned_to__isnull=True):
        node = by_user.get(task.assigned_to_id)
        if not node:
            continue
        if task.status == TaskStatus.DONE:
            node['done_count'] += 1
            node['completed_tasks'].append({
                'title': task.title,
                'url': reverse('dashboard:project_task_detail', args=[project.slug, task.pk]),
            })
        else:
            node['tasks'].append({
                'title': task.title,
                'status': task.get_status_display(),
                'url': reverse('dashboard:project_task_detail', args=[project.slug, task.pk]),
            })
            if task.status == TaskStatus.IN_PROGRESS:
                node['in_progress_count'] += 1

    for node in by_user.values():
        if node['in_progress_count']:
            node['work_status'] = 'In progress'
        elif node['tasks']:
            node['work_status'] = 'Ready to start'
        elif node['done_count']:
            node['work_status'] = 'Finished'
        else:
            node['work_status'] = 'No assigned work'

    return {
        'project': {
            'title': project.title,
            'description': project.description,
            'objectives': project.objectives,
            'status': project.get_status_display(),
            'members': len(by_user),
            'open_tasks': project.tasks.exclude(status=TaskStatus.DONE).count(),
            'completed_tasks': project.tasks.filter(status=TaskStatus.DONE).count(),
        },
        'members': list(by_user.values()),
    }


@login_required
def project_canvas(request, slug):
    project = get_object_or_404(Project.objects.select_related('created_by'), slug=slug)
    membership = ProjectMembership.objects.filter(project=project, user=request.user).first()
    if not membership:
        raise Http404
    return render(request, 'projects/canvas.html', {
        'project': project,
        'canvas_data': _project_canvas_payload(project, membership),
        'active_section': 'projects',
    })


@login_required
def project_canvas_data(request, slug):
    project = get_object_or_404(Project.objects.select_related('created_by'), slug=slug)
    membership = ProjectMembership.objects.filter(project=project, user=request.user).first()
    if not membership:
        raise Http404
    return JsonResponse(_project_canvas_payload(project, membership))


@login_required
@require_POST
def update_canvas_position(request, slug, user_pk):
    project = get_object_or_404(Project, slug=slug)
    membership = ProjectMembership.objects.filter(project=project, user=request.user).first()
    target = get_object_or_404(ProjectMembership, project=project, user_id=user_pk)
    if not membership:
        raise Http404
    try:
        payload = json.loads(request.body)
        x, y = float(payload['x']), float(payload['y'])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return JsonResponse({'error': 'Coordinates must be numbers.'}, status=400)
    target.canvas_x = min(max(x, 8), 92)
    target.canvas_y = min(max(y, 10), 90)
    target.save(update_fields=['canvas_x', 'canvas_y'])
    return JsonResponse({'x': target.canvas_x, 'y': target.canvas_y})


@login_required
def create_project(request):
    if not request.user.can_create_project:
        messages.error(request, 'Your role does not allow creating projects.')
        return redirect('dashboard:project_list')

    from projects.sandy_draft import form_initial_from_draft, pop_draft

    sandy_initial = {}
    sandy_member_ids = set()
    if request.method == 'GET':
        sandy_initial, sandy_member_ids = form_initial_from_draft(pop_draft(request.session))

    form = ProjectForm(
        request.POST or None,
        initial=sandy_initial or None,
        exclude_user=request.user,
    )
    if request.method == 'POST' and form.is_valid():
        project = form.save(commit=False)
        project.created_by = request.user
        project.save()
        ProjectMembership.objects.create(project=project, user=request.user, role=MemberRole.OWNER)
        # Add pre-selected initial members.
        for u in form.cleaned_data.get('initial_members', []):
            ProjectMembership.objects.get_or_create(
                project=project, user=u, defaults={'role': MemberRole.MEMBER},
            )
        # Auto-create group chat and add all members.
        chat = get_or_create_project_chat(project)
        chat.participants.add(request.user)
        for u in form.cleaned_data.get('initial_members', []):
            chat.participants.add(u)
        messages.success(request, f'Project "{project.title}" created.')
        return redirect('dashboard:project_detail', slug=project.slug)

    selected_initial_member_ids = set(sandy_member_ids)
    for value in form['initial_members'].value() or []:
        try:
            selected_initial_member_ids.add(int(value))
        except (TypeError, ValueError):
            pass
    return render(request, 'projects/create.html', {
        'form': form,
        'initial_member_candidates': form.fields['initial_members'].queryset,
        'selected_initial_member_ids': selected_initial_member_ids,
        'prefilled_by_sandy': bool(sandy_initial or sandy_member_ids),
        'active_section': 'projects',
    })


@login_required
def join_project(request, slug):
    project = get_object_or_404(Project, slug=slug)

    # Only Researcher-level and above may join. Students cannot join projects.
    allowed_roles = {
        Role.RESEARCHER, Role.PROFESSOR, Role.REVIEWER,
        Role.EDITOR, Role.PROJECT_MANAGER, Role.ADMIN,
    }
    if request.user.role not in allowed_roles and not request.user.is_superuser:
        messages.error(request, 'Postgraduate students cannot join research projects. Upgrade your membership role to apply.')
        return redirect('dashboard:project_detail', slug=slug)

    if project.status not in (ProjectStatus.OPEN,):
        messages.error(request, 'This project is not open for applications.')
        return redirect('dashboard:project_detail', slug=slug)

    if ProjectMembership.objects.filter(project=project, user=request.user).exists():
        messages.info(request, 'You are already a member.')
        return redirect('dashboard:project_detail', slug=slug)
    application, created = ProjectApplication.objects.get_or_create(
        project=project, applicant=request.user,
        defaults={'message': request.POST.get('message', '').strip(), 'answer': request.POST.get('answer', '').strip()},
    )
    if created:
        project_url = f'/app/projects/{slug}/'
        for m in project.memberships.filter(role__in=[MemberRole.OWNER, MemberRole.MANAGER]).select_related('user'):
            notify(recipient=m.user, actor=request.user, notif_type=NotifType.PROJECT_APPLICATION,
                   message=f'{request.user.display_name} applied to join "{project.title}".', url=project_url)
        messages.success(request, 'Your application was sent to the guarantor for review.')
    elif application.status == ProjectApplication.Status.PENDING:
        messages.info(request, 'Your application is awaiting guarantor review.')
    else:
        messages.info(request, f'Your earlier application was {application.get_status_display().lower()}.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
def review_application(request, slug, application_pk, decision):
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    application = get_object_or_404(ProjectApplication, pk=application_pk, project=project)
    if application.status != ProjectApplication.Status.PENDING:
        messages.info(request, 'This application has already been reviewed.')
        return redirect('dashboard:project_detail', slug=slug)
    if decision not in ('accept', 'decline'):
        raise Http404
    application.status = ProjectApplication.Status.ACCEPTED if decision == 'accept' else ProjectApplication.Status.DECLINED
    application.reviewed_at = timezone.now()
    application.save(update_fields=['status', 'reviewed_at'])
    if decision == 'accept':
        ProjectMembership.objects.get_or_create(project=project, user=application.applicant, defaults={'role': MemberRole.MEMBER})
        sync_member_to_project_chat(project, application.applicant, add=True)
        message = f'Your application to "{project.title}" was accepted.'
        messages.success(request, f'{application.applicant.display_name} was accepted into the project.')
    else:
        message = f'Your application to "{project.title}" was not accepted.'
        messages.info(request, 'Application declined.')
    notify(recipient=application.applicant, actor=request.user, notif_type=NotifType.PROJECT_APPLICATION_DECISION,
           message=message, url=f'/app/projects/{slug}/')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
def edit_project(request, slug):
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    form = ProjectForm(request.POST, instance=project, exclude_user=request.user, include_initial_members=False)
    if form.is_valid():
        form.save()
        messages.success(request, 'Project content updated.')
    else:
        messages.error(request, 'Could not update the project. Check the project details.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
def add_section(request, slug):
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    form = ProjectSectionForm(request.POST)
    if form.is_valid():
        section = form.save(commit=False)
        section.project = project
        section.save()
        messages.success(request, 'Project section added.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
def delete_section(request, slug, section_pk):
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    section = get_object_or_404(ProjectSection, pk=section_pk, project=project)
    section.delete()
    messages.info(request, 'Project section removed; its tasks are now unsectioned.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
def leave_project(request, slug):
    project = get_object_or_404(Project, slug=slug)
    deleted, _ = ProjectMembership.objects.filter(
        project=project, user=request.user,
    ).exclude(role=MemberRole.OWNER).delete()
    if deleted:
        sync_member_to_project_chat(project, request.user, add=False)
    messages.info(request, f'You left "{project.title}".')
    return redirect('dashboard:project_list')


@login_required
def invite_member(request, slug):
    """Manager invites a researcher. Membership only forms once they accept."""
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    form = InviteMemberForm(request.POST, project=project)
    if form.is_valid():
        invitee = form.cleaned_data['user']
        if ProjectMembership.objects.filter(project=project, user=invitee).exists():
            messages.info(request, f'{invitee.display_name} is already a member.')
        elif project.invitations.filter(invitee=invitee, status=InvitationStatus.PENDING).exists():
            messages.info(request, f'An invitation is already pending for {invitee.display_name}.')
        else:
            invitation = ProjectInvitation.objects.create(
                project=project,
                invitee=invitee,
                invited_by=request.user,
                role=form.cleaned_data['role'],
                message=form.cleaned_data.get('message', ''),
            )
            notify(
                recipient=invitee, actor=request.user,
                notif_type=NotifType.PROJECT_INVITATION,
                message=f'{request.user.display_name} invited you to join "{project.title}".',
                url=f'/app/projects/{slug}/',
                project_invitation=invitation,
            )
            messages.success(request, f'Invitation sent to {invitee.display_name}.')
    else:
        messages.error(request, 'Could not send the invitation.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
@require_POST
def respond_to_invitation(request, invitation_pk):
    """The invitee accepts or declines. Membership (chat, canvas bubble,
    task assignability) is only created on accept."""
    invitation = get_object_or_404(
        ProjectInvitation, pk=invitation_pk, invitee=request.user, status=InvitationStatus.PENDING,
    )
    action = request.POST.get('action')
    if action not in ('accept', 'decline'):
        raise Http404

    project = invitation.project
    if action == 'accept':
        _, created = ProjectMembership.objects.get_or_create(
            project=project, user=request.user, defaults={'role': invitation.role},
        )
        if created:
            sync_member_to_project_chat(project, request.user, add=True)
        invitation.status = InvitationStatus.ACCEPTED
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=['status', 'responded_at'])
        project_url = f'/app/projects/{project.slug}/'
        for m in project.memberships.filter(role__in=[MemberRole.OWNER, MemberRole.MANAGER]).select_related('user'):
            notify(recipient=m.user, actor=request.user, notif_type=NotifType.PROJECT_JOINED,
                   message=f'{request.user.display_name} accepted your invitation and joined "{project.title}".',
                   url=project_url)
        messages.success(request, f'You joined "{project.title}".')
    else:
        invitation.status = InvitationStatus.DECLINED
        invitation.responded_at = timezone.now()
        invitation.save(update_fields=['status', 'responded_at'])
        notify(
            recipient=invitation.invited_by, actor=request.user,
            notif_type=NotifType.PROJECT_INVITATION_DECLINED,
            message=f'{request.user.display_name} declined your invitation to "{project.title}".',
            url=f'/app/projects/{project.slug}/',
        )
        messages.info(request, f'You declined the invitation to "{project.title}".')

    next_url = request.POST.get('next', '')
    if next_url.startswith('/'):
        return redirect(next_url)
    return redirect('dashboard:home')


@login_required
@require_POST
def cancel_invitation(request, slug, invitation_pk):
    """Manager withdraws a pending invitation."""
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    invitation = get_object_or_404(
        ProjectInvitation, pk=invitation_pk, project=project, status=InvitationStatus.PENDING,
    )
    invitation.delete()
    messages.info(request, 'Invitation cancelled.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
def direct_add_member(request, slug):
    """Admin-only override that bypasses the invitation flow entirely."""
    project = get_object_or_404(Project, slug=slug)
    if not request.user.can_manage_users:
        raise Http404
    form = AddMemberForm(request.POST, project=project)
    if form.is_valid():
        user = form.cleaned_data['user']
        role = form.cleaned_data['role']
        _, created = ProjectMembership.objects.get_or_create(
            project=project, user=user, defaults={'role': role},
        )
        if created:
            sync_member_to_project_chat(project, user, add=True)
            messages.success(request, f'{user.display_name} added to the project.')
            notify(
                recipient=user, actor=request.user,
                notif_type=NotifType.PROJECT_ADDED,
                message=f'{request.user.display_name} added you to project "{project.title}".',
                url=f'/app/projects/{slug}/',
            )
        else:
            messages.info(request, f'{user.display_name} is already a member.')
    else:
        messages.error(request, 'Could not add member.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
def remove_member(request, slug, user_pk):
    """Manager removes a member (cannot remove the owner)."""
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    from accounts.models import User as UserModel
    target = get_object_or_404(UserModel, pk=user_pk)
    deleted, _ = ProjectMembership.objects.filter(
        project=project, user_id=user_pk,
    ).exclude(role=MemberRole.OWNER).delete()
    if deleted:
        sync_member_to_project_chat(project, target, add=False)
    messages.info(request, 'Member removed from project.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
def add_task(request, slug):
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    if project.tasks.count() >= MAX_TASKS_PER_PROJECT:
        messages.error(request, f'A project may contain at most {MAX_TASKS_PER_PROJECT} tasks. Combine work or remove an obsolete task first.')
        return redirect('dashboard:project_detail', slug=slug)
    form = TaskForm(request.POST, request.FILES, project=project)
    if form.is_valid():
        task = form.save(commit=False)
        task.project = project
        task.save()
        if task.assigned_to:
            notify(recipient=task.assigned_to, actor=request.user, notif_type=NotifType.TASK_ASSIGNED,
                   message=f'You were assigned task "{task.title}" in {project.title}.',
                   url=f'/app/projects/{slug}/tasks/{task.pk}/')
        messages.success(request, 'Task added.')
    else:
        messages.error(request, 'Could not add task.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
def edit_task(request, slug, task_pk):
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    task = get_object_or_404(Task, pk=task_pk, project=project)
    form = TaskForm(request.POST, request.FILES, instance=task, project=project)
    if form.is_valid():
        updated = form.save()
        if updated.assigned_to:
            notify(recipient=updated.assigned_to, actor=request.user, notif_type=NotifType.TASK_ASSIGNED,
                   message=f'Task "{updated.title}" in {project.title} was updated or assigned to you.',
                   url=f'/app/projects/{slug}/tasks/{task.pk}/')
        messages.success(request, 'Task updated.')
    return redirect('dashboard:project_task_detail', slug=slug, task_pk=task_pk)


@login_required
def delete_task(request, slug, task_pk):
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    get_object_or_404(Task, pk=task_pk, project=project).delete()
    messages.info(request, 'Task removed.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
@require_POST
def toggle_task(request, slug, task_pk):
    """One-way completion for managers; completed tasks can only be
    reopened through the explicit reopen action in task_detail."""
    project = get_object_or_404(Project, slug=slug)
    task = get_object_or_404(Task, pk=task_pk, project=project)
    _require_manager(project, request.user)
    if task.status == TaskStatus.DONE:
        messages.warning(request, f'Task "{task.title}" is already completed. Use the Reopen action in the task page to reopen it.')
        return redirect('dashboard:project_detail', slug=slug)
    task.status = TaskStatus.DONE
    task.save(update_fields=['status'])
    return redirect('dashboard:project_detail', slug=slug)


@login_required
@require_POST
def reopen_task(request, slug, task_pk):
    """Explicit, intentional action to take a completed task back to To do."""
    project = get_object_or_404(Project, slug=slug)
    task = get_object_or_404(Task, pk=task_pk, project=project)
    _require_manager(project, request.user)
    if task.status != TaskStatus.DONE:
        messages.info(request, f'Task "{task.title}" is not completed.')
        return redirect('dashboard:project_task_detail', slug=slug, task_pk=task_pk)
    task.status = TaskStatus.TODO
    # A reopened task is no longer "approved": the submission loop restarts.
    if task.review_status == ReviewStatus.APPROVED:
        task.review_status = ReviewStatus.NONE
    task.save(update_fields=['status', 'review_status'])
    messages.warning(request, f'Task "{task.title}" was reopened.')
    return redirect('dashboard:project_task_detail', slug=slug, task_pk=task_pk)


@login_required
def task_detail(request, slug, task_pk):
    project = get_object_or_404(Project, slug=slug)
    task = get_object_or_404(Task, pk=task_pk, project=project)

    membership = ProjectMembership.objects.filter(project=project, user=request.user).first()
    is_assignee = task.assigned_to == request.user
    is_manager = membership is not None and membership.role in (MemberRole.OWNER, MemberRole.MANAGER)

    # Task assignees can always view and submit their own task, even if their
    # membership was later removed. Anyone else who is not a manager is blocked.
    if not is_assignee and not is_manager:
        messages.error(request, 'Only the task assignee and project managers can view this task.')
        return redirect('dashboard:project_detail', slug=slug)

    submit_form = TaskSubmitForm() if is_assignee and task.review_status != ReviewStatus.SUBMITTED else None
    review_form = TaskReviewForm() if is_manager and task.is_submitted else None

    return render(request, 'projects/task_detail.html', {
        'project': project,
        'task': task,
        'is_assignee': is_assignee,
        'is_manager': is_manager,
        'submit_form': submit_form,
        'review_form': review_form,
        'task_form': TaskForm(instance=task, project=project) if is_manager else None,
        'active_section': 'projects',
    })


@login_required
def submit_task(request, slug, task_pk):
    """Task assignee submits their work for manager review."""
    project = get_object_or_404(Project, slug=slug)
    task = get_object_or_404(Task, pk=task_pk, project=project)
    if task.assigned_to != request.user:
        messages.error(request, 'Only the assigned member can submit this task.')
        return redirect('dashboard:project_detail', slug=slug)

    if task.review_status == ReviewStatus.SUBMITTED:
        messages.info(request, 'Task is already awaiting review.')
        return redirect('dashboard:project_task_detail', slug=slug, task_pk=task_pk)

    form = TaskSubmitForm(request.POST, request.FILES)
    if form.is_valid():
        task.submission_note = form.cleaned_data['submission_note']
        task.review_status = ReviewStatus.SUBMITTED
        task.status = TaskStatus.IN_PROGRESS
        task.submitted_at = timezone.now()
        fields = ['submission_note', 'review_status', 'status', 'submitted_at']
        if form.cleaned_data.get('submission_file'):
            task.submission_file = form.cleaned_data['submission_file']
            fields.append('submission_file')
        task.save(update_fields=fields)
        # Notify all project managers.
        task_url = f'/app/projects/{slug}/tasks/{task_pk}/'
        for m in project.memberships.filter(role__in=[MemberRole.OWNER, MemberRole.MANAGER]).select_related('user'):
            notify(
                recipient=m.user, actor=request.user,
                notif_type=NotifType.TASK_SUBMITTED,
                message=f'{request.user.display_name} submitted task "{task.title}" in {project.title}.',
                url=task_url,
            )
        messages.success(request, 'Task submitted for manager review.')
    else:
        messages.error(request, 'Please provide a work summary.')
    return redirect('dashboard:project_task_detail', slug=slug, task_pk=task_pk)


@login_required
def review_task(request, slug, task_pk):
    """Manager approves or rejects a submitted task."""
    project = get_object_or_404(Project, slug=slug)
    task = get_object_or_404(Task, pk=task_pk, project=project)
    _require_manager(project, request.user)

    if not task.is_submitted:
        messages.error(request, 'This task has not been submitted for review.')
        return redirect('dashboard:project_task_detail', slug=slug, task_pk=task_pk)

    form = TaskReviewForm(request.POST)
    if form.is_valid():
        decision = form.cleaned_data['decision']
        task.manager_feedback = form.cleaned_data.get('manager_feedback', '')
        task_url = f'/app/projects/{slug}/tasks/{task_pk}/'
        if decision == 'approved':
            task.review_status = ReviewStatus.APPROVED
            task.status = TaskStatus.DONE
            messages.success(request, f'Task "{task.title}" approved and marked as done.')
            if task.assigned_to:
                notify(
                    recipient=task.assigned_to, actor=request.user,
                    notif_type=NotifType.TASK_APPROVED,
                    message=f'Your task "{task.title}" in {project.title} was approved.',
                    url=task_url,
                )
        else:
            task.review_status = ReviewStatus.REJECTED
            task.status = TaskStatus.IN_PROGRESS
            messages.warning(request, f'Task "{task.title}" sent back for revision.')
            if task.assigned_to:
                notify(
                    recipient=task.assigned_to, actor=request.user,
                    notif_type=NotifType.TASK_REJECTED,
                    message=f'Your task "{task.title}" in {project.title} needs revision.',
                    url=task_url,
                )
        task.save(update_fields=['review_status', 'status', 'manager_feedback'])
    return redirect('dashboard:project_task_detail', slug=slug, task_pk=task_pk)


@login_required
def add_milestone(request, slug):
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    form = MilestoneForm(request.POST)
    if form.is_valid():
        ms = form.save(commit=False)
        ms.project = project
        ms.save()
        messages.success(request, 'Milestone added.')
    return redirect('dashboard:project_detail', slug=slug)


@login_required
def toggle_milestone(request, slug, ms_pk):
    project = get_object_or_404(Project, slug=slug)
    _require_manager(project, request.user)
    ms = get_object_or_404(Milestone, pk=ms_pk, project=project)
    ms.completed = not ms.completed
    ms.completed_at = timezone.now() if ms.completed else None
    ms.save(update_fields=['completed', 'completed_at'])
    return redirect('dashboard:project_detail', slug=slug)


def _require_manager(project, user):
    m = ProjectMembership.objects.filter(project=project, user=user).first()
    if not m or m.role not in (MemberRole.OWNER, MemberRole.MANAGER):
        raise Http404
