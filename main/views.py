from django.urls import reverse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.contrib import messages
from django.db import models, transaction
from django.core.files.storage import default_storage
from django.db.models import Count, Exists, OuterRef, Q
from django.core.exceptions import PermissionDenied
from django.http import Http404, QueryDict
from urllib.parse import urlencode
import csv
from functools import wraps
import random
from django.db.models.functions import Length
from django.db.models import Subquery
from django.http import HttpResponse
from .emails import send_acknowledgment, send_shortlist
from .models import Form, FormField, FormSubmission, FormAnswer, FormSection

def staff_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return redirect('applicant_dashboard')
        return view(request, *args, **kwargs)
    return wrapper

def home(request):
    if request.user.is_authenticated and not (request.user.is_staff or request.user.is_superuser):
        return redirect('applicant_dashboard')
    forms = Form.objects.filter(is_active=True).annotate(field_count=Count('fields'))
    return render(request, 'main/home.html', {'forms': forms})

# Form Management Views
@staff_required
def form_list(request):
    forms = Form.objects.filter(created_by=request.user).order_by('-created_at')
    return render(request, 'forms/form_list.html', {'forms': forms})

@staff_required
def form_create(request):
    if request.method == 'POST':
        title = request.POST.get('title')
        description = request.POST.get('description', '')
        form = Form.objects.create(
            title=title,
            description=description,
            created_by=request.user
        )
        messages.success(request, 'Form created successfully!')
        return redirect('form_builder', form_id=form.id)
    return render(request, 'forms/form_create.html')

@staff_required
def form_edit(request, form_id):
    form = get_object_or_404(Form, id=form_id, created_by=request.user)
    if request.method == 'POST':
        form.title = request.POST.get('title')
        form.description = request.POST.get('description', '')
        form.is_active = request.POST.get('is_active') == 'on'
        form.save()
        messages.success(request, 'Form updated successfully!')
        return redirect('form_builder', form_id=form.id)
    return render(request, 'forms/form_edit.html', {'form': form})

@staff_required
def form_delete(request, form_id):
    form = get_object_or_404(Form, id=form_id, created_by=request.user)
    if request.method == 'POST':
        form.delete()
        messages.success(request, 'Form deleted successfully!')
        return redirect('form_list')
    return render(request, 'forms/form_delete.html', {'form': form})

# Form Builder View (Google Forms-like)
@staff_required
def form_builder(request, form_id):
    form = get_object_or_404(Form, id=form_id, created_by=request.user)
    sections = form.sections.all()
    fields = form.fields.all()
    return render(request, 'forms/form_builder.html', {'form': form, 'sections': sections, 'fields': fields})

# Form Field Management
@staff_required
def field_add(request, form_id):
    form = get_object_or_404(Form, id=form_id, created_by=request.user)
    if request.method == 'POST':
        field_type = request.POST.get('field_type')
        label = request.POST.get('label')
        is_required = request.POST.get('is_required') == 'on'
        placeholder = request.POST.get('placeholder', '')
        options = request.POST.get('options', '')
        section_id = request.POST.get('section')
        
        # Get the highest order number
        max_order = form.fields.aggregate(models.Max('order'))['order__max'] or 0
        
        field = FormField.objects.create(
            form=form,
            field_type=field_type,
            label=label,
            is_required=is_required,
            placeholder=placeholder,
            options=options,
            order=max_order + 1
        )
        
        # Assign to section if provided
        if section_id:
            try:
                section = FormSection.objects.get(id=section_id, form=form)
                field.section = section
                field.save()
            except FormSection.DoesNotExist:
                pass
        
        return JsonResponse({'success': True, 'field_id': field.id})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@staff_required
def field_edit(request, field_id):
    field = get_object_or_404(FormField, id=field_id, form__created_by=request.user)
    if request.method == 'POST':
        field.label = request.POST.get('label')
        field.is_required = request.POST.get('is_required') == 'on'
        field.placeholder = request.POST.get('placeholder', '')
        field.options = request.POST.get('options', '')
        field.save()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@staff_required
