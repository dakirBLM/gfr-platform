def dashboard_globals(request):
    """Inject unread counts and recent notifications for authenticated users."""
    if not request.user.is_authenticated:
        return {
            'unread_messages_count': 0,
            'unread_notifications_count': 0,
            'recent_notifications': [],
        }
    try:
        from messaging.models import Message
        from notifications.models import Notification

        unread_msgs = (
            Message.objects
            .filter(conversation__participants=request.user)
            .exclude(sender=request.user)
            .exclude(read_by=request.user)
            .count()
        )
        notifs_qs = (
            request.user.notifications
            .select_related('actor', 'project_invitation')
            .order_by('-created_at')[:15]
        )
        unread_notifs = request.user.notifications.filter(is_read=False).count()
    except Exception:
        unread_msgs = 0
        unread_notifs = 0
        notifs_qs = []

    return {
        'unread_messages_count': unread_msgs,
        'unread_notifications_count': unread_notifs,
        'recent_notifications': notifs_qs,
    }


# Keep backward-compat alias so settings.py entry still works.
def unread_messages(request):
    return dashboard_globals(request)
