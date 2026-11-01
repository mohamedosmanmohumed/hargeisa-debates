from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from main.models import Form, FormSection, FormField

TITLE = 'Civic Lab Cohort 4'
DESCRIPTION = ('Application form for Civic Lab Cohort 4, open to fresh graduates and senior '
               'university students. Please answer all questions honestly and completely.')

YES_NO = 'Yes,No'
UNIVERSITIES = 'University of Hargeisa,Admas University,Amoud University,Edna Adan University,Nugal University,Gollis University,Other'

SECTIONS = [
    ('Personal Information', 'Tell us about yourself.', [
        ('text', 'Full Name', True, '', ''),
        ('email', 'Email Address', True, '', ''),
        ('text', 'Phone Number', True, 'e.g. +252 63 XXXXXXX', ''),
        ('date', 'Date of Birth', True, '', ''),
        ('radio', 'Gender', True, '', 'Female,Male,Prefer not to say'),
        ('text', 'City / District of Residence', True, '', ''),
    ]),
    ('Education Background', 'Civic Lab Cohort 4 is for fresh graduates and senior university students.', [
        ('radio', 'Current Status', True, '', 'Senior student (final year),Fresh graduate (graduated within the last 2 years)'),
        ('select', 'University', True, '', UNIVERSITIES),
        ('text', 'If you selected Other, write your university name', False, '', ''),
        ('text', 'Faculty / Department', True, '', ''),
        ('text', 'Field of Study / Major', True, '', ''),
        ('select', 'Expected or Actual Graduation Year', True, '', '2024,2025,2026,2027'),
        ('text', 'Current GPA (if available)', False, 'e.g. 3.4', ''),
    ]),
    ('Civic Interest & Motivation', 'Help us understand why you want to join.', [
        ('textarea', 'Why do you want to join Civic Lab Cohort 4?', True, '', ''),
        ('textarea', 'What community or civic problem do you care about most, and why?', True, '', ''),
        ('checkbox', 'Which areas interest you most?', True, '',
         'Governance and Policy,Youth Empowerment,Education,Health,Environment and Climate,Technology and Innovation,Entrepreneurship,Human Rights and Gender,Peacebuilding'),
        ('textarea', 'What do you hope to gain from the program?', True, '', ''),
        ('textarea', 'Where do you see yourself contributing to your community in the next 5 years?', False, '', ''),
    ]),
    ('Experience & Skills', 'Past experience is not required, but we would like to know more.', [
        ('radio', 'Have you participated in any volunteering or civic activity before?', True, '', YES_NO),
        ('textarea', 'If yes, briefly describe your experience', False, '', ''),
        ('checkbox', 'Which skills do you have?', False, '',
         'Public Speaking,Writing,Research,Leadership,Teamwork,Digital Skills,Project Management,Social Media,Data Analysis'),
        ('radio', 'English Proficiency', True, '', 'Basic,Intermediate,Advanced,Fluent'),
        ('file', 'Upload your CV (optional)', False, '', ''),
    ]),
    ('Commitment & Consent', 'Please confirm your availability.', [
        ('radio', 'Can you commit to attending all sessions of the program?', True, '', YES_NO),
        ('radio', 'Do you have access to a laptop or smartphone and internet?', True, '', YES_NO),
        ('select', 'How did you hear about Civic Lab?', True, '', 'Social Media,University,Friend or Family,Previous Cohort Participant,Other'),
        ('checkbox', 'Declaration', True, '', 'I confirm that the information provided is true and accurate'),
    ]),
]


class Command(BaseCommand):
    help = 'Create the Civic Lab Cohort 4 application form with all sections and questions.'

    def add_arguments(self, parser):
        parser.add_argument('--username', help='Owner of the form (defaults to first superuser)')

    def handle(self, *args, **opts):
        users = User.objects.filter(username=opts['username']) if opts['username'] else User.objects.order_by('-is_superuser', 'id')
        user = users.first()
        if not user:
            raise CommandError('No user found. Create one with: python manage.py createsuperuser')
        if Form.objects.filter(title=TITLE, created_by=user).exists():
            raise CommandError(f'"{TITLE}" already exists for {user.username}.')
        form = Form.objects.create(title=TITLE, description=DESCRIPTION, created_by=user)
        order = 0
        for s_order, (title, desc, fields) in enumerate(SECTIONS, 1):
            section = FormSection.objects.create(form=form, title=title, description=desc, order=s_order)
            for ftype, label, req, ph, opts_ in fields:
                order += 1
                FormField.objects.create(form=form, section=section, label=label, field_type=ftype,
                                         is_required=req, placeholder=ph, options=opts_, order=order)
        self.stdout.write(self.style.SUCCESS(f'Created form id={form.id} for {user.username}: /forms/{form.id}/view/'))
