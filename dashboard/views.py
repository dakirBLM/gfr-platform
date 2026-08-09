from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from accounts.forms import (
    AvatarForm, EducationForm, ProfileForm, PublicationForm,
)
from accounts.models import Education, Publication


def _dashboard_stats(user):
    """Real counts for the dashboard home stat cards."""
    from journals.models import Manuscript, ManuscriptStatus
    from projects.models import Task, TaskStatus
    from messaging.models import Message
    from conferences.models import Registration

    manuscripts = (
        Manuscript.objects
        .filter(submitter=user)
        .exclude(status=ManuscriptStatus.DRAFT)
        .count()
    )
    projects = user.projects.count()
    open_tasks = (
        Task.objects
        .filter(assigned_to=user)
        .exclude(status=TaskStatus.DONE)
        .count()
    )
    unread = (
        Message.objects
        .filter(conversation__participants=user)
        .exclude(sender=user)
        .exclude(read_by=user)
        .count()
    )
    return [
        {'label': 'Manuscripts', 'value': manuscripts, 'sub': 'submitted',          'tone': 'brand',   'href': reverse('dashboard:manuscript_list')},
        {'label': 'Projects',    'value': projects,    'sub': 'you participate in',  'tone': 'emerald', 'href': reverse('dashboard:project_list')},
        {'label': 'Open tasks',  'value': open_tasks,  'sub': 'assigned to you',     'tone': 'amber',   'href': reverse('dashboard:project_list') + '?tab=mine'},
        {'label': 'Unread msgs', 'value': unread,      'sub': 'waiting for a reply', 'tone': 'violet',  'href': reverse('dashboard:message_inbox')},
    ]


def _my_open_tasks(user):
    from projects.models import Task, TaskStatus
    return (
        Task.objects.filter(assigned_to=user)
        .exclude(status=TaskStatus.DONE)
        .select_related('project')
        .order_by('due_date', '-created_at')
    )


class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/home.html'

    def get_context_data(self, **kwargs):
        from social.views import get_feed_posts, liked_post_ids
        ctx = super().get_context_data(**kwargs)
        ctx['active_section'] = 'home'
        ctx['stats'] = _dashboard_stats(self.request.user)
        posts = list(get_feed_posts(self.request.user, limit=5))
        ctx['feed_posts'] = posts
        ctx['liked_ids'] = liked_post_ids(posts, self.request.user)
        ctx['feed_has_more'] = get_feed_posts(self.request.user, limit=6).count() > 5
        ctx['my_tasks'] = _my_open_tasks(self.request.user)
        ctx['open_task_count'] = ctx['my_tasks'].count()
        ctx['quick_actions'] = [
            {'title': 'Submit a manuscript', 'desc': 'Send your paper to a GFR journal.',  'href': reverse('dashboard:journal_list'),        'icon': 'upload'},
            {'title': 'Start a project',     'desc': 'Form a team and define milestones.', 'href': reverse('dashboard:project_create'),      'icon': 'flag'},
            {'title': 'Find researchers',    'desc': 'Browse the global directory.',        'href': reverse('dashboard:researcher_directory'), 'icon': 'search'},
            {'title': 'Browse journals',     'desc': 'Explore peer-reviewed publications.', 'href': reverse('dashboard:journal_list'),        'icon': 'book'},
        ]
        return ctx


@login_required
def profile_editor(request):
    """Single-page editor: identity + interests, education list, publications list."""
    user = request.user
    ctx = {
        'active_section': 'profile',
        'avatar_form': AvatarForm(instance=user),
        'profile_form': ProfileForm(instance=user),
        'education_form': EducationForm(),
        'publication_form': PublicationForm(),
        'education_entries': user.education.all(),
        'publications': user.publications.all(),
    }
    return render(request, 'dashboard/profile.html', ctx)


@login_required
@require_POST
def save_profile_info(request):
    form = ProfileForm(request.POST, instance=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, 'Profile updated.')
    else:
        # Re-render the editor inline so users see field-level errors instead of a flash.
        ctx = {
            'active_section': 'profile',
            'avatar_form': AvatarForm(instance=request.user),
            'profile_form': form,
            'education_form': EducationForm(),
            'publication_form': PublicationForm(),
            'education_entries': request.user.education.all(),
            'publications': request.user.publications.all(),
        }
        return render(request, 'dashboard/profile.html', ctx)
    return redirect(reverse('dashboard:profile'))


@login_required
@require_POST
def update_avatar(request):
    form = AvatarForm(request.POST, request.FILES, instance=request.user)
    if form.is_valid():
        form.save()
        messages.success(request, 'Profile photo updated.')
    else:
        messages.error(request, form.errors.get('avatar', ['Could not update photo.'])[0])
    return redirect(reverse('dashboard:profile'))


@login_required
@require_POST
def remove_avatar(request):
    user = request.user
    if user.avatar:
        user.avatar.delete(save=False)
        user.avatar = None
        user.save(update_fields=['avatar'])
        messages.success(request, 'Profile photo removed.')
    return redirect(reverse('dashboard:profile'))


@login_required
@require_POST
def add_education(request):
    form = EducationForm(request.POST)
    if form.is_valid():
        edu = form.save(commit=False)
        edu.user = request.user
        edu.save()
        messages.success(request, 'Education added.')
    else:
        messages.error(request, 'Could not add education entry. ' + '; '.join(
            f'{k}: {", ".join(v)}' for k, v in form.errors.items()
        ))
    return redirect(reverse('dashboard:profile'))


@login_required
@require_POST
def delete_education(request, pk: int):
    edu = get_object_or_404(Education, pk=pk, user=request.user)
    edu.delete()
    messages.success(request, 'Education removed.')
    return redirect(reverse('dashboard:profile'))


@login_required
@require_POST
def add_publication(request):
    form = PublicationForm(request.POST)
    if form.is_valid():
        pub = form.save(commit=False)
        pub.user = request.user
        pub.save()
        messages.success(request, 'Publication added.')
    else:
        messages.error(request, 'Could not add publication. ' + '; '.join(
            f'{k}: {", ".join(v)}' for k, v in form.errors.items()
        ))
    return redirect(reverse('dashboard:profile'))


@login_required
@require_POST
def delete_publication(request, pk: int):
    pub = get_object_or_404(Publication, pk=pk, user=request.user)
    pub.delete()
    messages.success(request, 'Publication removed.')
    return redirect(reverse('dashboard:profile'))
