from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError

from .models import Education, Publication, ResearchInterest, Role, User


MAX_AVATAR_BYTES = 4 * 1024 * 1024  # 4 MB
ALLOWED_AVATAR_CONTENT_TYPES = {'image/jpeg', 'image/png', 'image/webp', 'image/gif'}

# Shared input styling. Applied via __init__ on every form below so templates
# stay free of widget tweaks.
INPUT_CSS = (
    'mt-1 w-full rounded-md border border-ink-200 px-3 py-2 text-sm '
    'focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-brand-500'
)


def _apply_input_css(form: forms.Form, skip: set[str] = frozenset()) -> None:
    for name, field in form.fields.items():
        if name in skip:
            continue
        widget = field.widget
        if isinstance(widget, (forms.CheckboxInput, forms.FileInput, forms.ClearableFileInput)):
            continue
        css = INPUT_CSS
        if getattr(widget, 'input_type', None) == 'password':
            # Extra right padding so the visibility toggle never overlaps the text.
            css += ' pr-10'
        existing = widget.attrs.get('class', '')
        widget.attrs['class'] = (existing + ' ' + css).strip()


class AvatarForm(forms.ModelForm):
    """Profile photo upload. Empty file means no change; the model field already allows null."""
    class Meta:
        model = User
        fields = ['avatar']

    def clean_avatar(self):
        avatar = self.cleaned_data.get('avatar')
        if not avatar or not hasattr(avatar, 'content_type'):
            return avatar
        if avatar.size > MAX_AVATAR_BYTES:
            raise ValidationError('Image is too large. Please keep it under 4 MB.')
        if avatar.content_type not in ALLOWED_AVATAR_CONTENT_TYPES:
            raise ValidationError('Unsupported format. Use JPG, PNG, WebP, or GIF.')
        return avatar


class RegistrationForm(UserCreationForm):
    """
    Public sign-up form. Members default to STUDENT role; promotion to
    Researcher/Professor/etc. is gated by admin review per the spec.
    """
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    email = forms.EmailField()
    affiliation = forms.CharField(
        max_length=200, required=False,
        help_text='University, research center, or institution.',
    )
    country = forms.CharField(max_length=80, required=False)
    role = forms.ChoiceField(
        choices=[
            (Role.STUDENT, 'Postgraduate Student'),
            (Role.RESEARCHER, 'Researcher'),
            (Role.PROFESSOR, 'Senior Researcher / Professor'),
        ],
        initial=Role.STUDENT,
        help_text='Senior roles (Reviewer, Editor) are assigned by the editorial board after review.',
    )
    accepted_ethics_code = forms.BooleanField(
        required=True,
        label='I commit to the GFR Scientific Code of Ethics.',
    )

    class Meta:
        model = User
        fields = (
            'username', 'first_name', 'last_name', 'email',
            'affiliation', 'country', 'role',
            'password1', 'password2', 'accepted_ethics_code',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_input_css(self, skip={'accepted_ethics_code'})

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('An account with this email already exists.')
        return email


class ProfileForm(forms.ModelForm):
    """
    Identity, headline, biography, affiliation, social links, and research interests.
    Interests are managed as a free-text comma-separated list — get-or-create lookups
    happen in `save()` so users don't see admin-managed tag pickers.
    """
    interests_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'placeholder': 'Machine Learning, Bioinformatics, …'}),
        label='Research interests',
        help_text='Comma-separated. New tags are created on the fly.',
    )

    class Meta:
        model = User
        fields = [
            'first_name', 'last_name', 'headline', 'affiliation', 'country',
            'biography', 'orcid', 'website', 'linkedin', 'google_scholar',
        ]
        widgets = {
            'biography': forms.Textarea(attrs={'rows': 5}),
            'orcid': forms.TextInput(attrs={'placeholder': '0000-0000-0000-0000'}),
            'website': forms.URLInput(attrs={'placeholder': 'https://your-website.example'}),
            'linkedin': forms.URLInput(attrs={'placeholder': 'https://linkedin.com/in/…'}),
            'google_scholar': forms.URLInput(attrs={'placeholder': 'https://scholar.google.com/citations?user=…'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_input_css(self)
        # Pre-fill the comma-separated interests field from the M2M.
        if self.instance.pk:
            self.fields['interests_text'].initial = ', '.join(
                self.instance.interests.values_list('name', flat=True)
            )

    def save(self, commit=True):
        user = super().save(commit=commit)
        raw = self.cleaned_data.get('interests_text', '')
        names = [n.strip() for n in raw.split(',') if n.strip()]
        # De-dupe by lowercase name; preserve user-entered casing on first occurrence.
        seen = {}
        for name in names:
            key = name.lower()
            if key not in seen:
                seen[key] = name
        interests = []
        for name in seen.values():
            obj = ResearchInterest.get_or_create_by_name(name)
            if obj is not None:
                interests.append(obj)
        if commit:
            user.interests.set(interests)
        else:
            self._pending_interests = interests
        return user


class EducationForm(forms.ModelForm):
    class Meta:
        model = Education
        fields = ['degree', 'institution', 'year_from', 'year_to', 'description']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'year_from': forms.NumberInput(attrs={'min': 1950, 'max': 2100}),
            'year_to': forms.NumberInput(attrs={'min': 1950, 'max': 2100}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_input_css(self)

    def clean(self):
        cleaned = super().clean()
        yf, yt = cleaned.get('year_from'), cleaned.get('year_to')
        if yf and yt and yt < yf:
            raise ValidationError('"Year to" must be greater than or equal to "Year from".')
        return cleaned


class PublicationForm(forms.ModelForm):
    class Meta:
        model = Publication
        fields = ['title', 'authors', 'venue', 'year', 'doi', 'url', 'abstract']
        widgets = {
            'abstract': forms.Textarea(attrs={'rows': 3}),
            'year': forms.NumberInput(attrs={'min': 1950, 'max': 2100}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _apply_input_css(self)
