from django import forms

from accounts.forms import INPUT_CSS
from .models import Manuscript, Review, ReviewRecommendation


def _css(form):
    for field in form.fields.values():
        w = field.widget
        if isinstance(w, (forms.FileInput, forms.CheckboxInput)):
            continue
        existing = w.attrs.get('class', '')
        w.attrs['class'] = (existing + ' ' + INPUT_CSS).strip()


class ManuscriptSubmitForm(forms.ModelForm):
    class Meta:
        model = Manuscript
        fields = ['journal', 'title', 'abstract', 'keywords', 'file']
        widgets = {
            'abstract': forms.Textarea(attrs={'rows': 6}),
            'keywords': forms.TextInput(attrs={'placeholder': 'e.g. machine learning, protein folding, …'}),
        }

    def __init__(self, *args, journal=None, **kwargs):
        super().__init__(*args, **kwargs)
        if journal:
            self.fields['journal'].initial = journal
            self.fields['journal'].widget = forms.HiddenInput()
        _css(self)


class RevisionForm(forms.Form):
    file = forms.FileField(label='Revised manuscript (PDF)')
    author_note = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4}),
        label='Response to reviewers',
        help_text='Briefly describe changes made.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _css(self)


class AssignReviewerForm(forms.Form):
    reviewer = forms.ModelChoiceField(
        queryset=None,
        label='Assign reviewer',
        help_text='Only members with Reviewer or Professor role are shown.',
    )
    due_date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        required=False,
        label='Due date (optional)',
    )

    def __init__(self, *args, manuscript=None, **kwargs):
        super().__init__(*args, **kwargs)
        from accounts.models import Role, User
        already = manuscript.reviews.values_list('reviewer_id', flat=True) if manuscript else []
        self.fields['reviewer'].queryset = (
            User.objects
            .filter(role__in=[Role.PROFESSOR, Role.REVIEWER])
            .exclude(pk__in=already)
            .order_by('last_name', 'first_name')
        )
        _css(self)


class ReviewReportForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['recommendation', 'report', 'comments_to_author']
        widgets = {
            'report': forms.Textarea(attrs={'rows': 8}),
            'comments_to_author': forms.Textarea(attrs={'rows': 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['recommendation'].choices = [('', '— Select —')] + list(
            ReviewRecommendation.choices
        )
        _css(self)


class EditorDecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=[
        ('', '— Select decision —'),
        ('accepted', 'Accept'),
        ('revision_required', 'Request revision'),
        ('rejected', 'Reject'),
    ])
    editor_note = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 5}),
        label='Note to author',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _css(self)
