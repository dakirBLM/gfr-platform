import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.cache import cache
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from django.views.generic import TemplateView

from accounts.forms import (
    AvatarForm, EducationForm, ProfileForm, PublicationForm,
)
from accounts.models import Education, Publication


logger = logging.getLogger(__name__)

MAX_SANDY_CHAT_MESSAGE = 1500
MAX_SANDY_CHAT_HISTORY = 12


def _gemini_generate(system_prompt: str, history: list, user_message: str) -> str:
    """Call Gemini generateContent and return the assistant text."""
    api_key = settings.GEMINI_API_KEY
    model = getattr(settings, 'GEMINI_MODEL', 'gemini-2.0-flash') or 'gemini-2.0-flash'
    if not api_key:
        raise RuntimeError('GEMINI_API_KEY is not configured.')

    contents = []
    for turn in history[-MAX_SANDY_CHAT_HISTORY:]:
        role = turn.get('role')
        text = (turn.get('text') or '').strip()
        if role not in ('user', 'model') or not text:
            continue
        contents.append({'role': role, 'parts': [{'text': text[:MAX_SANDY_CHAT_MESSAGE]}]})
    contents.append({'role': 'user', 'parts': [{'text': user_message}]})

    endpoint = (
        f'https://generativelanguage.googleapis.com/v1beta/models/'
        f'{model}:generateContent?key={api_key}'
    )
    body = json.dumps({
        'systemInstruction': {'parts': [{'text': system_prompt}]},
        'contents': contents,
        'generationConfig': {
            'temperature': 0.6,
            'maxOutputTokens': 512,
        },
    }).encode('utf-8')
    request = Request(
        endpoint,
        data=body,
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'GFR-Sandy/1.0',
        },
        method='POST',
    )
    with urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode('utf-8'))

    candidates = payload.get('candidates') or []
    if not candidates:
        raise ValueError('Gemini returned no candidates.')
    parts = ((candidates[0].get('content') or {}).get('parts')) or []
    text = ''.join(part.get('text', '') for part in parts).strip()
    if not text:
        raise ValueError('Gemini returned an empty reply.')
    return text


@login_required
@require_POST
def sandy_chat(request):
    """Reply to a Sandy chat turn via Gemini, with GFR + role context."""
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid chat payload.'}, status=400)

    message = (payload.get('message') or '').strip()
    if not message:
        return JsonResponse({'error': 'Please type a message for Sandy.'}, status=400)
    if len(message) > MAX_SANDY_CHAT_MESSAGE:
        return JsonResponse(
            {'error': f'Messages must be under {MAX_SANDY_CHAT_MESSAGE} characters.'},
            status=400,
        )

    if not settings.GEMINI_API_KEY:
        logger.error('GEMINI_API_KEY is not configured.')
        return JsonResponse(
            {'error': 'Sandy chat is temporarily unavailable.'},
            status=503,
        )

    throttle_key = f'sandy-chat:{request.user.pk}'
    if not cache.add(throttle_key, True, timeout=3):
        return JsonResponse(
            {'error': 'Please wait a moment before sending another message.'},
            status=429,
        )

    history = payload.get('history') or []
    if not isinstance(history, list):
        history = []

    from dashboard.sandy_context import build_system_prompt

    try:
        reply = _gemini_generate(build_system_prompt(request.user), history, message)
    except HTTPError as error:
        logger.warning('Gemini rejected Sandy chat with status %s.', error.code)
        return JsonResponse(
            {'error': 'Sandy could not reply right now. Please try again.'},
            status=502,
        )
    except (URLError, TimeoutError, ValueError, RuntimeError) as error:
        logger.warning('Sandy chat failed: %s', error)
        return JsonResponse(
            {'error': 'Sandy could not reply right now. Please try again.'},
            status=502,
        )

    return JsonResponse({'reply': reply})


@login_required
@require_POST
def submit_sandy_feedback(request):
    """Validate feedback and forward it to Make without exposing its webhook."""
    try:
        rating = int(request.POST.get('rating', ''))
    except (TypeError, ValueError):
        rating = 0
    if rating not in range(1, 6):
        return JsonResponse({'error': 'Please choose a rating from 1 to 5.'}, status=400)

    bugs = request.POST.get('bugs', '').strip()[:2000]
    features = request.POST.get('features', '').strip()[:2000]
    webhook_url = settings.SANDY_FEEDBACK_WEBHOOK_URL
    if not webhook_url or urlsplit(webhook_url).scheme != 'https':
        logger.error('SANDY_FEEDBACK_WEBHOOK_URL is not configured.')
        return JsonResponse({'error': 'Feedback is temporarily unavailable.'}, status=503)

    throttle_key = f'sandy-feedback:{request.user.pk}'
    if not cache.add(throttle_key, True, timeout=30):
        return JsonResponse(
            {'error': 'Please wait a moment before sending another review.'},
            status=429,
        )

    payload = json.dumps({
        'source': 'Sandy feedback widget',
        'rating': rating,
        'bugs': bugs,
        'requested_features': features,
        'user': {
            'username': request.user.username,
            'name': request.user.display_name,
        },
    }).encode('utf-8')
    webhook_request = Request(
        webhook_url,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'GFR-Sandy/1.0',
        },
        method='POST',
    )
    try:
        with urlopen(webhook_request, timeout=5) as response:
            if not 200 <= response.status < 300:
                logger.warning('Make rejected Sandy feedback with status %s.', response.status)
                return JsonResponse(
                    {'error': 'We could not send your review. Please try again.'},
                    status=502,
                )
    except HTTPError as error:
        logger.warning('Make rejected Sandy feedback with status %s.', error.code)
        return JsonResponse(
            {'error': 'We could not send your review. Please try again.'},
            status=502,
        )
    except (URLError, TimeoutError, ValueError):
        logger.warning('Could not connect to Make for Sandy feedback.')
        return JsonResponse(
            {'error': 'We could not send your review. Please try again.'},
            status=502,
        )

    return JsonResponse({'message': 'Thank you for your review!'})


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
