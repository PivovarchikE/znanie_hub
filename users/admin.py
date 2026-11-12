from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from users.models import StudentProfile, User
from users.services import approve_user, notify_user_approved


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    list_display = ('username', 'full_name', 'role', 'email', 'is_validate', 'is_active', 'created_at')
    list_filter = ('is_validate', 'is_active', 'role')
    search_fields = ('username', 'first_name', 'last_name', 'email')
    ordering = ('-created_at',)

    fieldsets = DjangoUserAdmin.fieldsets + (
        ('Профиль и подтверждение', {
            'fields': ('role', 'middle_name', 'date_of_birth', 'avatar', 'is_validate'),
        }),
    )

    actions = ['approve_users']

    @admin.action(description='Подтвердить выбранных пользователей')
    def approve_users(self, request, queryset):
        pending = list(queryset.filter(is_validate=False))
        for user in pending:
            approve_user(user, request)
        self.message_user(request, f'Подтверждено пользователей: {len(pending)}', messages.SUCCESS)

    def save_model(self, request, obj, form, change):
        # Админ включил «Активный» или «Подтверждён» у ожидающего пользователя -> это подтверждение
        activated = change and 'is_active' in form.changed_data and obj.is_active
        validated = change and 'is_validate' in form.changed_data and obj.is_validate
        just_approved = (activated or validated) and not form.initial.get('is_validate')

        if just_approved:
            obj.is_active = True
            obj.is_validate = True
        super().save_model(request, obj, form, change)
        if just_approved:
            notify_user_approved(obj, request)


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'get_full_name', 'school_class', 'get_teachers')

    list_filter = ('school_class', 'subjects')

    search_fields = ('user__username', 'user__first_name', 'user__last_name')

    fields = ('user', 'teachers', 'school_class', 'subjects')

    filter_horizontal = ('subjects', 'teachers')

    def get_full_name(self, obj):
        return obj.user.full_name or obj.user.get_full_name()

    get_full_name.short_description = 'ФИО ученика'

    def get_teachers(self, obj):
        teachers_list = obj.teachers.all()
        return ", ".join([t.user.get_full_name() or t.user.username for t in teachers_list])

    get_teachers.short_description = 'Учителя'
