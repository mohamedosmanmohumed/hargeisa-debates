import random
from datetime import date, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from main.models import Form, FormAnswer, FormSubmission

TEST_DOMAIN = '@example.test'
FIRST = ['Ahmed', 'Mohamed', 'Abdi', 'Hodan', 'Fartun', 'Ayaan', 'Nimco', 'Hassan', 'Ismail', 'Khadar', 'Sagal', 'Ilhan',
         'Yusuf', 'Samsam', 'Liban', 'Mulki', 'Abdirahman', 'Deeqa', 'Faysal', 'Hibo', 'Zamzam', 'Guled', 'Najma', 'Omar']
LAST = ['Ali', 'Hussein', 'Jama', 'Ibrahim', 'Warsame', 'Abdillahi', 'Farah', 'Osman', 'Duale', 'Yusuf', 'Mohamud', 'Adan',
        'Egal', 'Dirir', 'Ahmed', 'Hersi', 'Nur', 'Said', 'Elmi', 'Gedi']
TEXT = ['Interested in community development.', 'I want to build skills and serve my community.',
        'Passionate about youth leadership and civic engagement.', 'I want to learn about policy and governance.']


class Command(BaseCommand):
    help = 'Create fake applicants (marked with @example.test emails) to test filters and shortlisting.'

    def add_arguments(self, parser):
        parser.add_argument('--form-id', type=int, help='Form id (defaults to the Civic Lab Cohort 4 form)')
        parser.add_argument('--count', type=int, default=450)
        parser.add_argument('--clear', action='store_true', help='Delete previously seeded test applicants and exit')
        parser.add_argument('--seed', type=int, default=4)

    def handle(self, *args, **opts):
        form = Form.objects.filter(id=opts['form_id']).first() if opts['form_id'] else Form.objects.filter(title='Civic Lab Cohort 4').first()
        if not form:
            raise CommandError('Form not found.')
        test_subs = form.submissions.filter(applicant_email__endswith=TEST_DOMAIN)
        if opts['clear']:
            n = test_subs.count()
            test_subs.delete()
            self.stdout.write(self.style.SUCCESS(f'Deleted {n} test applicants.'))
            return

        random.seed(opts['seed'])
        fields = list(form.fields.all())
        with transaction.atomic():
            for i in range(opts['count']):
                name = f'{random.choice(FIRST)} {random.choice(LAST)}'
                email = f'test{i + 1}{TEST_DOMAIN}'
                phone = f'+25263{random.randint(1000000, 9999999)}'
                answers = []
                for f in fields:
                    label, opts_ = f.label.lower(), [o.strip() for o in f.options.split(',') if o.strip()]
                    if f.field_type == 'file':
                        value = ''
                    elif f.field_type == 'email':
                        value = email
                    elif f.field_type == 'date':
                        value = (date(1998, 1, 1) + timedelta(days=random.randint(0, 365 * 8))).isoformat()
                    elif f.field_type in ('select', 'radio'):
                        value = random.choice(opts_)
                    elif f.field_type == 'checkbox':
                        value = ', '.join(random.sample(opts_, random.randint(1, min(3, len(opts_)))))
                    elif 'full name' in label:
                        value = name
                    elif 'phone' in label:
                        value = phone
                    elif 'gpa' in label:
                        value = f'{random.uniform(2.0, 4.0):.1f}'
                    elif f.field_type == 'textarea':
                        value = random.choice(TEXT)
                    else:
                        value = random.choice(['Hargeisa', 'Borama', 'Burao', 'Berbera', 'Gabiley']) if 'city' in label else 'N/A'
                    answers.append((f, value))
                sub = FormSubmission.objects.create(form=form, applicant_name=name, applicant_email=email, applicant_phone=phone)
                FormAnswer.objects.bulk_create(FormAnswer(submission=sub, field=f, answer=v) for f, v in answers)
        self.stdout.write(self.style.SUCCESS(f'Created {opts["count"]} test applicants for "{form.title}" (id={form.id}). Total: {form.submissions.count()}'))
