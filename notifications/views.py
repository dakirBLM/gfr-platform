from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
@require_POST
def mark_read(request, pk):
    n = get_object_or_404(Notification, pk=pk, recipient=request.user)
    n.is_read = True
    n.save(update_fields=['is_read'])
    return redirect(n.url or '/')


@login_required
@require_POST
def mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return redirect(request.META.get('HTTP_REFERER') or '/')
