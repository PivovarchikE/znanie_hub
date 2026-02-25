from django.contrib import admin
from courses import models
from django.utils.html import format_html

from users.models import StudentProfile


@admin.register(StudentProfile)
class StudentProfileAdmin(admin.ModelAdmin):
    # Поля, которые отображаются в списке всех учеников
    list_display = ('user', 'get_full_name', 'school_class', 'teacher')
    # Фильтры справа
    list_filter = ('school_class', 'teacher')
    # Поля для поиска
    search_fields = ('user__username', 'user__first_name', 'user__last_name')
    # Поля внутри карточки редактирования
    fields = ('user', 'teacher', 'school_class', 'subjects')
    # Many-to-Many поле subjects лучше отображать так для удобства выбора
    filter_horizontal = ('subjects',)

    def get_full_name(self, obj):
        return obj.user.full_name
    get_full_name.short_description = 'ФИО ученика'