def field_delete(request, field_id):
    field = get_object_or_404(FormField, id=field_id, form__created_by=request.user)
    if request.method == 'POST':
        field.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@staff_required
def field_reorder(request, form_id):
    import json
    form = get_object_or_404(Form, id=form_id, created_by=request.user)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            field_order = data.get('field_order', [])
            for index, field_id in enumerate(field_order):
                field = FormField.objects.get(id=field_id, form=form)
                field.order = index
                field.save()
            return JsonResponse({'success': True})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# Section Management
@staff_required
def section_add(request, form_id):
    form = get_object_or_404(Form, id=form_id, created_by=request.user)
    if request.method == 'POST':
        title = request.POST.get('title', '')
        description = request.POST.get('description', '')
        
        max_order = form.sections.aggregate(models.Max('order'))['order__max'] or 0
        
        section = FormSection.objects.create(
            form=form,
            title=title,
            description=description,
            order=max_order + 1
        )
        return JsonResponse({'success': True, 'section_id': section.id})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@staff_required
def section_edit(request, section_id):
    section = get_object_or_404(FormSection, id=section_id, form__created_by=request.user)
    if request.method == 'POST':
        section.title = request.POST.get('title', '')
        section.description = request.POST.get('description', '')
        section.save()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

@staff_required
def section_delete(request, section_id):
    section = get_object_or_404(FormSection, id=section_id, form__created_by=request.user)
    if request.method == 'POST':
        section.delete()
        return JsonResponse({'success': True})
    return JsonResponse({'success': False, 'error': 'Invalid request'})

# Public Form Views
def public_form_view(request, form_id):
    form = get_object_or_404(Form, id=form_id, is_active=True)
    if not form.accepting_responses:
        return render(request, 'forms/form_closed.html', {'form': form})
    sections = form.sections.all()
    fields = form.fields.all()
    return render(request, 'forms/public_form.html', {'form': form, 'sections': sections, 'fields': fields})

def public_form_submit(request, form_id):
    form = get_object_or_404(Form, id=form_id, is_active=True)
    if request.method != 'POST' or not form.accepting_responses:
        return redirect('public_form_view', form_id=form.id)

    fields = list(form.fields.all())
    answers, missing = {}, []
    for field in fields:
        name = f'field_{field.id}'
        if field.field_type == 'file':
            upload = request.FILES.get(name)
            value = default_storage.save(f'submissions/{form.id}/{upload.name}', upload) if upload else ''
        elif field.field_type == 'checkbox':
            value = ', '.join(request.POST.getlist(name))
        else:
            value = request.POST.get(name, '').strip()
        if field.is_required and not value:
            missing.append(field.label)
        answers[field.id] = value

    if missing:
        messages.error(request, 'Please complete the required fields: ' + ', '.join(missing))
        return redirect('public_form_view', form_id=form.id)

    applicant = {'name': '', 'email': '', 'phone': ''}
    for field in fields:
        value, label = answers[field.id], field.label.lower()
        if not value:
            continue
        if field.field_type == 'email' and not applicant['email']:
            applicant['email'] = value
        elif 'phone' in label and not applicant['phone']:
            applicant['phone'] = value[:20]
        elif 'name' in label and not applicant['name']:
            applicant['name'] = value

    with transaction.atomic():
        submission = FormSubmission.objects.create(
            form=form,
            applicant_name=applicant['name'][:200],
            applicant_email=applicant['email'],
            applicant_phone=applicant['phone'],
        )
        FormAnswer.objects.bulk_create(
            FormAnswer(submission=submission, field=field, answer=answers[field.id]) for field in fields
        )

    transaction.on_commit(lambda: send_acknowledgment(submission))
    return redirect('form_success', form_id=form.id)

