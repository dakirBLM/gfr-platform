from django.contrib import admin
from .models import Conversation, Message

class MessageInline(admin.TabularInline):
    model = Message
    extra = 0

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('pk', 'last_message_at')
    filter_horizontal = ('participants',)
    inlines = [MessageInline]
