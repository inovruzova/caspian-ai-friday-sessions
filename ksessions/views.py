from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone
from .forms import RegistrationForm, SessionApplicationForm
from .models import (
    SessionApplication, ApplicationSpeaker, ApprovedSession,
    VotingLink, Notification
)
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

User = get_user_model()


# ──────────────────────────────────────────────
# AUTH VIEWS
# ──────────────────────────────────────────────
def register_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()

            # Link any existing co-speaker records to this new account
            linked = ApplicationSpeaker.objects.filter(
                speaker_email=user.email, user__isnull=True
            )
            linked.update(user=user)

            # Send catch-up notifications for applications they missed
            for speaker_record in ApplicationSpeaker.objects.filter(user=user):
                app = speaker_record.application
                if app.status == 'approved':
                    Notification.objects.create(
                        recipient=user,
                        message=f"✅ You are a co-speaker for '{app.title}' on {app.session_date}, which has been approved!",
                        link='/sessions/'
                    )
                elif app.status == 'rejected':
                    reason_text = f" Reason: {app.rejection_reason}" if app.rejection_reason else ""
                    Notification.objects.create(
                        recipient=user,
                        message=f"❌ The session '{app.title}' on {app.session_date} (where you were a co-speaker) was rejected.{reason_text}",
                        link='/apply/'
                    )

            messages.success(request, 'Account created successfully! Please sign in.')
            return redirect('login')
    else:
        form = RegistrationForm()

    return render(request, 'registration/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')

    if request.method == 'POST':
        email = request.POST.get('email')
        password = request.POST.get('password')
        user = authenticate(request, username=email, password=password)

        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', '')
            if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                next_url = 'home'
            return redirect(next_url)

        else:
            messages.error(request, 'Invalid email or password.')

    return render(request, 'registration/login.html')


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, 'You have been signed out.')
    return redirect('home')


# ──────────────────────────────────────────────
# HOME PAGE
# ──────────────────────────────────────────────
def home_view(request):
    today = timezone.now().date()
    active_votes = VotingLink.objects.filter(is_active=True)
    next_session = ApprovedSession.objects.filter(date__gte=today).first()

    context = {
        'active_votes': active_votes,
        'next_session': next_session,
    }
    return render(request, 'home.html', context)


# ──────────────────────────────────────────────
# SESSIONS PAGE
# ──────────────────────────────────────────────
def sessions_view(request):
    today = timezone.now().date()
    tab = request.GET.get('tab', 'upcoming')

    upcoming_sessions = ApprovedSession.objects.filter(date__gte=today)
    past_sessions = ApprovedSession.objects.filter(date__lt=today).order_by('-date')

    pending_applications = []
    if request.user.is_authenticated:
        pending_applications = SessionApplication.objects.filter(
            status='pending',
            session_date__gte=today,
            speakers__user=request.user,
        ).distinct()

    context = {
        'upcoming_sessions': upcoming_sessions,
        'past_sessions': past_sessions,
        'pending_applications': pending_applications,
        'tab': tab,
    }
    return render(request, 'sessions.html', context)


# ──────────────────────────────────────────────
# APPLY PAGE
# ──────────────────────────────────────────────
@login_required(login_url='login')
def apply_view(request):
    if request.method == 'POST':
        form = SessionApplicationForm(request.POST, current_user=request.user)
        if form.is_valid():
            application = SessionApplication.objects.create(
                submitted_by=request.user,
                title=form.cleaned_data['title'],
                description=form.cleaned_data['description'],
                session_date=form.cleaned_data['session_date'],
                preferred_times=','.join(form.cleaned_data['preferred_times']),
                language=form.cleaned_data['language'],
                status='pending',
            )

            # Primary speaker (logged-in user)
            ApplicationSpeaker.objects.create(
                application=application,
                user=request.user,
                speaker_name=request.user.get_full_name(),
                speaker_email=request.user.email,
                is_primary=True,
            )

            # Co-speakers from DepartmentMember list
            co_speakers = form.cleaned_data.get('co_speakers', [])
            for member in co_speakers:
                # Check if this member has a registered account
                try:
                    user_obj = User.objects.get(email=member.email)
                except User.DoesNotExist:
                    user_obj = None

                ApplicationSpeaker.objects.create(
                    application=application,
                    user=user_obj,
                    speaker_name=member.full_name,
                    speaker_email=member.email,
                    is_primary=False,
                )

            # Notify admins
            admins = User.objects.filter(is_staff=True)
            all_names = [request.user.get_full_name()] + [m.full_name for m in co_speakers]
            speaker_names = ', '.join(all_names)

            for admin_user in admins:
                Notification.objects.create(
                    recipient=admin_user,
                    message=f"New session application: '{application.title}' by {speaker_names} for {application.session_date}.",
                    link='/admin/ksessions/sessionapplication/',
                )

            messages.success(
                request,
                'Your application has been submitted successfully! '
                'You will receive a response (approval or rejection) within 3 days.'
            )            
            
            return redirect('apply')
    else:
        form = SessionApplicationForm(current_user=request.user)

    return render(request, 'apply.html', {'form': form})


# ──────────────────────────────────────────────
# RULES PAGE
# ──────────────────────────────────────────────
def rules_view(request):
    active_votes = VotingLink.objects.filter(is_active=True)
    return render(request, 'rules.html', {'active_votes': active_votes})


# ──────────────────────────────────────────────
# NOTIFICATIONS PAGE
# ──────────────────────────────────────────────
@login_required(login_url='login')
def notifications_view(request):
    notifications = request.user.notifications.all()

    # Mark all as read when the page is visited
    request.user.notifications.filter(is_read=False).update(is_read=True)

    return render(request, 'notifications.html', {'notifications': notifications})