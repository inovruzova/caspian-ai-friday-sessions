from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone


# Custom manager because we're using email instead of username
class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email is required')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    username = None  # Remove username field entirely
    email = models.EmailField(unique=True)
    department = models.CharField(max_length=100)
    has_no_show_penalty = models.BooleanField(default=False)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['first_name', 'last_name', 'department']

    objects = UserManager()

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.email})"
    
class DepartmentMember(models.Model):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200)

    class Meta:
        ordering = ['full_name']

    def __str__(self):
        return f"{self.full_name} ({self.email})"
    
class SessionApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    TIME_CHOICES = [
        ('10:00', '10:00 AM'),
        ('11:00', '11:00 AM'),
        ('14:00', '2:00 PM'),
        ('15:00', '3:00 PM'),
        ('16:00', '4:00 PM'),
    ]
    
    submitted_by = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='applications'
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    session_date = models.DateField()
    preferred_times = models.CharField(
        max_length=100,
        help_text='Comma-separated times, e.g. 10:00,14:00,16:00'
    )
    language = models.CharField(max_length=100, default='English')
    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES, default='pending'
    )
    rejection_reason = models.TextField(blank=True, default='')
    submitted_at = models.DateTimeField(auto_now_add=True)
    no_show = models.BooleanField(default=False)

    class Meta:
        ordering = ['submitted_at']

    def __str__(self):
        return f"{self.title} - {self.session_date} ({self.status})"

class ApplicationSpeaker(models.Model):
    application = models.ForeignKey(
        SessionApplication, on_delete=models.CASCADE, related_name='speakers'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='speaking_applications',
        null=True, blank=True
    )
    speaker_name = models.CharField(max_length=200, blank=True)
    speaker_email = models.EmailField(blank=True)
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ['application', 'speaker_email']

    def __str__(self):
        return f"{self.get_display_name()} - {self.application.title}"

    def get_display_name(self):
        if self.user:
            return self.user.get_full_name()
        return self.speaker_name or self.speaker_email


class ApprovedSession(models.Model):
    application = models.OneToOneField(
        SessionApplication, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='approved_session'
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField(unique=True)
    time = models.CharField(max_length=10, blank=True)
    speaker_names = models.CharField(max_length=300, blank=True, help_text='Used for manually added sessions without a linked application.')
    language = models.CharField(max_length=100, blank=True, default='English')
    presentation_link = models.URLField(blank=True)
    recording_link = models.URLField(blank=True)

    class Meta:
        ordering = ['date']

    def __str__(self):
        return f"{self.title} - {self.date}"

    def get_speaker_display(self):
        if self.application:
            speakers = self.application.speakers.all()
            return ', '.join([s.get_display_name() for s in speakers])
        return self.speaker_names or 'TBA'


class VotingLink(models.Model):
    session_title = models.CharField(max_length=200)
    session_date = models.DateField()
    speaker_names = models.CharField(max_length=300)
    voting_url = models.URLField()
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.session_title} ({'Active' if self.is_active else 'Inactive'})"


class Notification(models.Model):
    recipient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='notifications'
    )
    message = models.CharField(max_length=500)
    link = models.CharField(max_length=200, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']  # Newest first

    def __str__(self):
        return f"To {self.recipient.email}: {self.message[:50]}"