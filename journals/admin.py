from django.contrib import admin

from .models import Issue, Journal, Manuscript, ManuscriptVersion, Review


class IssueInline(admin.TabularInline):
    model = Issue
    extra = 0


@admin.register(Journal)
class JournalAdmin(admin.ModelAdmin):
    list_display = ('name', 'issn', 'is_active')
    prepopulated_fields = {'slug': ('name',)}
    filter_horizontal = ('editors',)
    inlines = [IssueInline]


class ReviewInline(admin.TabularInline):
    model = Review
    extra = 0
    fields = ('reviewer', 'status', 'recommendation', 'due_date')


class VersionInline(admin.TabularInline):
    model = ManuscriptVersion
    extra = 0


@admin.register(Manuscript)
class ManuscriptAdmin(admin.ModelAdmin):
    list_display = ('title', 'journal', 'submitter', 'status', 'created_at')
    list_filter = ('status', 'journal')
    search_fields = ('title', 'submitter__username')
    inlines = [ReviewInline, VersionInline]
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('manuscript', 'reviewer', 'status', 'recommendation', 'due_date')
    list_filter = ('status', 'recommendation')
