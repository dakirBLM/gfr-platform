"""
Helpers for Sandy's guided project-creation draft.

The widget asks questions one by one, then POSTs the answers here. We stash a
cleaned draft in the session so /app/projects/new/ can open with those fields
already filled — including optional ones the user skipped.
"""

from datetime import datetime

from accounts.models import Role, User
from .forms import ProjectForm
from .models import FundingStatus, ProjectStatus

SESSION_KEY = 'sandy_project_draft'

TEXT_FIELDS = {
    'title': 200,
    'description': 5000,
    'objectives': 5000,
    'application_question': 300,
}
CHOICE_FIELDS = {
    'status': {choice.value for choice in ProjectStatus},
    'funding_status': {choice.value for choice in FundingStatus},
}
DATE_FIELDS = ('start_date', 'end_date')


def _clean_text(value, limit):
    text = (value or '').strip()
    if not text:
        return ''
    return text[:limit]


def _clean_date(value):
    text = (value or '').strip()
    if not text:
        return ''
    try:
        return datetime.strptime(text, '%Y-%m-%d').date().isoformat()
    except ValueError:
        return ''


def _invite_tokens(raw):
    if isinstance(raw, list):
        pieces = raw
    else:
        pieces = (raw or '').replace('\n', ',').replace(';', ',').split(',')
    tokens = []
    seen = set()
    for piece in pieces:
        token = piece.strip().lstrip('@')
        if not token:
            continue
        key = token.casefold()
        if key in seen:
            continue
        seen.add(key)
        tokens.append(token)
    return tokens[:20]


def resolve_invite_user_ids(tokens, *, exclude_user=None):
    """Map free-text invite tokens to eligible user primary keys."""
    if not tokens:
        return []

    # Match ProjectForm.initial_members so Sandy cannot select people the
    # create form would reject on submit.
    qs = User.objects.filter(
        role__in=[
            Role.RESEARCHER, Role.PROFESSOR, Role.REVIEWER,
            Role.EDITOR, Role.PROJECT_MANAGER,
        ],
    )
    if exclude_user is not None:
        qs = qs.exclude(pk=exclude_user.pk)

    ids = []
    seen = set()
    for token in tokens:
        match = (
            qs.filter(username__iexact=token).first()
            or qs.filter(email__iexact=token).first()
        )
        if match is None or match.pk in seen:
            continue
        seen.add(match.pk)
        ids.append(match.pk)
    return ids


def build_draft(payload, *, user):
    """
    Normalize a Sandy project payload into a session-safe dict.

    Empty / skipped answers are omitted so the create form keeps its defaults.
    """
    if not isinstance(payload, dict):
        payload = {}

    draft = {}
    for field, limit in TEXT_FIELDS.items():
        value = _clean_text(payload.get(field), limit)
        if value:
            draft[field] = value

    for field, allowed in CHOICE_FIELDS.items():
        value = (payload.get(field) or '').strip().lower()
        if value in allowed:
            draft[field] = value

    for field in DATE_FIELDS:
        value = _clean_date(payload.get(field))
        if value:
            draft[field] = value

    invites = _invite_tokens(payload.get('invites') or payload.get('invite') or '')
    member_ids = resolve_invite_user_ids(invites, exclude_user=user)
    if member_ids:
        draft['initial_members'] = member_ids

    return draft


def store_draft(session, draft):
    session[SESSION_KEY] = draft
    session.modified = True


def pop_draft(session):
    draft = session.pop(SESSION_KEY, None)
    if draft is not None:
        session.modified = True
    return draft or {}


def form_initial_from_draft(draft):
    """Split a draft into ModelForm initial values + selected member ids."""
    if not draft:
        return {}, set()

    initial = {}
    for field in (*TEXT_FIELDS, *CHOICE_FIELDS, *DATE_FIELDS):
        if draft.get(field):
            initial[field] = draft[field]

    member_ids = set()
    for value in draft.get('initial_members') or []:
        try:
            member_ids.add(int(value))
        except (TypeError, ValueError):
            continue
    if member_ids:
        initial['initial_members'] = list(member_ids)
    return initial, member_ids


def draft_is_usable(draft):
    """A draft is useful when at least one create-form field is present."""
    if not draft:
        return False
    initial, member_ids = form_initial_from_draft(draft)
    return bool(initial) or bool(member_ids)


# Touch ProjectForm so static checkers keep the create field list in sync.
_ = ProjectForm
