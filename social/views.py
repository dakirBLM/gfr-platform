from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from accounts.models import User
from .models import Comment, Follow, Like, Post


def get_feed_posts(user, limit=20, offset=0):
    """Posts from the user + everyone they follow, newest first."""
    following_ids = user.following.values_list('following_id', flat=True)
    ids = list(following_ids) + [user.pk]
    return (
        Post.objects
        .filter(author_id__in=ids)
        .select_related('author')
        .prefetch_related('likes', 'comments__author')
        .order_by('-created_at')[offset:offset + limit]
    )


def liked_post_ids(posts, user):
    """Set of post PKs liked by this user — used in templates."""
    if not user.is_authenticated:
        return set()
    return set(Like.objects.filter(user=user, post__in=posts).values_list('post_id', flat=True))


@login_required
def feed_page(request):
    """Small HTML fragment fetched by the dashboard as the reader scrolls."""
    try:
        page = max(1, int(request.GET.get('page', '1')))
    except ValueError:
        raise Http404
    page_size = 5
    # Fetch one extra record to say whether another lightweight request is useful.
    posts = list(get_feed_posts(request.user, limit=page_size + 1, offset=(page - 1) * page_size))
    has_more = len(posts) > page_size
    posts = posts[:page_size]
    response = render(request, 'social/feed_page.html', {
        'feed_posts': posts,
        'liked_ids': liked_post_ids(posts, request.user),
    })
    response['X-Has-More'] = 'true' if has_more else 'false'
    response['X-Next-Page'] = str(page + 1)
    return response


@login_required
@require_POST
def create_post(request):
    body = request.POST.get('body', '').strip()
    if body:
        Post.objects.create(author=request.user, body=body[:1000])
    return redirect(request.META.get('HTTP_REFERER') or 'dashboard:home')


@login_required
@require_POST
def delete_post(request, pk):
    post = get_object_or_404(Post, pk=pk, author=request.user)
    post.delete()
    return redirect(request.META.get('HTTP_REFERER') or 'dashboard:home')


@login_required
@require_POST
def toggle_like(request, pk):
    post = get_object_or_404(Post, pk=pk)
    obj, created = Like.objects.get_or_create(user=request.user, post=post)
    if not created:
        obj.delete()
    return redirect(request.META.get('HTTP_REFERER') or 'dashboard:home')


def redirect_to_post_comments(request, post_pk):
    """Back to the page the reader came from, with this post's comments expanded."""
    referer = request.META.get('HTTP_REFERER')
    if not referer:
        return redirect('dashboard:home')
    parts = urlsplit(referer)
    query = parse_qs(parts.query)
    query['commented'] = [str(post_pk)]
    # Scheme and host are dropped so the redirect can only stay on this site.
    return redirect(urlunsplit(
        ('', '', parts.path or '/', urlencode(query, doseq=True), f'post-{post_pk}'),
    ))


@login_required
@require_POST
def add_comment(request, pk):
    post = get_object_or_404(Post, pk=pk)
    body = request.POST.get('body', '').strip()
    if body:
        Comment.objects.create(post=post, author=request.user, body=body[:500])
    return redirect_to_post_comments(request, post.pk)


@login_required
@require_POST
def toggle_follow(request, username):
    target = get_object_or_404(User, username=username)
    if target == request.user:
        raise Http404
    obj, created = Follow.objects.get_or_create(follower=request.user, following=target)
    if not created:
        obj.delete()
    else:
        from notifications.models import NotifType, notify
        notify(
            recipient=target, actor=request.user,
            notif_type=NotifType.NEW_FOLLOW,
            message=f'{request.user.display_name} started following you.',
            url=f'/app/researchers/{request.user.username}/',
        )
    return redirect(request.META.get('HTTP_REFERER') or 'dashboard:home')