def form_success(request, form_id):
    form = get_object_or_404(Form, id=form_id)
    return render(request, 'forms/form_success.html', {'form': form})

# Admin View for Submissions
CHOICE_TYPES = ('select', 'radio', 'checkbox')

def get_manageable_form(user, form_id):
    form = get_object_or_404(Form, id=form_id)
    if form.created_by_id != user.id and not (user.is_staff or user.is_superuser):
        raise PermissionDenied
    return form


def parse_quota(form, params):
    """Read exact-number selection settings from GET params."""
    num = lambda v: int(v) if str(v).strip().isdigit() else 0
    field = form.fields.filter(id=num(params.get('quota_field', 0)), field_type__in=CHOICE_TYPES).first()
    counts = {}
    if field:
        for i, _ in enumerate(o for o in field.options.split(',') if o.strip()):
            counts[i] = num(params.get(f'quota_{i}', 0))
    total = num(params.get('quota_total', 0))
    active = sum(counts.values()) > 0 if field else total > 0
    return {'field': field, 'counts': counts, 'total': total, 'active': active,
            'mode': params.get('quota_mode', 'random'), 'seed': params.get('quota_seed', '0')}


def apply_quota(form, submissions, quota):
    rng = random.Random(quota['seed'])
    pick = lambda ids, n: rng.sample(ids, min(n, len(ids))) if quota['mode'] == 'random' else ids[:n]
    ordered = lambda qs: list(qs.values_list('id', flat=True))
    pool = submissions.filter(status='pending')
    chosen = []
    field = quota['field']
    if field:
        opts = [o.strip() for o in field.options.split(',') if o.strip()]
        for i, opt in enumerate(opts):
            n = quota['counts'].get(i, 0)
            if not n:
                continue
            cond = Q(answer__icontains=opt) if field.field_type == 'checkbox' else Q(answer=opt)
            group = pool.filter(Exists(FormAnswer.objects.filter(submission=OuterRef('pk'), field=field).filter(cond)))
            chosen += pick([x for x in ordered(group) if x not in chosen], n)
    else:
        chosen = pick(ordered(pool), quota['total'])
    return submissions.filter(id__in=chosen)

def filter_submissions(form, params):
    """Apply dynamic, field-based filters from GET params. Returns (queryset, filter descriptors)."""
    submissions = form.submissions.all()
    status = params.get('status', '')
    if status in ('pending', 'selected', 'admitted'):
        submissions = submissions.filter(status=status)
    q = params.get('q', '').strip()
    if q:
        submissions = submissions.filter(
            Q(applicant_name__icontains=q) | Q(applicant_email__icontains=q) | Q(applicant_phone__icontains=q)
            | Exists(FormAnswer.objects.filter(submission=OuterRef('pk'), answer__icontains=q))
        )
    filters = []
    for field in form.fields.all():
        if field.field_type == 'file':
            continue
        key = f'f_{field.id}'
        item = {'field': field, 'key': key}
        cond = None
        if field.field_type in CHOICE_TYPES:
            opts = [o.strip() for o in field.options.split(',') if o.strip()]
            chosen = [v for v in params.getlist(key) if v]
            item.update(kind='choice', options=[(o, o in chosen) for o in opts])
            if chosen:
                cond = Q()
                for v in chosen:
                    cond |= Q(answer__icontains=v) if field.field_type == 'checkbox' else Q(answer=v)
        elif field.field_type == 'date':
            d_from, d_to = params.get(key + '_from', ''), params.get(key + '_to', '')
            item.update(kind='date', value_from=d_from, value_to=d_to)
            if d_from:
                cond = Q(answer__gte=d_from) & ~Q(answer='')
            if d_to:
                cond = (cond or Q(answer__gt='')) & Q(answer__lte=d_to)
        else:
            val = params.get(key, '').strip()
            min_w, max_w = params.get(key + '_min', '').strip(), params.get(key + '_max', '').strip()
            item.update(kind='text', value=val, min_words=min_w, max_words=max_w)
            for word in val.split():
                cond = (cond or Q()) & Q(answer__icontains=word)
            if min_w.isdigit() or max_w.isdigit():
                lo = int(min_w) if min_w.isdigit() else 0
                hi = int(max_w) if max_w.isdigit() else float('inf')
                ids = [a.submission_id for a in FormAnswer.objects.filter(field=field).only('submission_id', 'answer')
                       if lo <= len(a.answer.split()) <= hi]
                submissions = submissions.filter(id__in=ids)
        if cond is not None:
            submissions = submissions.filter(
                Exists(FormAnswer.objects.filter(submission=OuterRef('pk'), field=field).filter(cond))
            )
        filters.append(item)
    sort = params.get('sort', '')
    direction, _, fid = sort.partition('_')
    if direction in ('longest', 'shortest') and fid.isdigit():
        length = Subquery(FormAnswer.objects.filter(submission=OuterRef('pk'), field_id=int(fid))
                          .annotate(l=Length('answer')).values('l')[:1])
        submissions = submissions.annotate(sort_len=length).order_by(
            ('-' if direction == 'longest' else '') + 'sort_len', '-submitted_at')
    elif sort == 'oldest':
        submissions = submissions.order_by('submitted_at')
    quota = parse_quota(form, params)
    if quota['active']:
        submissions = apply_quota(form, submissions, quota)
    return submissions, filters

