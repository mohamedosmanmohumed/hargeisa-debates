import json
from datetime import date, datetime, timedelta

from django import forms as djforms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy

from django.core.mail import EmailMessage

from .emails import _deliver, send_certificates_published
from .models import Announcement, Attendance, CertificateSetting, FormSubmission, GridConfig, ProgramSession
from .views import get_manageable_form, staff_required


class AnnouncementForm(djforms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'body']


DAY_NAMES = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']


def default_plan():
    plan, t = [], datetime(2000, 1, 1, 8, 30)
    for mins, brk in [(60, 0), (60, 0), (60, 0), (15, 1), (60, 0), (60, 0), (60, 0)]:
        end = t + timedelta(minutes=mins)
        plan.append({'start': t.strftime('%H:%M'), 'end': end.strftime('%H:%M'), 'break': bool(brk)})
        t = end
    return plan


def get_cfg(form):
    cfg = getattr(form, 'grid_config', None) or default_config(form)
    if not cfg.day_plans:
        cfg.day_plans = {str(i): default_plan() for i in range(7)}
        cfg.save(update_fields=['day_plans'])
    return cfg


def default_config(form):
    today = date.today()
    return GridConfig.objects.create(form=form, start_date=today + timedelta(days=(5 - today.weekday()) % 7),
                                     day_plans={str(i): default_plan() for i in range(7)})


def week_of(cfg, d):
    return (d - grid_first(cfg)).days // 7 + 1


def plan_for(cfg, d):
    plans, wd = cfg.day_plans, d.weekday()
    key = f'{week_of(cfg, d)}:{wd}'
    return (plans[key] if key in plans else plans.get(str(wd))) or []


def day_slots(cfg, d):
    """Ordered slot list for one date; number = column position (1-based)."""
    out = []
    for i, item in enumerate(plan_for(cfg, d), 1):
        out.append({'number': i, 'is_break': bool(item.get('break')),
                    'start': datetime.strptime(item['start'], '%H:%M').time(),
                    'end': datetime.strptime(item['end'], '%H:%M').time()})
    return out


def grid_first(cfg):
    return cfg.start_date - timedelta(days=(cfg.start_date.weekday() - 5) % 7)


def week_dates(cfg, k):
    days, first = set(cfg.work_day_list), grid_first(cfg) + timedelta(weeks=k - 1)
    return [first + timedelta(days=i) for i in range(7) if (first + timedelta(days=i)).weekday() in days]


def grid_dates(cfg):
    return [d for k in range(1, cfg.weeks + 1) for d in week_dates(cfg, k)]


