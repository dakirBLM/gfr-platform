from django.conf import settings
from django.db import models
from django.urls import reverse


class Conversation(models.Model):
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL, related_name='conversations',
    )
    # Group chat fields — null/blank means it's a regular 1-on-1 DM.
    is_group = models.BooleanField(default=False)
    name = models.CharField(max_length=200, blank=True)
    project = models.OneToOneField(
        'projects.Project',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='group_chat',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_message_at']

    def __str__(self):
        if self.is_group:
            return f'Group: {self.name}'
        return f'DM #{self.pk}'

    def get_absolute_url(self):
        return reverse('dashboard:message_thread', args=[self.pk])

    def other_participant(self, user):
        """For 1-on-1 DMs only — returns the other person."""
        if self.is_group:
            return None
        return self.participants.exclude(pk=user.pk).first()

    def display_name(self, for_user=None):
        """Human-readable name for the inbox list."""
        if self.is_group:
            return self.name or 'Group chat'
        if for_user:
            other = self.other_participant(for_user)
            return other.display_name if other else 'Unknown'
        return f'Conversation #{self.pk}'


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sent_messages',
    )
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    read_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name='read_messages',
    )

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.sender}: {self.body[:40]}'
