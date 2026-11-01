import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Form, FormField, FormSubmission

TMP_MEDIA = tempfile.mkdtemp()


@override_settings(MEDIA_ROOT=TMP_MEDIA)
class RegistrationFlowTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TMP_MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user('staff', password='pw')
        self.form = Form.objects.create(title='Debate Night', created_by=self.user)
        self.name = FormField.objects.create(form=self.form, label='Full Name', field_type='text', is_required=True, order=1)
        self.email = FormField.objects.create(form=self.form, label='Email', field_type='email', is_required=True, order=2)
        self.phone = FormField.objects.create(form=self.form, label='Phone Number', field_type='text', order=3)
        self.cv = FormField.objects.create(form=self.form, label='CV', field_type='file', order=4)

    def submit(self, **extra):
        data = {f'field_{self.name.id}': 'Amina', f'field_{self.email.id}': 'a@x.com', f'field_{self.phone.id}': '123'}
        data.update(extra)
        return self.client.post(reverse('public_form_submit', args=[self.form.id]), data)

    def test_home_lists_only_active_forms(self):
        Form.objects.create(title='Closed Event', created_by=self.user, is_active=False)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'Debate Night')
        self.assertNotContains(response, 'Closed Event')

    def test_submission_saves_applicant_and_file(self):
        cv = SimpleUploadedFile('cv.pdf', b'data')
        response = self.submit(**{f'field_{self.cv.id}': cv})
        self.assertRedirects(response, reverse('form_success', args=[self.form.id]))
        sub = FormSubmission.objects.get()
        self.assertEqual((sub.applicant_name, sub.applicant_email, sub.applicant_phone), ('Amina', 'a@x.com', '123'))
        self.assertTrue(sub.answers.get(field=self.cv).answer.startswith('submissions/'))

    def test_missing_required_field_rejected(self):
        response = self.submit(**{f'field_{self.name.id}': ''})
        self.assertRedirects(response, reverse('public_form_view', args=[self.form.id]))
        self.assertEqual(FormSubmission.objects.count(), 0)

    def test_export_requires_owner_and_returns_csv(self):
        self.submit()
        url = reverse('form_submissions_export', args=[self.form.id])
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.login(username='staff', password='pw')
        response = self.client.get(url)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('Amina', response.content.decode())
