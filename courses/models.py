import os

from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from users.models import User, BaseModel, SchoolClass, StudentProfile, TeacherProfile


class Subject(BaseModel):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название")

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"

    def __str__(self):
        return self.name


class Section(BaseModel):
    subject = models.ForeignKey(Subject, related_name='sections', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)

    parent = models.ForeignKey(
        'self',
        null=True,
        blank=True,
        related_name='subsections',
        on_delete=models.CASCADE
    )

    order = models.PositiveIntegerField(default=0, help_text="Порядок вывода (чем меньше число, тем выше)")

    def get_ancestors(self):
        ancestors = []
        curr = self.parent
        while curr is not None:
            ancestors.insert(0, curr)
            curr = curr.parent
        return ancestors

    def get_all_children(self):
        return self.subsections.all().prefetch_related('topics')

    class Meta:
        ordering = ['order', 'title']

    def __str__(self):
        if self.parent:
            return f"{self.parent.title} -> {self.title}"
        return f"[{self.subject.name}] {self.title}"


class Topic(BaseModel):
    section = models.ForeignKey(Section, related_name='topics', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(default='', blank=True, null=True)
    school_class = models.ForeignKey(SchoolClass, related_name='topics', blank=True, null=True, on_delete=models.PROTECT)
    text_content = models.TextField("Теория (Markdown/HTML)", blank=True, null=True)
    order = models.PositiveIntegerField(default=0, verbose_name="Порядок тем внутри раздела")


    def __str__(self):
        return self.title


class SimulatorConfig(BaseModel):
    """Настройки конкретного тренажера (например, 'до 20', 'до 100') или самостоятельной работы"""
    CONFIG_TYPE_CHOICES = [
        ('practice', 'Тренажер (случайные задания)'),
        ('exam', 'Самостоятельная работа (фиксированные задания)'),
    ]

    topic = models.ForeignKey(Topic, related_name='configs', on_delete=models.CASCADE)
    config_type = models.CharField(max_length=20, choices=CONFIG_TYPE_CHOICES, default='practice')
    label = models.CharField(max_length=100)  # "в пределах до 100"
    params = models.JSONField()  # Храним настройки: {"min": 0, "max": 100, "count": 50}

    def __str__(self):
        return f"{self.get_config_type_display()} ({self.label})"


class TrainingSession(BaseModel):
    """Результат прохождения тренажера"""
    student = models.ForeignKey(User, on_delete=models.CASCADE)
    config = models.ForeignKey(SimulatorConfig, on_delete=models.PROTECT)
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    total_questions = models.PositiveIntegerField(default=50)
    solved_count = models.PositiveIntegerField(default=0)
    correct_count = models.PositiveIntegerField(default=0)

    # Храним детали ответов: [{"q": "5+5", "a": "10", "is_correct": True, "user_a": "10"}, ...]
    detailed_results = models.JSONField(default=list)

    @property
    def duration(self):
        if self.end_time:
            return self.end_time - self.start_time
        return None


class Homework(BaseModel):
    TYPE_CHOICES = [
        ('theory', 'Теория'),
        ('practice', 'Практика'),
        ('simulator', 'Тренажер'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Ждет решения'),
        ('review', 'На проверке'),
        ('completed', 'Выполнено'),
        ('correction', 'На доработке'),
    ]

    student = models.ForeignKey('users.StudentProfile', on_delete=models.CASCADE, related_name='homeworks')
    teacher = models.ForeignKey('users.TeacherProfile', on_delete=models.CASCADE)
    subject = models.ForeignKey('courses.Subject', on_delete=models.CASCADE, null=True, verbose_name="Предмет")
    section = models.ForeignKey('courses.Section', on_delete=models.CASCADE, verbose_name="Раздел", null=True,
                                blank=True)
    topic = models.ForeignKey('courses.Topic', on_delete=models.CASCADE, null=True, verbose_name="Тема")
    hw_type = models.CharField("Тип задания", max_length=20, choices=TYPE_CHOICES)
    include_site_theory = models.BooleanField(
        default=False,
        verbose_name="Включить теорию с сайта"
    )
    title = models.CharField("Название", max_length=255)
    content = models.TextField("Содержание (текст)", blank=True, null=True)
    simulator_config = models.ForeignKey('courses.SimulatorConfig', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Конфигурация тренажера")
    score = models.PositiveIntegerField(default=0)
    deadline = models.DateTimeField("Срок сдачи", null=True, blank=True)
    is_completed = models.BooleanField(default=False)

    actual_score = models.PositiveIntegerField(
        "Полученный балл",
        null=True,
        blank=True,
        validators=[
            MinValueValidator(0),
            MaxValueValidator(10)
        ])
    is_theory_read = models.BooleanField("Теория изучена", default=False)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    teacher_comment = models.TextField("Комментарий учителя", blank=True, null=True)

    def get_status_for_student(self, student_user):
        if self.hw_type == 'simulator':
            return TrainingSession.objects.filter(
                student=student_user,
                config=self.simulator_config,
                end_time__isnull=False
            ).exists()

        if self.hw_type == 'practice':
            # Выполнено, если учитель проставил балл
            return self.actual_score is not None

        if self.hw_type == 'theory':
            # Выполнено, если есть отметка о прочтении или включена теория с сайта
            return self.is_theory_read

        return self.is_completed


class HomeworkFile(BaseModel):
    homework = models.ForeignKey(
        'Homework',
        on_delete=models.CASCADE,
        related_name='files'
    )
    file = models.FileField("Файл", upload_to='homeworks/%Y/%m/%d/')
    original_name = models.CharField(max_length=255, blank=True)

    @property
    def filename(self):
        """Возвращает оригинальное имя или имя файла из пути"""
        if self.original_name:
            return self.original_name
        if self.file:
            return os.path.basename(self.file.name)
        return "Файл без названия"

    def __str__(self):
        return self.original_name or self.file.name


class HomeworkResponseFile(BaseModel):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name='responses')
    file = models.ImageField("Фото решения", upload_to='responses/%Y/%m/%d/')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Файл для задания {self.homework.id}"


class HomeworkComment(BaseModel):
    homework = models.ForeignKey(Homework, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']