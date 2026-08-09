from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import User
from .models import Conversation, Message


@login_required
def inbox(request):
    convs = request.user.conversations.prefetch_related(
        'participants', 'messages__sender',
    ).order_by('-last_message_at')

    # Pre-compute per-conversation data in the view — templates can't call
    # methods with arguments, so other_participant(user) must be resolved here.
    conv_data = []
    for c in convs:
        unread = c.messages.exclude(read_by=request.user).exclude(sender=request.user).count()
        last_msg = c.messages.order_by('-created_at').first()
        if c.is_group:
            # For group chats show up to 4 member avatars
            members = list(c.participants.all()[:4])
            conv_data.append({
                'conv': c,
                'is_group': True,
                'group_name': c.name or c.project.title if c.project else 'Group chat',
                'group_members': members,
                'member_count': c.participants.count(),
                'unread': unread,
                'last_msg': last_msg,
            })
        else:
            other = c.participants.exclude(pk=request.user.pk).first()
            conv_data.append({
                'conv': c,
                'is_group': False,
                'other': other,
                'unread': unread,
                'last_msg': last_msg,
            })

    return render(request, 'messaging/inbox.html', {
        'conv_data': conv_data,
        'active_section': 'messages',
    })


@login_required
def new_conversation(request):
    q = request.GET.get('q', '').strip()
    users = []
    if q:
        users = (
            User.objects
            .filter(Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(username__icontains=q))
            .exclude(pk=request.user.pk)
            .exclude(membership_status='suspended')[:10]
        )

    if request.method == 'POST':
        recipient_id = request.POST.get('recipient')
        body = request.POST.get('body', '').strip()
        if not recipient_id or not body:
            return render(request, 'messaging/new.html', {
                'error': 'Please select a recipient and write a message.',
                'users': users, 'q': q, 'active_section': 'messages',
            })
        recipient = get_object_or_404(User, pk=recipient_id)
        if recipient == request.user:
            raise Http404

        existing = Conversation.objects.filter(participants=request.user).filter(participants=recipient)
        if existing.exists():
            conv = existing.first()
        else:
            conv = Conversation.objects.create()
            conv.participants.add(request.user, recipient)

        msg = Message.objects.create(conversation=conv, sender=request.user, body=body)
        msg.read_by.add(request.user)
        conv.last_message_at = msg.created_at
        conv.save(update_fields=['last_message_at'])
        return redirect('dashboard:message_thread', pk=conv.pk)

    return render(request, 'messaging/new.html', {
        'users': users, 'q': q, 'active_section': 'messages',
    })


@login_required
def thread(request, pk):
    conv = get_object_or_404(Conversation, pk=pk)
    if not conv.participants.filter(pk=request.user.pk).exists():
        raise Http404

    for msg in conv.messages.exclude(read_by=request.user):
        msg.read_by.add(request.user)

    if request.method == 'POST':
        body = request.POST.get('body', '').strip()
        if body:
            msg = Message.objects.create(conversation=conv, sender=request.user, body=body)
            msg.read_by.add(request.user)
            conv.last_message_at = timezone.now()
            conv.save(update_fields=['last_message_at'])
        return redirect('dashboard:message_thread', pk=pk)

    other = conv.other_participant(request.user)
    group_members = list(conv.participants.all()) if conv.is_group else []
    return render(request, 'messaging/thread.html', {
        'conv': conv,
        'other': other,
        'group_members': group_members,
        'messages': conv.messages.select_related('sender').all(),
        'active_section': 'messages',
    })
