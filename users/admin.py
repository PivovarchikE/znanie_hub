from django.contrib import admin
from courses import models
from django.utils.html import format_html

from users.models import StudentProfile


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
