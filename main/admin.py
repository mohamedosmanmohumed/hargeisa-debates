from django.contrib import admin
from .models import Form, FormField, FormSubmission, FormAnswer


class FormFieldInline(admin.TabularInline):
    model = FormField
    extra = 0
    fields = ['label', 'field_type', 'is_required', 'order']
    ordering = ['order']


@admin.register(Form)
class FormAdmin(admin.ModelAdmin):
    list_display = ['title', 'created_by', 'is_active', 'created_at', 'fields_count', 'submissions_count']
    list_filter = ['is_active', 'created_at']
    search_fields = ['title', 'description', 'created_by__username']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [FormFieldInline]
    
    def fields_count(self, obj):
        return obj.fields.count()
    fields_count.short_description = 'Fields'
    
    def submissions_count(self, obj):
        return obj.submissions.count()
    submissions_count.short_description = 'Submissions'


@admin.register(FormField)
class FormFieldAdmin(admin.ModelAdmin):
    list_display = ['label', 'form', 'field_type', 'is_required', 'order']
    list_filter = ['field_type', 'is_required', 'form']
    search_fields = ['label', 'form__title']
    ordering = ['form', 'order']


@admin.register(FormSubmission)
class FormSubmissionAdmin(admin.ModelAdmin):
    list_display = ['form', 'applicant_name', 'applicant_email', 'submitted_at']
    list_filter = ['form', 'submitted_at']
    search_fields = ['applicant_name', 'applicant_email', 'form__title']
    readonly_fields = ['submitted_at']


@admin.register(FormAnswer)
class FormAnswerAdmin(admin.ModelAdmin):
    list_display = ['field', 'submission', 'answer_preview']
    list_filter = ['field__form', 'field']
    search_fields = ['answer', 'field__label', 'submission__applicant_name']
    
    def answer_preview(self, obj):
        return obj.answer[:50] + '...' if len(obj.answer) > 50 else obj.answer
    answer_preview.short_description = 'Answer'
