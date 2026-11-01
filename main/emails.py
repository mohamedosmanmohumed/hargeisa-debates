import logging
import smtplib
import threading

from django.core import mail
from django.db import connection as db_connection

logger = logging.getLogger(__name__)
SKIP_DOMAINS = ('@example.test',)


def _log(form_id, submission_id, kind, to, subject, error=''):
    from .models import EmailLog
    EmailLog.objects.create(
        form_id=form_id, submission_id=submission_id, kind=kind, to_email=to, subject=subject,
        status='failed' if error else 'sent', error=error[:500],
    )


def _deliver(items):
    """items: list of (submission, kind, EmailMessage). Sends in the background and logs each result."""
    items = [i for i in items if i[2]]
    if not items:
        return

    def run():
        conn = None
        try:
            for submission, kind, msg in items:
                error = ''
                for attempt in (1, 2):
                    try:
                        if conn is None:
                            conn = mail.get_connection()
                            conn.open()
                        msg.connection = conn
                        msg.send()
                        error = ''
                        break
                    except smtplib.SMTPServerDisconnected as e:
                        error, conn = str(e) or 'Server disconnected', None
                    except Exception as e:
                        error = f'{type(e).__name__}: {e}'
                        break
                try:
                    _log(submission.form_id, submission.id, kind, msg.to[0], msg.subject, error)
                except Exception:
                    logger.exception('Could not write email log')
        except Exception:
            logger.exception('Email delivery crashed')
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            db_connection.close()

    threading.Thread(target=run, daemon=True).start()


def _build(submission, subject, body):
    to = (submission.applicant_email or '').strip()
    if not to or to.lower().endswith(SKIP_DOMAINS):
        return None
    return mail.EmailMessage(subject, body, to=[to])


def _name(submission):
    return submission.applicant_name or 'Applicant'


def acknowledgment_message(submission):
    form = submission.form
    return _build(
        submission,
        f'We received your application - {form.title}',
        f'Dear {_name(submission)},\n\n'
        f'Thank you for applying to {form.title}. We have received your application and our team will review it carefully.\n\n'
        'We will see your application and we hope that you will be selected for the shortlist. '
        'If you are shortlisted, we will contact you by email with the next steps.\n\n'
        'Best regards,\nThe Civic Lab Team',
    )


def shortlist_message(submission):
    form = submission.form
    return _build(
        submission,
        f'Congratulations! You have been shortlisted - {form.title}',
        f'Dear {_name(submission)},\n\n'
        f'Congratulations! We are pleased to inform you that you have been selected for the shortlist of {form.title}.\n\n'
        'Please attend as requested. We will share the schedule and venue details with you shortly; '
        'kindly reply to this email to confirm your attendance.\n\n'
        'Best regards,\nThe Civic Lab Team',
    )


def credentials_message(submission, username, password, login_url):
    return _build(
        submission,
        f'Your account - {submission.form.title}',
        f'Dear {_name(submission)},\n\n'
        f'Your account for {submission.form.title} has been created.\n\n'
        f'Login page: {login_url}\n'
        f'Username: {username}\n'
        f'Temporary password: {password}\n\n'
        'Please log in and change your password as soon as possible. Do not share this password with anyone.\n\n'
        'Best regards,\nThe Civic Lab Team',
    )


def certificate_published_message(submission, certificate_url):
    return _build(
        submission,
        f'Your certificate is ready - {submission.form.title}',
        f'Dear {_name(submission)},\n\n'
        f'Congratulations! Your certificate for {submission.form.title} has been published and is ready.\n\n'
        f'Log in to view, download or email your certificate:\n{certificate_url}\n\n'
        'Please approach us if you have any questions or need any help with your certificate.\n\n'
        'Best regards,\nThe Civic Lab Team',
    )


def send_certificates_published(submissions, certificate_url):
    _deliver([(s, 'certificate', certificate_published_message(s, certificate_url)) for s in submissions])


def send_acknowledgment(submission):
    _deliver([(submission, 'acknowledgment', acknowledgment_message(submission))])


def send_shortlist(submissions):
    _deliver([(s, 'shortlist', shortlist_message(s)) for s in submissions])


def send_credentials(items, login_url):
    """items: list of (submission, username, password)."""
    _deliver([(s, 'credentials', credentials_message(s, u, p, login_url)) for s, u, p in items])