def quota_state(form, params):
    q = parse_quota(form, params)
    return {'field_id': q['field'].id if q['field'] else '', 'counts': q['counts'], 'total': q['total'] or '',
            'mode': q['mode'], 'active': q['active']}


@staff_required
def form_submissions(request, form_id):
    form = get_manageable_form(request.user, form_id)
    submissions, filters = filter_submissions(form, request.GET)
    total = form.submissions.count()
    context = {
        'form': form,
        'submissions': submissions,
        'filters': filters,
        'total': total,
        'admitted_count': form.submissions.filter(status='admitted').count(),
        'selected_count': form.submissions.filter(status='selected').count(),
        'status': request.GET.get('status', ''),
        'sort': request.GET.get('sort', ''),
        'quota': quota_state(form, request.GET),
        'sort_options': [
            (f'{d}_{f["field"].id}', f'{d.capitalize()} answer: {f["field"].label[:40]}')
            for f in filters if f['kind'] == 'text' and f['field'].field_type == 'textarea' for d in ('longest', 'shortest')
        ],
        'choice_fields': [
            {'id': f['field'].id, 'label': f['field'].label, 'options': [o for o, _ in f['options']]}
            for f in filters if f['kind'] == 'choice'
        ],
        'quota_json': quota_state(form, request.GET),
        'q': request.GET.get('q', ''),
        'querystring': request.GET.urlencode(),
        'is_filtered': any(v for k, vals in request.GET.lists() for v in vals if k != 'status') or bool(request.GET.get('status')),
    }
    return render(request, 'forms/form_submissions.html', context)

@staff_required
def form_toggle_applications(request, form_id):
    form = get_manageable_form(request.user, form_id)
    if request.method == 'POST':
        form.accepting_responses = not form.accepting_responses
        form.save(update_fields=['accepting_responses'])
        messages.success(request, 'Applications are now open.' if form.accepting_responses else 'Applications are now closed.')
    return redirect(request.POST.get('next') or 'form_list')

