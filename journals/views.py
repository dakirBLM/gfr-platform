from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.generic import DetailView, ListView

from .forms import (
    AssignReviewerForm, EditorDecisionForm,
    ManuscriptSubmitForm, ReviewReportForm, RevisionForm,
)
from .models import (
    Journal, Manuscript, ManuscriptStatus, ManuscriptVersion,
    Review, ReviewStatus,
)


class JournalListView(LoginRequiredMixin, ListView):
    model = Journal
    template_name = 'journals/list.html'
    context_object_name = 'journals'
    queryset = Journal.objects.filter(is_active=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_section'] = 'journals'
        return ctx


class JournalDetailView(LoginRequiredMixin, DetailView):
    model = Journal
    template_name = 'journals/detail.html'
    context_object_name = 'journal'

    def get_object(self, queryset=None):
        return get_object_or_404(Journal, slug=self.kwargs['slug'], is_active=True)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_section'] = 'journals'
        ctx['recent_issues'] = self.object.issues.all()[:5]
        ctx['can_submit'] = self.request.user.can_submit_paper
        return ctx


@login_required
def submit_manuscript(request, slug):
    journal = get_object_or_404(Journal, slug=slug, is_active=True)
    if not request.user.can_submit_paper:
        messages.error(request, 'Your membership level does not allow manuscript submission.')
        return redirect('dashboard:journal_detail', slug=slug)

    form = ManuscriptSubmitForm(request.POST or None, request.FILES or None, journal=journal)
    if request.method == 'POST' and form.is_valid():
        ms = form.save(commit=False)
        ms.submitter = request.user
        ms.status = ManuscriptStatus.SUBMITTED
        ms.save()
        messages.success(request, f'"{ms.title}" submitted to {journal.name}.')
        return redirect('dashboard:manuscript_detail', pk=ms.pk)

    return render(request, 'journals/submit.html', {
        'journal': journal, 'form': form, 'active_section': 'journals',
    })


@login_required
def manuscript_list(request):
    qs = Manuscript.objects.filter(submitter=request.user).select_related('journal')
    return render(request, 'journals/manuscript_list.html', {
        'manuscripts': qs, 'active_section': 'manuscripts',
    })


@login_required
def manuscript_detail(request, pk):
    ms = get_object_or_404(Manuscript, pk=pk)
    is_author = ms.submitter == request.user
    is_editor = request.user in ms.journal.editors.all() or request.user.is_superuser
    if not (is_author or is_editor or request.user.is_staff):
        raise Http404
    return render(request, 'journals/manuscript_detail.html', {
        'ms': ms, 'is_author': is_author, 'is_editor': is_editor,
        'reviews': ms.reviews.select_related('reviewer').all() if is_editor else [],
        'versions': ms.versions.all(),
        'active_section': 'manuscripts',
    })


@login_required
def submit_revision(request, pk):
    ms = get_object_or_404(Manuscript, pk=pk, submitter=request.user)
    if ms.status != ManuscriptStatus.REVISION_REQUIRED:
        messages.error(request, 'This manuscript does not require a revision right now.')
        return redirect('dashboard:manuscript_detail', pk=pk)

    form = RevisionForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        ManuscriptVersion.objects.create(
            manuscript=ms,
            version_number=ms.versions.count() + 1,
            file=form.cleaned_data['file'],
            author_note=form.cleaned_data['author_note'],
        )
        ms.status = ManuscriptStatus.UNDER_REVIEW
        ms.save(update_fields=['status', 'updated_at'])
        messages.success(request, 'Revision submitted.')
        return redirect('dashboard:manuscript_detail', pk=pk)

    return render(request, 'journals/revise.html', {
        'ms': ms, 'form': form, 'active_section': 'manuscripts',
    })


@login_required
def review_queue(request):
    if not request.user.can_peer_review:
        messages.error(request, 'You do not have a reviewer role.')
        return redirect('dashboard:home')
    reviews = (
        Review.objects
        .filter(reviewer=request.user)
        .exclude(status=ReviewStatus.DECLINED)
        .select_related('manuscript__journal')
    )
    return render(request, 'journals/review_queue.html', {
        'reviews': reviews, 'active_section': 'reviews',
    })


@login_required
def review_detail(request, pk):
    review = get_object_or_404(Review, pk=pk, reviewer=request.user)
    if review.status == ReviewStatus.DECLINED:
        raise Http404

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'accept' and review.status == ReviewStatus.INVITED:
            review.status = ReviewStatus.ACCEPTED
            review.save(update_fields=['status'])
            messages.success(request, 'Review accepted.')
            return redirect('dashboard:review_detail', pk=pk)

        if action == 'decline' and review.status == ReviewStatus.INVITED:
            review.status = ReviewStatus.DECLINED
            review.save(update_fields=['status'])
            messages.info(request, 'Review declined.')
            return redirect('dashboard:review_queue')

        if action == 'submit' and review.status == ReviewStatus.ACCEPTED:
            form = ReviewReportForm(request.POST, instance=review)
            if form.is_valid():
                r = form.save(commit=False)
                r.status = ReviewStatus.COMPLETED
                r.submitted_at = timezone.now()
                r.save()
                ms = review.manuscript
                if ms.status not in ManuscriptStatus.terminal():
                    ms.status = ManuscriptStatus.UNDER_REVIEW
                    ms.save(update_fields=['status', 'updated_at'])
                messages.success(request, 'Report submitted. Thank you.')
                return redirect('dashboard:review_queue')
            return render(request, 'journals/review_detail.html', {
                'review': review, 'form': form, 'active_section': 'reviews',
            })

    form = ReviewReportForm(instance=review)
    return render(request, 'journals/review_detail.html', {
        'review': review, 'form': form, 'active_section': 'reviews',
    })


@login_required
def editor_queue(request):
    if request.user.is_superuser:
        journals = Journal.objects.filter(is_active=True)
    else:
        journals = Journal.objects.filter(editors=request.user)
    if not journals.exists():
        messages.error(request, 'You are not an editor of any journal.')
        return redirect('dashboard:journal_list')
    manuscripts = (
        Manuscript.objects
        .filter(journal__in=journals)
        .exclude(status__in=[ManuscriptStatus.DRAFT, ManuscriptStatus.PUBLISHED])
        .select_related('journal', 'submitter')
        .prefetch_related('reviews')
    )
    return render(request, 'journals/editor_queue.html', {
        'manuscripts': manuscripts, 'active_section': 'journals',
    })


@login_required
def editor_manuscript(request, pk):
    ms = get_object_or_404(Manuscript, pk=pk)
    is_editor = request.user in ms.journal.editors.all() or request.user.is_superuser
    if not is_editor:
        raise Http404

    assign_form = AssignReviewerForm(manuscript=ms)
    decision_form = EditorDecisionForm()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'assign':
            assign_form = AssignReviewerForm(request.POST, manuscript=ms)
            if assign_form.is_valid():
                Review.objects.get_or_create(
                    manuscript=ms,
                    reviewer=assign_form.cleaned_data['reviewer'],
                    defaults={'due_date': assign_form.cleaned_data.get('due_date')},
                )
                if ms.status == ManuscriptStatus.SUBMITTED:
                    ms.status = ManuscriptStatus.UNDER_REVIEW
                    ms.save(update_fields=['status', 'updated_at'])
                messages.success(request, 'Reviewer assigned.')
                return redirect('dashboard:editor_manuscript', pk=pk)

        elif action == 'decide':
            decision_form = EditorDecisionForm(request.POST)
            if decision_form.is_valid():
                ms.status = decision_form.cleaned_data['decision']
                ms.editor_note = decision_form.cleaned_data.get('editor_note', '')
                ms.save(update_fields=['status', 'editor_note', 'updated_at'])
                messages.success(request, f'Decision: {ms.get_status_display()}.')
                from notifications.models import NotifType, notify
                notify(
                    recipient=ms.submitter, actor=request.user,
                    notif_type=NotifType.MANUSCRIPT_UPDATE,
                    message=f'Your manuscript "{ms.title[:60]}" status updated to: {ms.get_status_display()}.',
                    url=f'/app/journals/manuscripts/{ms.pk}/',
                )
                return redirect('dashboard:editor_queue')

    return render(request, 'journals/editor_manuscript.html', {
        'ms': ms,
        'reviews': ms.reviews.select_related('reviewer').all(),
        'versions': ms.versions.all(),
        'assign_form': assign_form,
        'decision_form': decision_form,
        'active_section': 'journals',
    })
