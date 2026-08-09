from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class ProjectStatus(models.TextChoices):
    OPEN = 'open', 'Open for applications'
    ACTIVE = 'active', 'Active'
    COMPLETED = 'completed', 'Completed'
    CLOSED = 'closed', 'Closed'


class FundingStatus(models.TextChoices):
    UNFUNDED = 'unfunded', 'Seeking funding'
    PARTIAL = 'partial', 'Partially funded'
    FUNDED = 'funded', 'Fully funded'
    INSTITUTIONAL = 'institutional', 'Institutional support'


class Project(models.Model):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True)
    description = models.TextField()
    objectives = models.TextField(blank=True)
    application_question = models.CharField(
        max_length=300, blank=True,
        help_text='Optional suitability question shown to prospective team members.',
    )
    status = models.CharField(max_length=16, choices=ProjectStatus.choices, default=ProjectStatus.OPEN)
    funding_status = models.CharField(max_length=16, choices=FundingStatus.choices, default=FundingStatus.UNFUNDED)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_projects',
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL, through='ProjectMembership', related_name='projects',
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:200]
            slug, n = base, 1
            while Project.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f'{base}-{n}'
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('dashboard:project_detail', args=[self.slug])


class ProjectSection(models.Model):
    """A guarantor-defined part of a project, used to keep work organised."""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return f'{self.project}: {self.title}'


class MemberRole(models.TextChoices):
    OWNER = 'owner', 'Project owner'
    MANAGER = 'manager', 'Manager'
    MEMBER = 'member', 'Member'
    OBSERVER = 'observer', 'Observer'


class ProjectMembership(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='project_memberships',
    )
    role = models.CharField(max_length=16, choices=MemberRole.choices, default=MemberRole.MEMBER)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('project', 'user')]
        ordering = ['role', 'joined_at']

    def __str__(self):
        return f'{self.user} in {self.project} ({self.role})'


class TaskPriority(models.TextChoices):
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'


class TaskStatus(models.TextChoices):
    TODO = 'todo', 'To do'
    IN_PROGRESS = 'in_progress', 'In progress'
    DONE = 'done', 'Done'


class ReviewStatus(models.TextChoices):
    NONE = 'none', 'Not submitted'
    SUBMITTED = 'submitted', 'Awaiting review'
    APPROVED = 'approved', 'Approved'
    REJECTED = 'rejected', 'Needs revision'


class Task(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    section = models.ForeignKey(
        ProjectSection, on_delete=models.SET_NULL, null=True, blank=True, related_name='tasks',
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_tasks',
    )
    status = models.CharField(max_length=16, choices=TaskStatus.choices, default=TaskStatus.TODO)
    priority = models.CharField(max_length=8, choices=TaskPriority.choices, default=TaskPriority.MEDIUM)
    due_date = models.DateField(null=True, blank=True)
    assignment_file = models.FileField(
        upload_to='task_assignments/', blank=True, null=True,
        help_text='Optional brief, source material, or other assignment documentation.',
    )

    # Submission & review fields
    review_status = models.CharField(
        max_length=12, choices=ReviewStatus.choices, default=ReviewStatus.NONE,
    )
    submission_note = models.TextField(blank=True, help_text='Member note when submitting the task.')
    submission_file = models.FileField(
        upload_to='task_submissions/', blank=True, null=True,
        help_text='Optional file attachment (PDF, document, image, etc.).',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    manager_feedback = models.TextField(blank=True, help_text='Manager feedback on the submission.')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['status', '-priority', 'due_date']

    def __str__(self):
        return self.title

    @property
    def is_submitted(self):
        return self.review_status == ReviewStatus.SUBMITTED


class ProjectApplication(models.Model):
    """An application stays private until the guarantor explicitly accepts it."""
    class Status(models.TextChoices):
        PENDING = 'pending', 'Awaiting guarantor review'
        ACCEPTED = 'accepted', 'Accepted'
        DECLINED = 'declined', 'Declined'

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='applications')
    applicant = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='project_applications')
    message = models.TextField(blank=True)
    answer = models.TextField(blank=True, help_text='Answer to the guarantor’s suitability question.')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = [('project', 'applicant')]
        ordering = ['-created_at']


class Milestone(models.Model):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['due_date', 'created_at']

    def __str__(self):
        return self.title
