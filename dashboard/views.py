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
GEMINI_DEFAULT_MODEL = 'gemini-3.6-flash'
# Gemini 3 counts its own reasoning against maxOutputTokens, so a budget sized
# for the visible answer alone gets spent thinking and returns empty text with
# finishReason MAX_TOKENS. Sandy also asks for minimal thinking: the questions
# are support questions, and deeper reasoning only adds latency and cost.
MAX_SANDY_CHAT_OUTPUT_TOKENS = 2048


class GeminiUnavailable(Exception):
    """Sandy could not get a reply. The message is for logs; user_message is for the browser."""

    DEFAULT_USER_MESSAGE = 'Sandy could not reply right now. Please try again.'

    def __init__(self, log_message, status=502, user_message=None):
        super().__init__(log_message)
        self.status = status
        self.user_message = user_message or self.DEFAULT_USER_MESSAGE


def _gemini_error_detail(error):
    """Gemini names the real problem here: bad key, unknown model, exhausted quota."""
    try:
        body = error.read().decode('utf-8', 'replace')
    except OSError:
        return '<response body unavailable>'
    try:
        return (json.loads(body).get('error') or {}).get('message') or body[:300]
    except (json.JSONDecodeError, AttributeError):
        return body[:300]


def _gemini_generate(system_prompt: str, history: list, user_message: str) -> str:
    """Call Gemini generateContent and return the assistant text."""
    api_key = settings.GEMINI_API_KEY
    model = getattr(settings, 'GEMINI_MODEL', GEMINI_DEFAULT_MODEL) or GEMINI_DEFAULT_MODEL
    if not api_key:
        raise GeminiUnavailable('GEMINI_API_KEY is not configured.')

    contents = []
    for turn in history[-MAX_SANDY_CHAT_HISTORY:]:
        role = turn.get('role')
        text = (turn.get('text') or '').strip()
        if role not in ('user', 'model') or not text:
            continue
        contents.append({'role': role, 'parts': [{'text': text[:MAX_SANDY_CHAT_MESSAGE]}]})
    contents.append({'role': 'user', 'parts': [{'text': user_message}]})

    body = json.dumps({
        'systemInstruction': {'parts': [{'text': system_prompt}]},
        'contents': contents,
        'generationConfig': {
            'thinkingConfig': {'thinkingLevel': 'minimal'},
            'maxOutputTokens': MAX_SANDY_CHAT_OUTPUT_TOKENS,
        },
    }).encode('utf-8')
    # The key travels as a header so it never lands in a URL, log line, or traceback.
    request = Request(
        f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
        data=body,
        headers={
            'Content-Type': 'application/json',
            'User-Agent': 'GFR-Sandy/1.0',
            'x-goog-api-key': api_key,
        },
        method='POST',
    )

    try:
        with urlopen(request, timeout=20) as response:
            raw = response.read().decode('utf-8')
    except HTTPError as error:
        detail = _gemini_error_detail(error)
        if error.code == 429:
            raise GeminiUnavailable(
                f'Gemini quota exhausted for model "{model}": {detail}',
                status=429,
                user_message='Sandy is a bit busy. Please try again in a minute.',
            )
        raise GeminiUnavailable(f'Gemini returned HTTP {error.code} for model "{model}": {detail}')
    except (URLError, TimeoutError) as error:
        raise GeminiUnavailable(f'Could not reach Gemini: {error}')

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise GeminiUnavailable('Gemini returned a response that was not JSON.')

    blocked = (payload.get('promptFeedback') or {}).get('blockReason')
    if blocked:
        raise GeminiUnavailable(f'Gemini blocked the prompt: {blocked}')

    candidates = payload.get('candidates') or []
    if not candidates:
        raise GeminiUnavailable('Gemini returned no candidates.')

    candidate = candidates[0]
    parts = ((candidate.get('content') or {}).get('parts')) or []
    text = ''.join(part.get('text', '') for part in parts).strip()
    if not text:
        raise GeminiUnavailable(
            f'Gemini returned an empty reply (finishReason={candidate.get("finishReason") or "unknown"}).'
        )
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
    except GeminiUnavailable as error:
        logger.warning('Sandy chat failed: %s', error)
        return JsonResponse({'error': error.user_message}, status=error.status)

    return JsonResponse({'reply': reply})


