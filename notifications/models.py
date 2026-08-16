from django.conf import settings
from django.db import models


class NotifType(models.TextChoices):
    TASK_ASSIGNED   = 'task_assigned',   'Task assigned to you'
    TASK_SUBMITTED  = 'task_submitted',  'Task submitted for review'
    TASK_APPROVED   = 'task_approved',   'Task approved'
    TASK_REJECTED   = 'task_rejected',   'Task needs revision'
    PROJECT_JOINED  = 'project_joined',  'Member joined project'
    PROJECT_ADDED   = 'project_added',   'Added to project'
    PROJECT_APPLICATION = 'project_application', 'Project application received'
    PROJECT_APPLICATION_DECISION = 'project_application_decision', 'Project application decision'
    PROJECT_INVITATION = 'project_invitation', 'Project invitation received'
    PROJECT_INVITATION_DECLINED = 'project_invitation_declined', 'Project invitation declined'
    MANUSCRIPT_UPDATE = 'manuscript_update', 'Manuscript status updated'
    NEW_FOLLOW      = 'new_follow',      'New follower'
    NEW_MESSAGE     = 'new_message',     'New message'


class Notification(models.Model):
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications',
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='sent_notifications',
    )
    notif_type = models.CharField(max_length=32, choices=NotifType.choices)
    message = models.CharField(max_length=255)
    url = models.CharField(max_length=500, blank=True)
    project_invitation = models.ForeignKey(
        'projects.ProjectInvitation', on_delete=models.CASCADE,
        null=True, blank=True, related_name='notifications',
        help_text='Linked when this notification is about a project invitation.',
    )
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'→ {self.recipient}: {self.message}'


def notify(recipient, notif_type: str, message: str, url: str = '', actor=None, project_invitation=None):
    """
    Create a notification. Safe to call from anywhere — silently ignores
    sending a notification to the actor themselves.
    """
    if actor and actor.pk == recipient.pk:
        return
    Notification.objects.create(
        recipient=recipient,
        actor=actor,
        notif_type=notif_type,
        message=message,
        url=url,
        project_invitation=project_invitation,
    )
