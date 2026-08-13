from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class Journal(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField(blank=True)
    scope = models.TextField(blank=True, help_text='Aims and scope of the journal.')
    issn = models.CharField(max_length=9, blank=True, help_text='e.g. 1234-5678')
    cover = models.ImageField(upload_to='journal_covers/', blank=True, null=True)
    editors = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True,
        related_name='edited_journals',
        limit_choices_to={'role__in': ['editor', 'admin']},
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            # Non-Latin names slugify to an empty string; fall back so the
            # journal detail URL can never be empty or duplicate.
            base = slugify(self.name)[:220] or 'journal'
            slug, n = base, 1
            while Journal.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('dashboard:journal_detail', args=[self.slug])


class Issue(models.Model):
    journal = models.ForeignKey(Journal, on_delete=models.CASCADE, related_name='issues')
    volume = models.PositiveSmallIntegerField()
    number = models.PositiveSmallIntegerField()
    year = models.PositiveSmallIntegerField()
    published_date = models.DateField(null=True, blank=True)
    title = models.CharField(max_length=200, blank=True, help_text='Optional special issue title.')

    class Meta:
        ordering = ['-year', '-volume', '-number']
        unique_together = [('journal', 'volume', 'number')]

    def __str__(self):
        return f'{self.journal} Vol. {self.volume} No. {self.number} ({self.year})'


class ManuscriptStatus(models.TextChoices):
    DRAFT = 'draft', 'Draft'
    SUBMITTED = 'submitted', 'Submitted'
    UNDER_REVIEW = 'under_review', 'Under Review'
    REVISION_REQUIRED = 'revision_required', 'Revision Required'
    ACCEPTED = 'accepted', 'Accepted'
    REJECTED = 'rejected', 'Rejected'
    PUBLISHED = 'published', 'Published'

    @classmethod
    def terminal(cls):
        return {cls.ACCEPTED, cls.REJECTED, cls.PUBLISHED}

    @classmethod
    def badge_color(cls, status):
        return {
            cls.DRAFT:             'gray',
            cls.SUBMITTED:         'blue',
            cls.UNDER_REVIEW:      'yellow',
            cls.REVISION_REQUIRED: 'orange',
            cls.ACCEPTED:          'green',
            cls.REJECTED:          'red',
            cls.PUBLISHED:         'brand',
        }.get(status, 'gray')


class Manuscript(models.Model):
    journal = models.ForeignKey(Journal, on_delete=models.PROTECT, related_name='manuscripts')
    submitter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='manuscripts',
    )
    issue = models.ForeignKey(
        Issue, on_delete=models.SET_NULL, null=True, blank=True, related_name='manuscripts',
    )
    title = models.CharField(max_length=300)
    abstract = models.TextField()
    keywords = models.CharField(max_length=300, blank=True, help_text='Comma-separated keywords.')
    file = models.FileField(upload_to='manuscripts/', blank=True, null=True)
    status = models.CharField(
        max_length=24, choices=ManuscriptStatus.choices, default=ManuscriptStatus.DRAFT,
    )
    editor_note = models.TextField(blank=True, help_text='Note from the editor to the author.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('dashboard:manuscript_detail', args=[self.pk])

    @property
    def status_color(self):
        return ManuscriptStatus.badge_color(self.status)

    @property
    def can_submit(self):
        return self.status == ManuscriptStatus.DRAFT

    @property
    def can_revise(self):
        return self.status == ManuscriptStatus.REVISION_REQUIRED


class ManuscriptVersion(models.Model):
    manuscript = models.ForeignKey(Manuscript, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveSmallIntegerField()
    file = models.FileField(upload_to='manuscript_versions/')
    author_note = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version_number']

    def __str__(self):
        return f'{self.manuscript} v{self.version_number}'


class ReviewStatus(models.TextChoices):
    INVITED = 'invited', 'Invited'
    ACCEPTED = 'accepted', 'Accepted'
    DECLINED = 'declined', 'Declined'
    COMPLETED = 'completed', 'Completed'


class ReviewRecommendation(models.TextChoices):
    ACCEPT = 'accept', 'Accept'
    MINOR_REVISION = 'minor_revision', 'Minor Revision'
    MAJOR_REVISION = 'major_revision', 'Major Revision'
    REJECT = 'reject', 'Reject'


class Review(models.Model):
    manuscript = models.ForeignKey(Manuscript, on_delete=models.CASCADE, related_name='reviews')
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='reviews',
    )
    status = models.CharField(max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.INVITED)
    recommendation = models.CharField(
        max_length=20, choices=ReviewRecommendation.choices, blank=True,
    )
    report = models.TextField(blank=True, help_text='Confidential report to the editor.')
    comments_to_author = models.TextField(blank=True, help_text='Non-anonymous comments for the author.')
    due_date = models.DateField(null=True, blank=True)
    invited_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-invited_at']
        unique_together = [('manuscript', 'reviewer')]

    def __str__(self):
        return f'Review of "{self.manuscript}" by {self.reviewer}'
