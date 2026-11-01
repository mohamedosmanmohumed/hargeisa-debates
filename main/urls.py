from django.urls import path
from . import views, program_views as pv

urlpatterns = [
    path('', views.home, name='home'),
    
    # Form Management
    path('forms/', views.form_list, name='form_list'),
    path('forms/create/', views.form_create, name='form_create'),
    path('forms/<int:form_id>/edit/', views.form_edit, name='form_edit'),
    path('forms/<int:form_id>/delete/', views.form_delete, name='form_delete'),
    path('forms/<int:form_id>/builder/', views.form_builder, name='form_builder'),
    
    # Field Management
    path('forms/<int:form_id>/field/add/', views.field_add, name='field_add'),
    path('forms/field/<int:field_id>/edit/', views.field_edit, name='field_edit'),
    path('forms/field/<int:field_id>/delete/', views.field_delete, name='field_delete'),
    path('forms/<int:form_id>/reorder/', views.field_reorder, name='field_reorder'),
    
    # Section Management
    path('forms/<int:form_id>/section/add/', views.section_add, name='section_add'),
    path('forms/section/<int:section_id>/edit/', views.section_edit, name='section_edit'),
    path('forms/section/<int:section_id>/delete/', views.section_delete, name='section_delete'),
    
    # Public Form Views
    path('forms/<int:form_id>/view/', views.public_form_view, name='public_form_view'),
    path('forms/<int:form_id>/submit/', views.public_form_submit, name='public_form_submit'),
    path('forms/<int:form_id>/success/', views.form_success, name='form_success'),
    
    # Submission Management
    path('forms/<int:form_id>/submissions/', views.form_submissions, name='form_submissions'),
    path('forms/<int:form_id>/submissions/export/', views.form_submissions_export, name='form_submissions_export'),
    path('forms/<int:form_id>/toggle-applications/', views.form_toggle_applications, name='form_toggle_applications'),
    path('forms/<int:form_id>/submissions/bulk/', views.submissions_bulk_action, name='submissions_bulk_action'),
    path('forms/<int:form_id>/admitted/', views.admitted_list, name='admitted_list'),
    path('forms/<int:form_id>/admitted/create-accounts/', views.create_accounts, name='create_accounts'),
    path('forms/<int:form_id>/emails/', views.email_logs, name='email_logs'),
    path('forms/<int:form_id>/emails/retry/', views.email_retry, name='email_retry'),
    # Program management (staff)
    path('forms/<int:form_id>/program/', pv.program_manage, name='program_manage'),
    path('forms/<int:form_id>/program/settings/', pv.grid_settings, name='grid_settings'),
    path('forms/<int:form_id>/program/session/add/', pv.session_add, name='session_add'),
    path('program/session/<int:session_id>/delete/', pv.session_delete, name='session_delete'),
    path('program/session/<int:session_id>/attendance/', pv.session_attendance, name='session_attendance'),
    path('forms/<int:form_id>/program/announcement/add/', pv.announcement_add, name='announcement_add'),
    path('program/announcement/<int:announcement_id>/delete/', pv.announcement_delete, name='announcement_delete'),

    # Applicant portal
    path('welcome/', pv.post_login, name='post_login'),
    path('me/', pv.applicant_dashboard, name='applicant_dashboard'),
    path('me/schedule/', pv.applicant_schedule, name='applicant_schedule'),
    path('me/attendance/', pv.applicant_attendance, name='applicant_attendance'),
    path('me/announcements/', pv.applicant_announcements, name='applicant_announcements'),
    path('me/certificate/', pv.applicant_certificate, name='applicant_certificate'),
    path('me/certificate/send/', pv.applicant_certificate_send, name='applicant_certificate_send'),
    path('forms/<int:form_id>/certificate/', pv.certificate_manage, name='certificate_manage'),
    path('certificate/preview/<int:submission_id>/', pv.certificate_preview, name='certificate_preview'),
    path('me/application/', pv.applicant_application, name='applicant_application'),
    path('me/password/', pv.ApplicantPasswordChange.as_view(), name='applicant_password'),
    path('submissions/<int:submission_id>/', views.submission_detail, name='submission_detail'),
]
