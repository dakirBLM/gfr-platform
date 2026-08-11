from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DetailView, ListView

from .forms import RegistrationForm
from .models import MembershipStatus, Role, User


class RegisterView(CreateView):
    form_class = RegistrationForm
    template_name = 'accounts/register.html'
    success_url = reverse_lazy('dashboard:home')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        messages.success(
            self.request,
            f"Welcome to GFR, {self.object.display_name}. "
            "Complete your profile to start collaborating.",
        )
        return response


class ResearcherDirectoryView(LoginRequiredMixin, ListView):
    """
    Searchable, filterable directory of all active members.
    Search covers name, username, affiliation, headline, and research interests.
    """
    model = User
    template_name = 'researchers/directory.html'
    context_object_name = 'researchers'
    paginate_by = 12

    def get_queryset(self):
        qs = (
            User.objects
            .filter(membership_status=MembershipStatus.ACTIVE)
            .prefetch_related('interests', 'followers')
            .order_by('first_name', 'last_name')
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(username__icontains=q) |
                Q(affiliation__icontains=q) |
                Q(headline__icontains=q) |
                Q(interests__name__icontains=q)
            ).distinct()
        role = self.request.GET.get('role', '').strip()
        if role:
            qs = qs.filter(role=role)
        country = self.request.GET.get('country', '').strip()
        if country:
            qs = qs.filter(country__icontains=country)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_section'] = 'researchers'
        ctx['q'] = self.request.GET.get('q', '')
        ctx['selected_role'] = self.request.GET.get('role', '')
        ctx['selected_country'] = self.request.GET.get('country', '')
        ctx['role_choices'] = [
            (v, l) for v, l in Role.choices
            if v not in (Role.GUEST, Role.ADMIN)
        ]
        ctx['countries'] = (
            User.objects
            .filter(membership_status=MembershipStatus.ACTIVE, country__gt='')
            .values_list('country', flat=True)
            .distinct()
            .order_by('country')
        )
        ctx['total'] = self.get_queryset().count()
        from social.models import Follow
        ctx['following_ids'] = set(
            Follow.objects.filter(follower=self.request.user).values_list('following_id', flat=True)
        )
        return ctx


class ResearcherProfileView(LoginRequiredMixin, DetailView):
    """
    Read-only researcher profile inside the workspace at /app/researchers/<username>/.
    Suspended members are 404'd unless the viewer is staff.
    """
    model = User
    template_name = 'researchers/profile.html'
    context_object_name = 'profile_user'
    slug_field = 'username'
    slug_url_kwarg = 'username'

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        if obj.membership_status == MembershipStatus.SUSPENDED and not self.request.user.is_staff:
            raise Http404
        return obj

    def get_context_data(self, **kwargs):
        from social.models import Follow
        ctx = super().get_context_data(**kwargs)
        u = self.object
        ctx['interests'] = u.interests.all()
        ctx['education_entries'] = u.education.all()
        ctx['publications'] = u.publications.all()
        ctx['is_self'] = self.request.user.pk == u.pk
        ctx['active_section'] = 'researchers'
        ctx['follower_count'] = u.followers.count()
        ctx['following_count'] = u.following.count()
        ctx['is_following'] = Follow.objects.filter(
            follower=self.request.user, following=u,
        ).exists()
        ctx['post_count'] = u.posts.count()
        ctx['user_posts'] = u.posts.select_related('author').prefetch_related(
            'likes', 'comments__author',
        )[:10]
        from social.views import liked_post_ids
        ctx['liked_ids'] = liked_post_ids(ctx['user_posts'], self.request.user)
        return ctx