def current_week(cfg, today=None):
    today = today or date.today()
    return max(1, min(cfg.weeks, (today - grid_first(cfg)).days // 7 + 1))


def pick_week(request, cfg):
    try:
        k = int(request.GET.get('week', ''))
    except ValueError:
        return current_week(cfg)
    return max(1, min(cfg.weeks, k))


def week_nav(cfg, k):
    first = grid_first(cfg) + timedelta(weeks=k - 1)
    return {'week': k, 'weeks': cfg.weeks, 'first': first, 'last': first + timedelta(days=6),
            'prev': k - 1 if k > 1 else None, 'next': k + 1 if k < cfg.weeks else None,
            'is_current': k == current_week(cfg) and grid_first(cfg) <= date.today() <= grid_first(cfg) + timedelta(weeks=cfg.weeks, days=-1),
            'all': [{'n': i, 'first': grid_first(cfg) + timedelta(weeks=i - 1)} for i in range(1, cfg.weeks + 1)]}


def clean_plans(raw, work_days=()):
    plans = {}
    for day, items in json.loads(raw).items():
        wk, wd = (int(x) for x in day.split(':'))
        if wd not in range(7) or not 1 <= wk <= 12:
            raise ValueError('Bad day.')
        clean = []
        for it in items:
            start, end = datetime.strptime(it['start'], '%H:%M'), datetime.strptime(it['end'], '%H:%M')
            if end <= start and wd in work_days:
                raise ValueError(f'Week {wk}, {DAY_NAMES[wd]}: end time must be after start time.')
            clean.append({'start': it['start'], 'end': it['end'], 'break': bool(it.get('break'))})
        plans[f'{wk}:{wd}'] = clean
    return plans


# ---------- staff side ----------
@staff_required
def program_manage(request, form_id):
    form = get_manageable_form(request.user, form_id)
    cfg = get_cfg(form)
    admitted = form.submissions.filter(status='admitted').count()
    sessions = list(form.sessions.all())
    for s in sessions:
        counts = {k: 0 for k, _ in Attendance.STATUS_CHOICES}
        for a in s.attendance.all():
            counts[a.status] += 1
        s.counts, s.marked = counts, sum(counts.values())
    by_cell = {(s.date, s.slot_number): s for s in sessions if s.slot_number}
    shown = {(d, sl['number']) for d in grid_dates(cfg) for sl in day_slots(cfg, d) if not sl['is_break']}
    wk = pick_week(request, cfg)
    rows, ncols = [], 0
    for d in week_dates(cfg, wk):
        slots = day_slots(cfg, d)
        ncols = max(ncols, len(slots))
        rows.append({'date': d, 'slots': slots})
    headers = []
    for k in range(1, ncols + 1):
        items = [sl for r in rows for sl in r['slots'] if sl['number'] == k]
        headers.append({'number': k, 'is_break': bool(items) and all(i['is_break'] for i in items)})
    for r in rows:
        r['cells'] = []
        for k in range(1, ncols + 1):
            sl = next((x for x in r['slots'] if x['number'] == k), None)
            r['cells'].append({'slot': sl, 'session': by_cell.get((r['date'], k)) if sl and not sl['is_break'] else None})
    cols = ' '.join('7rem' if h['is_break'] else 'minmax(10rem, 1fr)' for h in headers)
    plans = {f'{k}:{i}': plan_for(cfg, grid_first(cfg) + timedelta(weeks=k - 1, days=(i - 5) % 7)) for k in range(1, cfg.weeks + 1) for i in range(7)}
    return render(request, 'forms/program_manage.html', {
        'form': form, 'cfg': cfg, 'headers': headers, 'rows': rows, 'cols': cols, 'admitted': admitted,
        'loose_sessions': [s for s in sessions if (s.date, s.slot_number) not in shown],
        'announcements': form.announcements.all(),
        'day_choices': [{'i': i, 'name': DAY_NAMES[i], 'on': i in cfg.work_day_list} for i in (5, 6, 0, 1, 2, 3, 4)],
        'plans': plans, 'day_names': DAY_NAMES, 'nav': week_nav(cfg, wk),
    })


@staff_required
def grid_settings(request, form_id):
    form = get_manageable_form(request.user, form_id)
    cfg = get_cfg(form)
    if request.method == 'POST':
        p = request.POST
        try:
            cfg.start_date = date.fromisoformat(p['start_date'])
            cfg.weeks = max(1, min(int(p['weeks']), 12))
            cfg.work_days = ','.join(sorted(set(p.getlist('work_days')), key=int)) or '5,6,0,1,2,3'
            cfg.day_plans = clean_plans(p['plans'], {int(d) for d in cfg.work_days.split(',')})
        except (ValueError, KeyError, TypeError) as e:
            messages.error(request, f'Invalid grid settings: {e}')
            return redirect('program_manage', form_id=form.id)
        cfg.save()
        for s in form.sessions.filter(slot_number__isnull=False):
            sl = next((x for x in day_slots(cfg, s.date) if x['number'] == s.slot_number and not x['is_break']), None)
            if sl:
                s.start_time, s.end_time = sl['start'], sl['end']
                s.save(update_fields=['start_time', 'end_time'])
        messages.success(request, 'Grid settings saved and session times recalculated.')
    return redirect('program_manage', form_id=form.id)


@staff_required
def session_add(request, form_id):
    form = get_manageable_form(request.user, form_id)
    cfg = get_cfg(form)
    if request.method == 'POST':
        p = request.POST
        try:
            day, number = date.fromisoformat(p['date']), int(p['slot'])
            sl = next(x for x in day_slots(cfg, day) if x['number'] == number and not x['is_break'])
        except (ValueError, KeyError, StopIteration):
            messages.error(request, 'Invalid cell.')
            return redirect('program_manage', form_id=form.id)
        start, end = sl['start'], sl['end']
        title, facilitator = p.get('title', '').strip(), p.get('facilitator', '').strip()
        if not title:
            messages.error(request, 'Session name is required.')
            return redirect('program_manage', form_id=form.id)
        if facilitator:
            clash = (ProgramSession.objects.exclude(form=form).filter(
                facilitator__iexact=facilitator, date=day, start_time__lt=end, end_time__gt=start).select_related('form').first())
            if clash:
                messages.error(request, f'{facilitator} is already booked in "{clash.form.title}" on {day:%a %b %d} '
                                        f'({clash.start_time:%H:%M}-{clash.end_time:%H:%M}).')
                return redirect('program_manage', form_id=form.id)
        _, created = ProgramSession.objects.update_or_create(
            form=form, date=day, slot_number=number,
            defaults={'title': title, 'facilitator': facilitator, 'location': p.get('location', '').strip(),
                      'description': p.get('description', '').strip(), 'start_time': start, 'end_time': end})
        messages.success(request, 'Session added to the schedule.' if created else 'Session updated.')
    return redirect('program_manage', form_id=form.id)


@staff_required
def session_delete(request, session_id):
    session = get_object_or_404(ProgramSession, id=session_id)
    form = get_manageable_form(request.user, session.form_id)
    if request.method == 'POST':
        session.delete()
        messages.success(request, 'Session deleted.')
    return redirect('program_manage', form_id=form.id)


@staff_required
def session_attendance(request, session_id):
    session = get_object_or_404(ProgramSession, id=session_id)
    form = get_manageable_form(request.user, session.form_id)
    people = list(form.submissions.filter(status='admitted').order_by('applicant_name'))
    existing = {a.submission_id: a.status for a in session.attendance.all()}
    if request.method == 'POST':
        valid = {k for k, _ in Attendance.STATUS_CHOICES}
        saved = 0
        for p in people:
            value = request.POST.get(f'status_{p.id}', '')
            if value in valid:
                Attendance.objects.update_or_create(session=session, submission=p, defaults={'status': value})
                saved += 1
            elif p.id in existing:
                Attendance.objects.filter(session=session, submission=p).delete()
        messages.success(request, f'Attendance saved for {saved} applicant(s).')
        return redirect('session_attendance', session_id=session.id)
    for p in people:
        p.current = existing.get(p.id, '')
    return render(request, 'forms/session_attendance.html', {
        'form': form, 'session': session, 'people': people, 'statuses': Attendance.STATUS_CHOICES,
    })


@staff_required
def announcement_add(request, form_id):
    form = get_manageable_form(request.user, form_id)
    if request.method == 'POST':
        af = AnnouncementForm(request.POST)
        if af.is_valid():
            af.instance.form = form
            af.save()
            messages.success(request, 'Announcement posted.')
        else:
            messages.error(request, 'Please enter a title and a message.')
    return redirect('program_manage', form_id=form.id)


@staff_required
def announcement_delete(request, announcement_id):
    ann = get_object_or_404(Announcement, id=announcement_id)
    form = get_manageable_form(request.user, ann.form_id)
    if request.method == 'POST':
        ann.delete()
        messages.success(request, 'Announcement deleted.')
    return redirect('program_manage', form_id=form.id)


# ---------- applicant side ----------
def applicant_required(view):
    """Only signed-in, non-staff users that have an admitted application."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff or request.user.is_superuser:
            return redirect('form_list')
        submission = (FormSubmission.objects.filter(user=request.user, status='admitted')
                      .select_related('form').order_by('-submitted_at').first())
        if not submission:
            raise PermissionDenied
        request.submission = submission
        return view(request, *args, **kwargs)
    wrapper.__name__ = view.__name__
    return wrapper


def post_login(request):
    if request.user.is_staff or request.user.is_superuser:
        return redirect('form_list')
    return redirect('applicant_dashboard')


def attendance_summary(submission):
    form = submission.form
    today = date.today()
    held = list(form.sessions.filter(date__lte=today))
    records = {a.session_id: a.status for a in submission.attendance.all()}
    counts = {k: 0 for k, _ in Attendance.STATUS_CHOICES}
    for s in held:
        if s.id in records:
            counts[records[s.id]] += 1
    attended = counts['present'] + counts['late']
    rate = round(100 * attended / len(held)) if held else None
    return held, records, counts, rate


@applicant_required
def applicant_dashboard(request):
    sub = request.submission
    form = sub.form
    held, records, counts, rate = attendance_summary(sub)
    return render(request, 'applicant/dashboard.html', {
        'sub': sub, 'form': form, 'active': 'dashboard',
        'next_session': form.sessions.filter(date__gte=date.today()).first(),
        'upcoming_count': form.sessions.filter(date__gte=date.today()).count(),
        'held_count': len(held), 'counts': counts, 'rate': rate,
        'announcements': form.announcements.all()[:3],
    })


@applicant_required
def applicant_schedule(request):
    sub, form, today = request.submission, request.submission.form, date.today()
    cfg = get_cfg(form)
    wk = pick_week(request, cfg)
    by_cell = {(x.date, x.slot_number): x for x in form.sessions.filter(slot_number__isnull=False)}
    days = [{'date': d, 'is_today': d == today,
             'slots': [dict(sl, session=None if sl['is_break'] else by_cell.get((d, sl['number']))) for sl in day_slots(cfg, d)]}
            for d in week_dates(cfg, wk)]
    nav = week_nav(cfg, wk)
    shown = {(d['date'], sl['number']) for d in days for sl in d['slots'] if not sl['is_break']}
    loose = [x for x in form.sessions.filter(date__range=(nav['first'], nav['last'])) if (x.date, x.slot_number) not in shown]
    return render(request, 'applicant/schedule.html', {
        'sub': sub, 'form': form, 'active': 'schedule', 'days': days, 'nav': nav, 'loose': loose,
    })


@applicant_required
def applicant_attendance(request):
    sub = request.submission
    held, records, counts, rate = attendance_summary(sub)
    rows = []
    labels = dict(Attendance.STATUS_CHOICES)
    for s in held:
        st = records.get(s.id, '')
        rows.append({'session': s, 'status': st, 'label': labels.get(st, 'Not recorded yet')})
    rows.reverse()
    return render(request, 'applicant/attendance.html', {
        'sub': sub, 'form': sub.form, 'active': 'attendance', 'rows': rows, 'counts': counts, 'rate': rate, 'held_count': len(held),
    })


@applicant_required
def applicant_announcements(request):
    sub = request.submission
    return render(request, 'applicant/announcements.html', {
        'sub': sub, 'form': sub.form, 'active': 'announcements', 'announcements': sub.form.announcements.all(),
    })


@applicant_required
def applicant_application(request):
    sub = request.submission
    return render(request, 'applicant/application.html', {
        'sub': sub, 'form': sub.form, 'active': 'application', 'answers': sub.answers.select_related('field'),
    })


class ApplicantPasswordChange(PasswordChangeView):
    template_name = 'applicant/password_change.html'
    success_url = reverse_lazy('applicant_dashboard')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        sub = FormSubmission.objects.filter(user=self.request.user, status='admitted').select_related('form').first()
        ctx.update(sub=sub, active='password')
        return ctx

    def form_valid(self, form):
        messages.success(self.request, 'Your password was changed.')
        return super().form_valid(form)


# ---------- certificates ----------
class CertificateForm(djforms.ModelForm):
    class Meta:
        model = CertificateSetting
        exclude = ['form']
        widgets = {
            'issue_date': djforms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'description': djforms.Textarea(attrs={'rows': 3}),
            'published': djforms.CheckboxInput(),
            'signer1_signature': djforms.ClearableFileInput(attrs={'accept': 'image/*'}),
            'signer2_signature': djforms.ClearableFileInput(attrs={'accept': 'image/*'}),
        }


def render_certificate(request, sub, setting, preview=False):
    return render(request, 'certificate.html', {
        'sub': sub, 'cert': setting, 'form': sub.form, 'preview': preview,
        'program_title': setting.program_title or sub.form.title,
        'number': f'{setting.number_prefix}-{sub.id:03d}',
    })


@staff_required
def certificate_manage(request, form_id):
    form = get_manageable_form(request.user, form_id)
    setting, _ = CertificateSetting.objects.get_or_create(form=form)
    cf = CertificateForm(request.POST or None, request.FILES or None, instance=setting)
    if request.method == 'POST' and cf.is_valid():
        was_published = setting.published
        cf.save()
        msg = 'Certificate settings saved.'
        if cf.instance.published and (not was_published or request.POST.get('notify')):
            subs = list(form.submissions.filter(status='admitted'))
            send_certificates_published(subs, request.build_absolute_uri(reverse('applicant_certificate')))
            msg += f' Notification emails are being sent to {len(subs)} admitted applicant(s).'
        messages.success(request, msg)
        return redirect('certificate_manage', form_id=form.id)
    return render(request, 'forms/certificate_manage.html', {
        'form': form, 'cf': cf, 'setting': setting,
        'admitted': form.submissions.filter(status='admitted').order_by('applicant_name'),
    })


@xframe_options_sameorigin
@staff_required
def certificate_preview(request, submission_id):
    sub = get_object_or_404(FormSubmission.objects.select_related('form'), id=submission_id)
    get_manageable_form(request.user, sub.form_id)
    setting, _ = CertificateSetting.objects.get_or_create(form=sub.form)
    return render_certificate(request, sub, setting, preview=True)


@applicant_required
def applicant_certificate(request):
    sub = request.submission
    setting = CertificateSetting.objects.filter(form=sub.form).first()
    if not setting or not setting.published or not setting.issue_date:
        return render(request, 'applicant/certificate_pending.html', {'sub': sub, 'form': sub.form, 'active': 'certificate'})
    if request.GET.get('view') == 'full':
        return render_certificate(request, sub, setting)
    return render(request, 'applicant/certificate.html', {'sub': sub, 'form': sub.form, 'active': 'certificate', 'cert': setting})


@applicant_required
@require_POST
def applicant_certificate_send(request):
    sub = request.submission
    setting = CertificateSetting.objects.filter(form=sub.form).first()
    if not setting or not setting.published or not setting.issue_date:
        return JsonResponse({'ok': False, 'error': 'Certificate is not available yet.'}, status=403)
    to = (sub.applicant_email or request.user.email or '').strip()
    magics = {'png': (b'\x89PNG', 'image/png'), 'pdf': (b'%PDF', 'application/pdf')}
    files = {f: request.FILES[f] for f in magics if f in request.FILES}
    if not to:
        return JsonResponse({'ok': False, 'error': 'No email address on file.'}, status=400)
    datas = {f: u.read() for f, u in files.items() if u.size <= 15 * 1024 * 1024}
    if not datas or len(datas) != len(files) or any(not d.startswith(magics[f][0]) for f, d in datas.items()):
        return JsonResponse({'ok': False, 'error': 'Invalid certificate file.'}, status=400)
    msg = EmailMessage(
        f'Your certificate - {sub.form.title}',
        f'Dear {sub.applicant_name or "Participant"},\n\nCongratulations! Your certificate for {sub.form.title} is attached.\n\n'
        'Best regards,\nThe Civic Lab Team',
        to=[to],
    )
    for f, d in datas.items():
        msg.attach(f'certificate.{f}', d, magics[f][1])
    _deliver([(sub, 'certificate', msg)])
    return JsonResponse({'ok': True, 'email': to})
