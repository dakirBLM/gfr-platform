from django.conf import settings
from django.db import models


class Follow(models.Model):
    follower = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='following',
    )
    following = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='followers',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('follower', 'following')]
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.follower} → {self.following}'


class Post(models.Model):
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='posts',
    )
    body = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.author}: {self.body[:60]}'

    def like_count(self):
        return self.likes.count()

    def comment_count(self):
        return self.comments.count()


class Like(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='likes',
    )
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('user', 'post')]


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='comments',
    )
    body = models.TextField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'{self.author}: {self.body[:40]}'
