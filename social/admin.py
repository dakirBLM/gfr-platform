from django.contrib import admin
from .models import Comment, Follow, Like, Post

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('author', 'body', 'created_at')
    search_fields = ('author__username', 'body')

@admin.register(Follow)
class FollowAdmin(admin.ModelAdmin):
    list_display = ('follower', 'following', 'created_at')

admin.site.register(Like)
admin.site.register(Comment)
