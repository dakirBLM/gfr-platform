from django.contrib import admin
from .models import AbstractSubmission, Conference, Registration

class AbstractInline(admin.TabularInline):
    model = AbstractSubmission
    extra = 0

@admin.register(Conference)
class ConferenceAdmin(admin.ModelAdmin):
    list_display = ('title', 'event_type', 'status', 'start_date', 'end_date')
    list_filter = ('event_type', 'status')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [AbstractInline]

@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ('attendee', 'conference', 'registered_at')
