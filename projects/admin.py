from django.contrib import admin
from .models import Milestone, Project, ProjectMembership, Task


class MembershipInline(admin.TabularInline):
    model = ProjectMembership
    extra = 0


class TaskInline(admin.TabularInline):
    model = Task
    extra = 0


class MilestoneInline(admin.TabularInline):
    model = Milestone
    extra = 0


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'status', 'funding_status', 'created_by', 'created_at')
    list_filter = ('status', 'funding_status')
    search_fields = ('title', 'created_by__username')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [MembershipInline, TaskInline, MilestoneInline]