@login_required
@require_POST
def sandy_project_draft(request):
    """Store Sandy's guided project answers, then send the user to create."""
    if not request.user.can_create_project:
        return JsonResponse(
            {'error': 'Your role cannot create projects. Only academic guarantors can.'},
            status=403,
        )

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse({'error': 'Invalid project draft.'}, status=400)

    from projects.sandy_draft import build_draft, draft_is_usable, store_draft

    draft = build_draft(payload.get('answers') or payload, user=request.user)
    if not draft_is_usable(draft):
        return JsonResponse(
            {'error': 'Add at least one project detail before opening the create form.'},
            status=400,
        )

    store_draft(request.session, draft)
    return JsonResponse({
        'redirect': reverse('dashboard:project_create'),
        'fields': sorted(draft.keys()),
    })


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


def _spark(queryset, days=7):
    """
    Daily counts and item titles for the last `days` days, derived from the
    same queryset that feeds a card's number.

    Returns a list of dicts: ``[{ 'date': ..., 'count': N, 'items': [...] }, ...]``
    ordered oldest → newest so the template can pair them with the SVG bars.
    """
    from datetime import timedelta

    from django.db.models import Count
    from django.db.models.functions import TruncDate
    from django.utils import timezone

    today = timezone.localdate()
    start = today - timedelta(days=days - 1)

    rows = (
        queryset.filter(created_at__date__gte=start)
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    items_by_day = {}
    for row in rows:
        items_by_day[row['day']] = row['count']

    title_field = _spark_title_field(queryset)
    if title_field and items_by_day:
        titled = (
            queryset.filter(created_at__date__gte=start)
            .annotate(day=TruncDate('created_at'))
            .filter(day__in=items_by_day)
            .order_by('day')
            .values_list('day', title_field)
        )
        day_titles = {}
        for day, title in titled:
            day_titles.setdefault(day, []).append(title)
    else:
        day_titles = {}

    return [
        {
            'date': start + timedelta(days=i),
            'count': items_by_day.get(start + timedelta(days=i), 0),
            'items': day_titles.get(start + timedelta(days=i), []),
        }
        for i in range(days)
    ]


def _spark_title_field(queryset):
    model = queryset.model
    if hasattr(model, 'title'):
        return 'title'
    if hasattr(model, 'name'):
        return 'name'
    return None


SPARK_STROKE_BY_TONE = {'brand': '#3b6cf2', 'emerald': '#10b981', 'amber': '#f59e0b'}


def _line_chart(spark, stroke, global_max):
    """Build a line-chart dict for the template. The SVG grows taller when
    y_max > 6 so that Y-axis labels never overlap."""
    svg_w = 170
    margin_l, margin_r, margin_b = 18, 4, 14
    chart_w = svg_w - margin_l - margin_r

    y_max = global_max if global_max > 0 else 1
    svg_h = max(80, 20 + y_max * 10)
    chart_h = svg_h - margin_b

    days = len(spark)
    gap = chart_w / (days - 1) if days > 1 else 0

    points = []
    for i, p in enumerate(spark):
        x = margin_l + i * gap
        h = p['count'] / y_max * (chart_h - 4) if y_max else 0
        y = chart_h - h
        items_label = ', '.join(p['items'][:3])
        if p['count'] > 3:
            items_label += f' +{p["count"] - 3} more'
        points.append({
            'x': round(x, 1), 'y': round(y, 1),
            'n': p['count'], 't': items_label,
            'd': p['date'].strftime('%d'),
        })

    path_parts = [f'{pt["x"]},{pt["y"]}' for pt in points]
    path = 'M' + ' L'.join(path_parts)

    y_labels = [{'v': v, 'y': round(chart_h - v / y_max * (chart_h - 4), 1)}
                for v in range(0, y_max + 1)]

    x_labels = [{'label': pt['d'], 'x': pt['x']} for pt in points]

    return {
        'path': path,
        'points': points,
        'y_max': y_max,
        'y_labels': y_labels,
        'x_labels': x_labels,
        'stroke': stroke,
        'svg_w': svg_w,
        'svg_h': svg_h,
    }


def _line_chart_json(chart):
    """JSON-safe version of line chart data for the template data attribute."""
    return [
        {
            'd': pt['d'], 'n': pt['n'], 't': pt['t'],
            'x': pt['x'], 'y': pt['y'],
        }
        for pt in chart['points']
    ]


def _dashboard_stats(user):
    """Real counts for the dashboard home stat cards. Each card's line chart is
    built from the same queryset as its number, so graphs match the numbers."""
    from journals.models import Manuscript, ManuscriptStatus
    from projects.models import Task, TaskStatus

    manuscripts = Manuscript.objects.filter(submitter=user).exclude(status=ManuscriptStatus.DRAFT)
    projects = user.projects.all()
    open_tasks = Task.objects.filter(assigned_to=user).exclude(status=TaskStatus.DONE)

    specs = [
        (manuscripts, {'label': 'Manuscripts', 'sub': 'submitted',          'tone': 'brand',   'href': reverse('dashboard:manuscript_list')}),
        (projects,    {'label': 'Projects',    'sub': 'you participate in', 'tone': 'emerald', 'href': reverse('dashboard:project_list')}),
        (open_tasks,  {'label': 'Open tasks',  'sub': 'assigned to you',    'tone': 'amber',   'href': reverse('dashboard:project_list') + '?tab=mine'}),
    ]
    sparks = [_spark(qs) for qs, _ in specs]
    counts_only = [[p['count'] for p in spark] for spark in sparks]
    global_max = max((max(c) for c in counts_only), default=0)
    stats = []
    for (queryset, base), spark in zip(specs, sparks):
        stroke = SPARK_STROKE_BY_TONE[base['tone']]
        chart = _line_chart(spark, stroke, global_max)
        stats.append(dict(
            base,
            value=queryset.count(),
            chart=chart,
            chart_json=json.dumps(_line_chart_json(chart)),
        ))
    return stats


def _my_open_tasks(user):
    from projects.models import Task, TaskStatus
    return (
        Task.objects.filter(assigned_to=user)
        .exclude(status=TaskStatus.DONE)
        .select_related('project')
        .order_by('due_date', '-created_at')
    )


def _pending_owner_work(user):
    """Pending decisions in projects the user owns or manages.

    Returns None when the user has no management role anywhere, so the
    dashboard section never renders for regular members. Otherwise a dict
    with pending applications, submitted tasks awaiting review, and a total.
    """
    from projects.models import (
        MemberRole, ProjectApplication, ProjectMembership, ReviewStatus, Task,
    )

    managed_project_ids = ProjectMembership.objects.filter(
        user=user, role__in=[MemberRole.OWNER, MemberRole.MANAGER],
    ).values_list('project_id', flat=True)
    if not managed_project_ids.exists():
        return None

    return {
        'applications': (
            ProjectApplication.objects
            .filter(project_id__in=managed_project_ids, status=ProjectApplication.Status.PENDING)
            .select_related('applicant', 'project')
            .order_by('-created_at')
        ),
        'task_reviews': (
            Task.objects
            .filter(project_id__in=managed_project_ids, review_status=ReviewStatus.SUBMITTED)
            .select_related('project', 'assigned_to')
            .order_by('submitted_at')
        ),
        'total': None,  # filled by the caller via _pending_work_total
    }


def _pending_work_total(pending_work):
    if not pending_work:
        return 0
    return pending_work['applications'].count() + pending_work['task_reviews'].count()


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
        pending_work = _pending_owner_work(self.request.user)
        ctx['pending_work'] = pending_work
        ctx['pending_work_total'] = _pending_work_total(pending_work)
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
