from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.templatetags.static import static
from django.urls import reverse
from django.utils.text import slugify


class Role(models.TextChoices):
    """
    Role on the platform. Drives the permission matrix described in the spec.
    A user has exactly one primary role; staff/admin is set via is_staff/is_superuser.
    """
    GUEST = 'guest', 'Guest'
    STUDENT = 'student', 'Postgraduate Student'
    RESEARCHER = 'researcher', 'Researcher'
    PROFESSOR = 'professor', 'Senior Researcher / Professor'
    ASSISTANT_PROFESSOR = 'assistant_professor', 'Assistant Professor'
    REVIEWER = 'reviewer', 'Reviewer'
    EDITOR = 'editor', 'Editor'
    PROJECT_MANAGER = 'project_manager', 'Project Manager'
    ADMIN = 'admin', 'Administrator'


class MembershipStatus(models.TextChoices):
    PENDING = 'pending', 'Pending review'
    ACTIVE = 'active', 'Active'
    SUSPENDED = 'suspended', 'Suspended'


orcid_validator = RegexValidator(
    regex=r'^\d{4}-\d{4}-\d{4}-\d{3}[\dX]$',
    message='ORCID must follow the 0000-0000-0000-0000 format (last digit may be X).',
)


class ResearchInterest(models.Model):
    """Free-form, lightly normalized topic tag (e.g. "Machine Learning", "Bioinformatics")."""
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:100]
        super().save(*args, **kwargs)

    @classmethod
    def get_or_create_by_name(cls, raw_name: str) -> 'ResearchInterest | None':
        name = (raw_name or '').strip()
        if not name:
            return None
        slug = slugify(name)[:100]
        if not slug:
            return None
        obj, _ = cls.objects.get_or_create(slug=slug, defaults={'name': name})
        return obj


class User(AbstractUser):
    """
    Custom user. Email is the canonical identifier; username stays for admin compat.
    """
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=32, choices=Role.choices, default=Role.STUDENT)
    membership_status = models.CharField(
        max_length=16, choices=MembershipStatus.choices, default=MembershipStatus.ACTIVE,
    )
    affiliation = models.CharField(max_length=200, blank=True)
    country = models.CharField(max_length=80, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    headline = models.CharField(
        max_length=160, blank=True,
        help_text='One-line academic headline shown on profile cards.',
    )

    # Academic identity
    biography = models.TextField(blank=True, help_text='Short biography for your public profile.')
    orcid = models.CharField(max_length=19, blank=True, validators=[orcid_validator])
    website = models.URLField(blank=True)
    linkedin = models.URLField(blank=True)
    google_scholar = models.URLField(blank=True)
    interests = models.ManyToManyField(ResearchInterest, blank=True, related_name='researchers')

    accepted_ethics_code = models.BooleanField(default=False)

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['email']

    class Meta:
        ordering = ['-date_joined']

    def __str__(self) -> str:
        return self.get_full_name() or self.username

    def get_absolute_url(self) -> str:
        return reverse('dashboard:researcher_profile', args=[self.username])

    @property
    def display_name(self) -> str:
        return self.get_full_name() or self.username

    @property
    def avatar_url(self) -> str:
        """Uploaded avatar if present, otherwise the platform-wide default silhouette."""
        if self.avatar and hasattr(self.avatar, 'url'):
            try:
                return self.avatar.url
            except ValueError:
                pass
        return static('img/default-avatar.svg')

    def has_role(self, *roles: str) -> bool:
        return self.role in roles or self.is_superuser

    @property
    def can_submit_paper(self) -> bool:
        return self.has_role(Role.RESEARCHER, Role.PROFESSOR, Role.EDITOR, Role.ADMIN)

    @property
    def can_peer_review(self) -> bool:
        return self.has_role(Role.PROFESSOR, Role.REVIEWER, Role.EDITOR, Role.ADMIN)

    @property
    def can_create_project(self) -> bool:
        # A research project must have an academic guarantor.
        return self.has_role(Role.PROFESSOR, Role.ASSISTANT_PROFESSOR, Role.ADMIN)

    @property
    def can_download_full_papers(self) -> bool:
        return self.role != Role.STUDENT or self.is_superuser

    @property
    def can_manage_users(self) -> bool:
        return self.has_role(Role.ADMIN) or self.is_superuser


class Education(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='education')
    degree = models.CharField(max_length=200, help_text='e.g. PhD in Computer Science')
    institution = models.CharField(max_length=200)
    year_from = models.PositiveSmallIntegerField(null=True, blank=True)
    year_to = models.PositiveSmallIntegerField(null=True, blank=True, help_text='Leave empty if ongoing.')
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year_to', '-year_from', '-created_at']

    def __str__(self) -> str:
        return f'{self.degree} — {self.institution}'

    @property
    def years_label(self) -> str:
        if not self.year_from and not self.year_to:
            return ''
        end = self.year_to or 'present'
        return f'{self.year_from or ""}–{end}'.strip('–')


class Publication(models.Model):
    """
    Self-managed publication entry on a researcher's profile. Distinct from
    peer-reviewed manuscripts submitted to GFR journals (those live in the journals app).
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='publications')
    title = models.CharField(max_length=300)
    authors = models.CharField(max_length=400, blank=True, help_text='Comma-separated list as it appears on the paper.')
    venue = models.CharField(max_length=200, blank=True, help_text='Journal or conference name.')
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    doi = models.CharField(max_length=100, blank=True)
    url = models.URLField(blank=True)
    abstract = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-year', '-created_at']

    def __str__(self) -> str:
        return self.title
