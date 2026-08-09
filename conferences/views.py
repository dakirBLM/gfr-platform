from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic import ListView

from .models import AbstractSubmission, Conference, EventStatus, Registration


class ConferenceListView(LoginRequiredMixin, ListView):
    model = Conference
    template_name = 'conferences/list.html'
    context_object_name = 'conferences'

    def get_queryset(self):
        qs = Conference.objects.select_related('organizer')
        status = self.request.GET.get('status', '')
        if status:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['active_section'] = 'conferences'
        ctx['selected_status'] = self.request.GET.get('status', '')
        ctx['status_choices'] = EventStatus.choices
        ctx['my_registrations'] = set(
            Registration.objects.filter(attendee=self.request.user).values_list('conference_id', flat=True)
        )
        return ctx


@login_required
def conference_detail(request, slug):
    conf = get_object_or_404(Conference, slug=slug)
    is_registered = Registration.objects.filter(conference=conf, attendee=request.user).exists()
    my_abstract = AbstractSubmission.objects.filter(conference=conf, submitter=request.user).first()
    return render(request, 'conferences/detail.html', {
        'conf': conf,
        'is_registered': is_registered,
        'my_abstract': my_abstract,
        'registrations_count': conf.registrations.count(),
        'abstracts_count': conf.abstracts.count(),
        'active_section': 'conferences',
    })


@login_required
def register(request, slug):
    conf = get_object_or_404(Conference, slug=slug)
    if conf.status == EventStatus.PAST:
        messages.error(request, 'Registration is closed for past events.')
        return redirect('dashboard:conference_detail', slug=slug)
    _, created = Registration.objects.get_or_create(conference=conf, attendee=request.user)
    messages.success(request, f'Registered for "{conf.title}".' if created else 'Already registered.')
    return redirect('dashboard:conference_detail', slug=slug)


@login_required
def unregister(request, slug):
    conf = get_object_or_404(Conference, slug=slug)
    Registration.objects.filter(conference=conf, attendee=request.user).delete()
    messages.info(request, f'Registration cancelled for "{conf.title}".')
    return redirect('dashboard:conference_detail', slug=slug)


@login_required
def submit_abstract(request, slug):
    conf = get_object_or_404(Conference, slug=slug)
    if AbstractSubmission.objects.filter(conference=conf, submitter=request.user).exists():
        messages.info(request, 'You have already submitted an abstract for this event.')
        return redirect('dashboard:conference_detail', slug=slug)

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        abstract = request.POST.get('abstract', '').strip()
        keywords = request.POST.get('keywords', '').strip()
        if not title or not abstract:
            messages.error(request, 'Title and abstract are required.')
        else:
            AbstractSubmission.objects.create(
                conference=conf, submitter=request.user,
                title=title, abstract=abstract, keywords=keywords,
            )
            messages.success(request, 'Abstract submitted.')
            return redirect('dashboard:conference_detail', slug=slug)

    return render(request, 'conferences/submit_abstract.html', {
        'conf': conf, 'active_section': 'conferences',
    })
