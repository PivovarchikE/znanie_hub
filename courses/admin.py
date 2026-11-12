from django.contrib import admin
from .models import Subject, Section, Topic, SimulatorConfig, TrainingSession, Homework, HomeworkFile


# --- HELP TEXT ---
HELP_TEXTS = {
    'tasks_count': "Сколько примеров получит ученик за одну тренировку (1–100). "
                   "Только для типа «Тренажёр»; для самостоятельной работы не используется. "
                   "Для таблицы умножения на одно число максимум 19 уникальных примеров, "
                   "для «всей таблицы» максимум 81.",
    'params': 'JSON с настройками генератора, например {"kind": "multiplication_division"} '
              'или {"min": 1, "max": 20, "operations": ["+", "-"]}. '
              'Для самостоятельной работы: {"fixed_tasks": [{"question": "2 + 2", "answer": "4"}]}. '
              '"locked": true отключает выбор параметров учеником.',
    'config_type': "«Тренажёр» генерирует случайные примеры, «Самостоятельная работа» использует фиксированный список.",
}


class HelpTextMixin:
    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name in HELP_TEXTS:
            kwargs['help_text'] = HELP_TEXTS[db_field.name]
        return super().formfield_for_dbfield(db_field, request, **kwargs)


# --- INLINES ---

class SimulatorConfigInline(HelpTextMixin, admin.TabularInline):
    model = SimulatorConfig
    extra = 1
    fields = ('label', 'config_type', 'tasks_count', 'params')


class HomeworkFileInline(admin.TabularInline):
    model = HomeworkFile
    extra = 1


# --- РЕДАКТИРУЕМЫЕ МОДЕЛИ ---

@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'parent', 'order')
    list_filter = ('subject', 'parent')
    search_fields = ('title',)
    list_editable = ('order',)
    autocomplete_fields = ['parent']


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('title', 'section', 'order', 'school_class')
    list_editable = ('order',)
    list_filter = ('section__subject', 'school_class')
    search_fields = ('title',)
    inlines = [SimulatorConfigInline]


@admin.register(SimulatorConfig)
class SimulatorConfigAdmin(HelpTextMixin, admin.ModelAdmin):
    list_display = ('label', 'topic', 'config_type', 'tasks_count')
    list_editable = ('tasks_count',)
    list_filter = ('config_type',)
    search_fields = ('label', 'topic__title')


@admin.register(Homework)
class HomeworkAdmin(admin.ModelAdmin):
    list_display = ('title', 'student', 'hw_type', 'is_completed', 'score', 'deadline')
    list_filter = ('hw_type', 'is_completed', 'subject')
    inlines = [HomeworkFileInline]
    date_hierarchy = 'created_at'


# --- МОДЕЛЬ СЕССИЙ (ТОЛЬКО ПРОСМОТР) ---

@admin.register(TrainingSession)
class TrainingSessionAdmin(admin.ModelAdmin):
    # Поля в списке
    list_display = ('get_student_name', 'config', 'correct_count', 'total_questions', 'score_percent', 'end_time')

    # ФИЛЬТРЫ И ПОИСК
    list_filter = ('student', 'config__topic__section__subject', 'end_time')
    # Поиск по связанным полям модели User через "__"
    search_fields = ('student__last_name', 'student__first_name', 'student__username', 'config__label')

    # Кастомные методы для отображения
    def get_student_name(self, obj):
        return obj.student.get_full_name() or obj.student.username

    get_student_name.short_description = "Ученик"
    get_student_name.admin_order_field = 'student__last_name'

    def score_percent(self, obj):
        if obj.total_questions > 0:
            p = int((obj.correct_count / obj.total_questions) * 100)
            color = "green" if p >= 80 else "orange" if p >= 50 else "red"
            from django.utils.html import format_html
            return format_html('<b style="color: {};">{}%</b>', color, p)
        return "0%"

    score_percent.short_description = "Результат"

    # --- ТОЛЬКО ПРОСМОТР ---
    def get_readonly_fields(self, request, obj=None):
        # Все поля модели + свойство duration
        return [f.name for f in self.model._meta.fields] + ['duration']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
