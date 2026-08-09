from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Education, Publication, ResearchInterest, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'email', 'role', 'membership_status', 'affiliation', 'is_staff')
    list_filter = ('role', 'membership_status', 'is_staff', 'is_superuser')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'affiliation')
    filter_horizontal = ('groups', 'user_permissions', 'interests')

    fieldsets = DjangoUserAdmin.fieldsets + (
        ('GFR profile', {
            'fields': ('role', 'membership_status', 'affiliation', 'country',
                       'avatar', 'headline', 'biography', 'accepted_ethics_code'),
        }),
        ('Academic identity', {
            'fields': ('orcid', 'website', 'linkedin', 'google_scholar', 'interests'),
        }),
    )
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (
        ('GFR profile', {'fields': ('email', 'role', 'affiliation')}),
    )


@admin.register(ResearchInterest)
class ResearchInterestAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ('user', 'degree', 'institution', 'year_from', 'year_to')
    search_fields = ('user__username', 'degree', 'institution')


@admin.register(Publication)
class PublicationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'year', 'venue')
    search_fields = ('title', 'user__username', 'venue', 'authors')
