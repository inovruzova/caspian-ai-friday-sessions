from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, SessionApplication, ApplicationSpeaker,
    ApprovedSession, VotingLink, Notification, DepartmentMember
)


# ──────────────────────────────────────────────
# USER ADMIN
# ──────────────────────────────────────────────
class CustomUserAdmin(BaseUserAdmin):
    model = User
    list_display = ('email', 'first_name', 'last_name', 'department', 'has_no_show_penalty', 'is_staff')
    list_filter = ('department', 'is_staff', 'has_no_show_penalty')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)

    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal Info', {'fields': ('first_name', 'last_name', 'department')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser')}),
        ('Session Info', {'fields': ('has_no_show_penalty',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'first_name', 'last_name', 'department', 'password1', 'password2'),
        }),
    )


admin.site.register(User, CustomUserAdmin)


# ──────────────────────────────────────────────
# SESSION APPLICATION ADMIN
# ──────────────────────────────────────────────
class ApplicationSpeakerInline(admin.TabularInline):
    model = ApplicationSpeaker
    extra = 0
    readonly_fields = ('user', 'is_primary')


class SessionApplicationAdmin(admin.ModelAdmin):
    list_display = ('title', 'session_date', 'preferred_times', 'status', 'submitted_at', 'no_show', 'get_speakers')
    list_filter = ('status', 'session_date', 'no_show')
    search_fields = ('title', 'submitted_by__email')
    readonly_fields = ('submitted_by', 'submitted_at')
    inlines = [ApplicationSpeakerInline]
    fields = ('submitted_by', 'title', 'description', 'session_date', 'preferred_times', 'status', 'rejection_reason', 'submitted_at', 'no_show')

    actions = ['approve_applications', 'reject_applications', 'flag_no_show']

    def get_speakers(self, obj):
        speakers = obj.speakers.all()
        return ', '.join([s.get_display_name() for s in speakers])
    get_speakers.short_description = 'Speakers'

    def approve_applications(self, request, queryset):
        queryset = queryset.filter(status='pending')
        if not queryset.exists():
            self.message_user(request, "No pending applications in selection.", level='warning')
            return

        # Build the time choices lookup from the model
        time_labels = dict(SessionApplication.TIME_CHOICES)

        if 'apply_approval' in request.POST:
            count = 0
            for application in queryset:
                if ApprovedSession.objects.filter(date=application.session_date).exists():
                    self.message_user(
                        request,
                        f"Cannot approve '{application.title}' — date {application.session_date} already has an approved session.",
                        level='error'
                    )
                    continue

                selected_time = request.POST.get(f'time_{application.pk}', '')
                if not selected_time:
                    selected_time = application.preferred_times.split(',')[0].strip()

                speakers = application.speakers.all()
                speaker_names = ', '.join([s.get_display_name() for s in speakers])

                ApprovedSession.objects.create(
                    application=application,
                    title=application.title,
                    description=application.description,
                    date=application.session_date,
                    time=selected_time,
                    speaker_names=speaker_names,
                    language=application.language,
                )

                application.status = 'approved'
                application.save()

                for speaker in speakers:
                    if speaker.user:
                        Notification.objects.create(
                            recipient=speaker.user,
                            message=f"✅ Your session '{application.title}' on {application.session_date} at {time_labels.get(selected_time, selected_time)} has been approved!",
                            link='/sessions/'
                        )
                count += 1

            self.message_user(request, f"{count} application(s) approved.")
            return

        # Show intermediate page with time selection
        from django.template.response import TemplateResponse

        applications_with_times = []
        for app in queryset:
            raw_times = [t.strip() for t in app.preferred_times.split(',') if t.strip()]
            time_choices = [(t, time_labels.get(t, t)) for t in raw_times]
            speakers = app.speakers.all()
            applications_with_times.append({
                'application': app,
                'time_choices': time_choices,
                'speaker_names': ', '.join([s.get_display_name() for s in speakers]),
            })

        context = {
            'title': 'Approve Applications',
            'queryset': queryset,
            'applications_with_times': applications_with_times,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'opts': self.model._meta,
        }
        return TemplateResponse(request, 'admin/approve_intermediate.html', context)
    approve_applications.short_description = "Approve selected applications"

    def reject_applications(self, request, queryset):
        queryset = queryset.filter(status='pending')
        if not queryset.exists():
            self.message_user(request, "No pending applications in selection.", level='warning')
            return

        if 'apply_rejection' in request.POST:
            reason = request.POST.get('rejection_reason', '').strip()
            count = 0
            for application in queryset:
                application.status = 'rejected'
                application.rejection_reason = reason
                application.save()

                for speaker in application.speakers.all():
                    if speaker.user:
                        reason_text = f" Reason: {reason}" if reason else ""
                        Notification.objects.create(
                            recipient=speaker.user,
                            message=f"❌ Your session '{application.title}' on {application.session_date} has been rejected.{reason_text}",
                            link='/apply/'
                        )
                count += 1

            self.message_user(request, f"{count} application(s) rejected.")
            return

        from django.template.response import TemplateResponse
        context = {
            'title': 'Reject Applications',
            'queryset': queryset,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
            'opts': self.model._meta,
        }
        return TemplateResponse(request, 'admin/reject_intermediate.html', context)
    reject_applications.short_description = "Reject selected applications"

    def flag_no_show(self, request, queryset):
        for application in queryset.filter(status='approved'):
            application.no_show = True
            application.save()

            for speaker in application.speakers.all():
                if speaker.user:
                    speaker.user.has_no_show_penalty = True
                    speaker.user.save()

                    Notification.objects.create(
                        recipient=speaker.user,
                        message=f"⚠️ You have been marked as a no-show for '{application.title}'. Your future applications will have reduced priority.",
                        link='/sessions/'
                    )

            self.message_user(request, f"No-show flagged for '{application.title}'. Penalty applied to registered speaker(s).")
    flag_no_show.short_description = "Flag as no-show (applies penalty)"


admin.site.register(SessionApplication, SessionApplicationAdmin)


# ──────────────────────────────────────────────
# APPROVED SESSION ADMIN
# ──────────────────────────────────────────────
class ApprovedSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'date', 'time', 'speaker_names', 'presentation_link', 'recording_link')
    list_filter = ('date',)
    search_fields = ('title',)
    

admin.site.register(ApprovedSession, ApprovedSessionAdmin)


# ──────────────────────────────────────────────
# VOTING LINK ADMIN
# ──────────────────────────────────────────────
class VotingLinkAdmin(admin.ModelAdmin):
    list_display = ('session_title', 'session_date', 'speaker_names', 'is_active')
    list_filter = ('is_active',)


admin.site.register(VotingLink, VotingLinkAdmin)


# ──────────────────────────────────────────────
# NOTIFICATION ADMIN
# ──────────────────────────────────────────────
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'message', 'is_read', 'created_at')
    list_filter = ('is_read',)
    readonly_fields = ('recipient', 'message', 'link', 'is_read', 'created_at')


admin.site.register(Notification, NotificationAdmin)


# ──────────────────────────────────────────────
# DEPARTMENT MEMBER ADMIN
# ──────────────────────────────────────────────
class DepartmentMemberAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email')
    search_fields = ('full_name', 'email')
    ordering = ('full_name',)

admin.site.register(DepartmentMember, DepartmentMemberAdmin)