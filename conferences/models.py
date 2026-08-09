from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class EventType(models.TextChoices):
    CONFERENCE = 'conference', 'International Conference'
    WORKSHOP = 'workshop', 'Workshop'
    SUMMER_SCHOOL = 'summer_school', 'Summer School'
    WEBINAR = 'webinar', 'Webinar'


class EventStatus(models.TextChoices):
    UPCOMING = 'upcoming', 'Upcoming'
    ONGOING = 'ongoing', 'Ongoing'
    PAST = 'past', 'Past'


class AbstractStatus(models.TextChoices):
    SUBMITTED = 'submitted', 'Submitted'
    UNDER_REVIEW = 'under_review', 'Under Review'
    ACCEPTED = 'accepted', 'Accepted'
    REJECTED = 'rejected', 'Rejected'


class Conference(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    event_type = models.CharField(max_length=16, choices=EventType.choices, default=EventType.CONFERENCE)
    status = models.CharField(max_length=12, choices=EventStatus.choices, default=EventStatus.UPCOMING)
    description = models.TextField()
    topics = models.TextField(blank=True, help_text='One topic per line.')
    location = models.CharField(max_length=200, blank=True)
    is_virtual = models.BooleanField(default=False)
    start_date = models.DateField()
    end_date = models.DateField()
    abstract_deadline = models.DateField(null=True, blank=True)
    registration_deadline = models.DateField(null=True, blank=True)
    website = models.URLField(blank=True)
    banner = models.ImageField(upload_to='conference_banners/', blank=True, null=True)
    organizer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='organized_conferences',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_date']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200]
            slug, n = base, 1
            while Conference.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('dashboard:conference_detail', args=[self.slug])

    @property
    def topic_list(self):
        return [t.strip() for t in self.topics.splitlines() if t.strip()]


class AbstractSubmission(models.Model):
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name='abstracts')
    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='abstract_submissions',
    )
    title = models.CharField(max_length=300)
    abstract = models.TextField()
    keywords = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=16, choices=AbstractStatus.choices, default=AbstractStatus.SUBMITTED)
    submitted_at = models.DateTimeField(auto_now_add=True)
    feedback = models.TextField(blank=True)

    class Meta:
        ordering = ['-submitted_at']
        unique_together = [('conference', 'submitter')]

    def __str__(self):
        return f'{self.title} — {self.conference}'


class Registration(models.Model):
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name='registrations')
    attendee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conference_registrations',
    )
    registered_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('conference', 'attendee')]
        ordering = ['-registered_at']

    def __str__(self):
        return f'{self.attendee} @ {self.conference}'
