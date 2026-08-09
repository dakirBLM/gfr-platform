from django import forms

from accounts.forms import INPUT_CSS
from accounts.models import Role, User
from .models import Milestone, Project, ProjectApplication, ProjectSection, Task


def _css(form):
    for field in form.fields.values():
        w = field.widget
        if isinstance(w, (forms.CheckboxInput, forms.FileInput, forms.MultipleHiddenInput)):
            continue
        existing = w.attrs.get('class', '')
        w.attrs['class'] = (existing + ' ' + INPUT_CSS).strip()


class ProjectForm(forms.ModelForm):
    # Optional pre-selected members at creation time.
    initial_members = forms.ModelMultipleChoiceField(
        queryset=User.objects.filter(
            role__in=[Role.RESEARCHER, Role.PROFESSOR, Role.REVIEWER,
                      Role.EDITOR, Role.PROJECT_MANAGER]
        ).order_by('last_name', 'first_name'),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Invite initial members',
        help_text='These researchers will be added as members when the project is created.',
    )

    class Meta:
        model = Project
        fields = [
            'title', 'description', 'objectives',
            'application_question', 'status', 'funding_status', 'start_date', 'end_date',
        ]
        widgets = {
            'description': forms.Textarea(attrs={'rows': 5}),
            'objectives': forms.Textarea(attrs={'rows': 4}),
            'start_date': forms.DateInput(attrs={'type': 'date'}),
            'end_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, exclude_user=None, include_initial_members=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not include_initial_members:
            self.fields.pop('initial_members')
            _css(self)
            return
        if exclude_user:
            self.fields['initial_members'].queryset = (
                self.fields['initial_members'].queryset.exclude(pk=exclude_user.pk)
            )
        _css(self)


class ProjectSectionForm(forms.ModelForm):
    class Meta:
        model = ProjectSection
        fields = ['title', 'description', 'order']
        widgets = {'description': forms.Textarea(attrs={'rows': 2})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _css(self)


class AddMemberForm(forms.Form):
    """Manager adds a single member to an existing project by searching username."""
    user = forms.ModelChoiceField(
        queryset=User.objects.filter(
            role__in=[Role.RESEARCHER, Role.PROFESSOR, Role.REVIEWER,
                      Role.EDITOR, Role.PROJECT_MANAGER]
        ).order_by('last_name', 'first_name'),
        label='Add member',
        help_text='Only Researcher-level and above can be added.',
    )
    role = forms.ChoiceField(
        choices=[('member', 'Member'), ('manager', 'Manager'), ('observer', 'Observer')],
        initial='member',
    )

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            existing = project.members.values_list('pk', flat=True)
            self.fields['user'].queryset = (
                self.fields['user'].queryset.exclude(pk__in=existing)
            )
        _css(self)


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ['section', 'title', 'description', 'assigned_to', 'priority', 'due_date', 'assignment_file']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, project=None, **kwargs):
        super().__init__(*args, **kwargs)
        if project:
            self.fields['assigned_to'].queryset = project.members.all()
            self.fields['section'].queryset = project.sections.all()
        self.fields['assigned_to'].required = False
        _css(self)


class ProjectApplicationForm(forms.ModelForm):
    class Meta:
        model = ProjectApplication
        fields = ['message', 'answer']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Briefly introduce your relevant experience.'}),
            'answer': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Explain how your skills suit this project.'}),
        }
        labels = {
            'message': 'Application message',
            'answer': 'Suitability answer',
        }

    def __init__(self, *args, question='', **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['answer'].required = bool(question)
        if question:
            self.fields['answer'].label = question
            self.fields['answer'].help_text = 'This answer will be visible only to the project guarantor.'
        else:
            self.fields['answer'].widget = forms.HiddenInput()
        _css(self)


class TaskSubmitForm(forms.Form):
    """Member submits a completed task to the manager for review."""
    submission_note = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        label='Work summary',
        help_text='Briefly describe what you did and any relevant notes for the manager.',
    )
    submission_file = forms.FileField(
        required=False,
        label='Attachment (optional)',
        help_text='PDF, Word, image, or any relevant file. Max 20 MB.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _css(self)

    def clean_submission_file(self):
        f = self.cleaned_data.get('submission_file')
        if f and hasattr(f, 'size') and f.size > 20 * 1024 * 1024:
            raise forms.ValidationError('File is too large. Please keep it under 20 MB.')
        return f


class TaskReviewForm(forms.Form):
    """Manager approves or rejects a submitted task."""
    decision = forms.ChoiceField(choices=[
        ('approved', 'Approve — mark as done'),
        ('rejected', 'Request revision'),
    ])
    manager_feedback = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        required=False,
        label='Feedback to member',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _css(self)


class MilestoneForm(forms.ModelForm):
    class Meta:
        model = Milestone
        fields = ['title', 'description', 'due_date']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _css(self)
