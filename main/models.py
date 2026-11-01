import datetime
from django.db import models
from django.contrib.auth.models import User

class Form(models.Model):
    FIELD_TYPE_CHOICES = [
        ('text', 'Short Answer'),
        ('textarea', 'Paragraph'),
        ('email', 'Email'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('select', 'Dropdown'),
        ('radio', 'Multiple Choice'),
        ('checkbox', 'Checkboxes'),
        ('file', 'File Upload'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    accepting_responses = models.BooleanField(default=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='forms')

    def __str__(self):
        return self.title

    class Meta:
        ordering = ['-created_at']


class FormSection(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='sections')
    title = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.form.title} - {self.title or 'Untitled Section'}"

    class Meta:
        ordering = ['order']


class FormField(models.Model):
    FIELD_TYPE_CHOICES = [
        ('text', 'Short Answer'),
        ('textarea', 'Paragraph'),
        ('email', 'Email'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('select', 'Dropdown'),
        ('radio', 'Multiple Choice'),
        ('checkbox', 'Checkboxes'),
        ('file', 'File Upload'),
    ]

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='fields')
    section = models.ForeignKey(FormSection, on_delete=models.CASCADE, related_name='fields', null=True, blank=True)
    label = models.CharField(max_length=200)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPE_CHOICES)
    is_required = models.BooleanField(default=False)
    placeholder = models.CharField(max_length=200, blank=True)
    options = models.TextField(blank=True, help_text='Comma-separated options for select/radio/checkbox')
    order = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.form.title} - {self.label}"

    class Meta:
        ordering = ['order']


class FormSubmission(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('selected', 'Selected (staged)'), ('admitted', 'Admitted')]

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='submissions')
    submitted_at = models.DateTimeField(auto_now_add=True)
    applicant_name = models.CharField(max_length=200, blank=True)
    applicant_email = models.EmailField(blank=True)
    applicant_phone = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='applications')

    def __str__(self):
        return f"{self.form.title} - {self.applicant_name}"

    class Meta:
        ordering = ['-submitted_at']


class FormAnswer(models.Model):
    submission = models.ForeignKey(FormSubmission, on_delete=models.CASCADE, related_name='answers')
    field = models.ForeignKey(FormField, on_delete=models.CASCADE)
    answer = models.TextField()

    def __str__(self):
        return f"{self.field.label}: {self.answer[:50]}"



class EmailLog(models.Model):
    KIND_CHOICES = [('acknowledgment', 'Application received'), ('shortlist', 'Shortlisted'), ('credentials', 'Account credentials'), ('certificate', 'Certificate')]
    STATUS_CHOICES = [('sent', 'Sent'), ('failed', 'Failed')]

    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='email_logs')
    submission = models.ForeignKey(FormSubmission, on_delete=models.SET_NULL, null=True, blank=True, related_name='email_logs')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    to_email = models.EmailField()
    subject = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.get_kind_display()} -> {self.to_email} ({self.status})'


class GridConfig(models.Model):
    form = models.OneToOneField(Form, on_delete=models.CASCADE, related_name='grid_config')
    start_date = models.DateField()
    weeks = models.PositiveSmallIntegerField(default=1)
    work_days = models.CharField(max_length=20, default='5,6,0,1,2,3')
    day_plans = models.JSONField(default=dict, blank=True)

    @property
    def work_day_list(self):
        return [int(x) for x in self.work_days.split(',') if x != '']


class ProgramSession(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='sessions')
    slot_number = models.PositiveSmallIntegerField(null=True, blank=True)
    facilitator = models.CharField(max_length=200, blank=True)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    date = models.DateField()
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ['date', 'start_time', 'id']

    def __str__(self):
        return f'{self.title} ({self.date})'


class Attendance(models.Model):
    STATUS_CHOICES = [('present', 'Present'), ('late', 'Late'), ('excused', 'Excused'), ('absent', 'Absent')]

    session = models.ForeignKey(ProgramSession, on_delete=models.CASCADE, related_name='attendance')
    submission = models.ForeignKey(FormSubmission, on_delete=models.CASCADE, related_name='attendance')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('session', 'submission')


class Announcement(models.Model):
    form = models.ForeignKey(Form, on_delete=models.CASCADE, related_name='announcements')
    title = models.CharField(max_length=200)
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class CertificateSetting(models.Model):
    form = models.OneToOneField(Form, on_delete=models.CASCADE, related_name='certificate')
    published = models.BooleanField(default=False, help_text='Admitted applicants can only see their certificate when this is on.')
    title = models.CharField(max_length=120, default='Certificate of Participation')
    workshop_text = models.CharField(max_length=300, default='has successfully participated in a 8 days workshop held in September 2026')
    program_title = models.CharField(max_length=300, blank=True, help_text='Shown in quotes. Defaults to the form title.')
    description = models.TextField(default='This workshop was organized by Hargeisa Debates Organization in partnership with Heinrich Böll Stiftung and held at the Hargeisa Debates Office, Hargeisa Somaliland.')
    issue_date = models.DateField(null=True, blank=True)
    signer1_title = models.CharField(max_length=100, default='HBS Program Coordinator')
    signer2_title = models.CharField(max_length=100, default='HDO Head of Programs')
    number_prefix = models.CharField(max_length=30, default='HDO-HBS')
    signer1_signature = models.FileField(upload_to='signatures/', blank=True, help_text='Signature image shown above the first signer title (PNG with transparent background works best).')
    signer2_signature = models.FileField(upload_to='signatures/', blank=True, help_text='Signature image shown above the second signer title.')

    def __str__(self):
        return f'Certificate settings - {self.form.title}'