@staff_required
def submissions_bulk_action(request, form_id):
    form = get_manageable_form(request.user, form_id)
    qs = request.POST.get('querystring', '')
    back = f"{reverse('form_submissions', args=[form.id])}{'?' + qs if qs else ''}"
    if request.method != 'POST':
        return redirect(back)
    nxt = request.POST.get('next', '')
    if nxt.startswith('/') and not nxt.startswith('//'):
        back = nxt
    action = request.POST.get('action')
    if action in ('stage_filtered', 'admit_filtered', 'unadmit_filtered'):
        targets, _ = filter_submissions(form, QueryDict(qs))
    elif action == 'admit_staged':
        targets = form.submissions.filter(status='selected')
    else:
        targets = form.submissions.filter(id__in=request.POST.getlist('ids'))
    if action in ('stage_selected', 'stage_filtered'):
        changing = list(targets.filter(status='pending'))
        new_status, text = 'selected', 'added to the Selection (not admitted yet)'
    elif action in ('admit_selected', 'admit_filtered', 'admit_staged'):
        changing = list(targets.exclude(status='admitted').select_related('form'))
        new_status, text = 'admitted', 'admitted to the shortlist and emailed'
    else:
        changing = list(targets.exclude(status='pending'))
        new_status, text = 'pending', 'moved back to Pending'
    count = FormSubmission.objects.filter(id__in=[t.id for t in changing]).update(status=new_status)
    if new_status == 'admitted':
        send_shortlist(changing)
    messages.success(request, f'{count} applicant(s) {text}.')
    return redirect(back)

@staff_required
def form_submissions_export(request, form_id):
    form = get_manageable_form(request.user, form_id)
    fields = list(form.fields.all())
    submissions, _ = filter_submissions(form, request.GET)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="form-{form.id}-submissions.csv"'
    writer = csv.writer(response)
    writer.writerow(['Submitted', 'Status'] + [f.label for f in fields])
    for submission in submissions.prefetch_related('answers'):
        by_field = {a.field_id: a.answer for a in submission.answers.all()}
        writer.writerow([submission.submitted_at.strftime('%Y-%m-%d %H:%M'), submission.get_status_display()] + [by_field.get(f.id, '') for f in fields])
    return response

@staff_required
def submission_detail(request, submission_id):
    submission = get_object_or_404(FormSubmission, id=submission_id)
    get_manageable_form(request.user, submission.form_id)
    answers = submission.answers.all()
    return render(request, 'forms/submission_detail.html', {'submission': submission, 'answers': answers})


# Admitted applicants, accounts and email log
import re
import secrets
from urllib.parse import quote
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from .emails import _deliver as deliver_items, acknowledgment_message, shortlist_message, credentials_message, send_credentials
from .models import EmailLog

TEMP_ALPHABET = 'abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789'


def make_temp_password():
    return ''.join(secrets.choice(TEMP_ALPHABET) for _ in range(10))


def login_url(request):
    return request.build_absolute_uri(reverse('login'))


@staff_required
def admitted_list(request, form_id):
    form = get_manageable_form(request.user, form_id)
    admitted = form.submissions.filter(status='admitted').select_related('user')
    q = request.GET.get('q', '').strip()
    account = request.GET.get('account', '')
    if q:
        admitted = admitted.filter(Q(applicant_name__icontains=q) | Q(applicant_email__icontains=q) | Q(applicant_phone__icontains=q))
    if account == 'with':
        admitted = admitted.filter(user__isnull=False)
    elif account == 'without':
        admitted = admitted.filter(user__isnull=True)
    base = form.submissions.filter(status='admitted')
    return render(request, 'forms/admitted_list.html', {
        'form': form, 'admitted': admitted, 'q': q, 'account': account,
        'total': base.count(), 'with_account': base.filter(user__isnull=False).count(),
        'without_account': base.filter(user__isnull=True).count(),
    })


