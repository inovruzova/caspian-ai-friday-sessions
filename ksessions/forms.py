from django import forms
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta, date
from .models import SessionApplication, ApplicationSpeaker, ApprovedSession, DepartmentMember
from django.contrib.auth.password_validation import validate_password

User = get_user_model()


class RegistrationForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'department', 'password']

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password and password != confirm_password:
            raise forms.ValidationError("Passwords do not match.")

        if password:
            validate_password(password)

        return cleaned_data

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])  # Hash the password
        if commit:
            user.save()
        return user
    

class SessionApplicationForm(forms.Form):
    TIME_CHOICES = [
        ('10:00', '10:00 AM'),
        ('11:00', '11:00 AM'),
        ('14:00', '2:00 PM'),
        ('15:00', '3:00 PM'),
        ('16:00', '4:00 PM'),
    ]

    PROGRAM_START = date(2026, 3, 1)
    PROGRAM_END = date(2026, 5, 22)

    title = forms.CharField(max_length=200)
    description = forms.CharField(widget=forms.Textarea(attrs={'rows': 4}))
    session_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    preferred_times = forms.MultipleChoiceField(
        choices=TIME_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        help_text='Select one or more preferred times.'
    )
    co_speakers = forms.ModelMultipleChoiceField(
        queryset=DepartmentMember.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={
            'id': 'co_speakers',
        }),
        help_text='Search and select co-speakers.'
    )
    language = forms.CharField(
        max_length=100,
        initial='English',
        widget=forms.TextInput(attrs={'placeholder': 'e.g. English, Azerbaijani'}),
    )

    def __init__(self, *args, **kwargs):
        self.current_user = kwargs.pop('current_user', None)
        super().__init__(*args, **kwargs)
        # Exclude the current user from co-speaker list if they exist in DepartmentMember
        if self.current_user:
            self.fields['co_speakers'].queryset = DepartmentMember.objects.exclude(
                email=self.current_user.email
            )

    def clean_session_date(self):
        session_date = self.cleaned_data['session_date']
        today = timezone.now().date()

        if session_date < self.PROGRAM_START:
            raise forms.ValidationError('Session date must be within the program period (March–May 2026).')

        if session_date > self.PROGRAM_END:
            raise forms.ValidationError(
                f'The application deadline has passed. All sessions must be on or before {self.PROGRAM_END.strftime("%B %d, %Y")}.'
            )

        deadline = session_date - timedelta(days=3)
        if today > deadline:
            raise forms.ValidationError(
                f'Applications must be submitted at least 3 days before the session date. '
                f'The deadline for {session_date.strftime("%B %d, %Y")} was {deadline.strftime("%B %d, %Y")}.'
            )

        if ApprovedSession.objects.filter(date=session_date).exists():
            raise forms.ValidationError('This date already has an approved session. Please choose another date.')

        return session_date