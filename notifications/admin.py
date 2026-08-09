from django.contrib import admin
from .models import Notification

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'notif_type', 'message', 'is_read', 'created_at')
    list_filter = ('notif_type', 'is_read')
    search_fields = ('recipient__username', 'message')