@staff_required
def create_accounts(request, form_id):
    form = get_manageable_form(request.user, form_id)
    back = reverse('admitted_list', args=[form.id])
    if request.method != 'POST':
        return redirect(back)
    targets = form.submissions.filter(status='admitted', user__isnull=True).select_related('form')
    if request.POST.get('action') == 'selected':
        targets = targets.filter(id__in=request.POST.getlist('ids'))
    created, skipped, outgoing = 0, [], []
    for sub in targets:
        email = (sub.applicant_email or '').strip().lower()
        if not email:
            skipped.append(f'{sub.applicant_name or sub.id} (no email)')
        elif User.objects.filter(username__iexact=email).exists():
            skipped.append(f'{email} (an account with this email already exists)')
        else:
            password = make_temp_password()
            user = User.objects.create_user(username=email, email=email, password=password,
                                            first_name=(sub.applicant_name or '')[:150])
            sub.user = user
            sub.save(update_fields=['user'])
            outgoing.append((sub, email, password))
            created += 1
    send_credentials(outgoing, login_url(request))
    messages.success(request, f'{created} account(s) created. Login details are being emailed - check the Email Log for the results.')
    if skipped:
        messages.warning(request, 'Skipped: ' + '; '.join(skipped[:10]) + (' ...' if len(skipped) > 10 else ''))
    return redirect(back)


KIND_NOTE = {
    'acknowledgment': 'we received your application',
    'shortlist': 'you have been shortlisted',
    'credentials': 'your account login details',
}


@staff_required
def email_logs(request, form_id):
    form = get_manageable_form(request.user, form_id)
    logs = form.email_logs.select_related('submission')
    status, kind, q = request.GET.get('status', ''), request.GET.get('kind', ''), request.GET.get('q', '').strip()
    counts = {s: form.email_logs.filter(status=s).count() for s in ('sent', 'failed')}
    if status in ('sent', 'failed'):
        logs = logs.filter(status=status)
    if kind in KIND_NOTE:
        logs = logs.filter(kind=kind)
    if q:
        logs = logs.filter(Q(to_email__icontains=q) | Q(submission__applicant_name__icontains=q) | Q(submission__applicant_phone__icontains=q))
    page = Paginator(logs, 100).get_page(request.GET.get('page'))
    for row in page:
        sub = row.submission
        digits = re.sub(r'\D', '', sub.applicant_phone) if sub else ''
        row.phone = sub.applicant_phone if sub else ''
        row.name = sub.applicant_name if sub else ''
        text = (f'Hello {row.name or ""}, we tried to email you about {KIND_NOTE[row.kind]} ({form.title}) '
                f'but the message to {row.to_email} could not be delivered. Please reply here with a correct email address.')
        row.wa_link = f'https://wa.me/{digits}?text={quote(text)}' if row.status == 'failed' and digits else ''
    return render(request, 'forms/email_logs.html', {
        'form': form, 'page': page, 'status': status, 'kind': kind, 'q': q, 'counts': counts,
        'kinds': EmailLog.KIND_CHOICES,
        'querystring': '&'.join(f'{k}={quote(v)}' for k, v in (('status', status), ('kind', kind), ('q', q)) if v),
    })


@staff_required
def email_retry(request, form_id):
    form = get_manageable_form(request.user, form_id)
    back = reverse('email_logs', args=[form.id]) + '?status=failed'
    if request.method != 'POST':
        return redirect(back)
    failed = form.email_logs.filter(status='failed').select_related('submission__form', 'submission__user')
    if request.POST.get('action') == 'selected':
        failed = failed.filter(id__in=request.POST.getlist('ids'))
    items, retried_ids = [], []
    for log in failed:
        sub = log.submission
        if not sub:
            continue
        if log.kind == 'acknowledgment':
            msg = acknowledgment_message(sub)
        elif log.kind == 'shortlist':
            msg = shortlist_message(sub)
        elif sub.user:
            password = make_temp_password()
            sub.user.set_password(password)
            sub.user.save(update_fields=['password'])
            msg = credentials_message(sub, sub.user.username, password, login_url(request))
        else:
            continue
        items.append((sub, log.kind, msg))
        retried_ids.append(log.id)
    form.email_logs.filter(id__in=retried_ids).delete()
    deliver_items(items)
    messages.success(request, f'Retrying {len(items)} failed email(s). Refresh in a moment to see the new results.')
    return redirect(back)
