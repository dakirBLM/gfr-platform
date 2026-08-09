"""
Helpers for keeping project group chats in sync with project membership.
Imported by projects.views to avoid circular imports.
"""
from .models import Conversation


def get_or_create_project_chat(project):
    """Return the group conversation for a project, creating it if needed."""
    conv, created = Conversation.objects.get_or_create(
        project=project,
        defaults={
            'is_group': True,
            'name': project.title,
        },
    )
    return conv


def sync_member_to_project_chat(project, user, add: bool = True):
    """Add or remove a user from the project group chat."""
    conv = get_or_create_project_chat(project)
    if add:
        conv.participants.add(user)
    else:
        conv.participants.remove(user)
