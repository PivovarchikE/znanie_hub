from django.db import models
from users.models import User, BaseModel, SchoolClass, StudentProfile, TeacherProfile


class Subject(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Название")

    class Meta:
        verbose_name = "Предмет"
        verbose_name_plural = "Предметы"

    def __str__(self):
        return self.name


class Section(BaseModel):
    subject = models.ForeignKey(Subject, related_name='sections', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(default='')

    def __str__(self):
        return self.title


class Topic(BaseModel):
    CONTENT_TYPE_CHOICES = [
        ('theory_and_practice', 'Теория и практика'),
        ('simulator', 'Тренажер'),
    ]

    section = models.ForeignKey(Section, related_name='topics', on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(default='')
    school_class = models.ForeignKey(SchoolClass, related_name='topics', blank=True, null=True, on_delete=models.PROTECT)
    content_type = models.CharField(max_length=20, choices=CONTENT_TYPE_CHOICES, default='theory_and_practice')
    text_content = models.TextField(blank=True, null=True)


    def __str__(self):
        return self.title


class SimulatorConfig(models.Model):
    """Настройки конкретного тренажера (например, 'до 20', 'до 100')"""
    topic = models.ForeignKey(Topic, related_name='configs', on_delete=models.CASCADE)
    label = models.CharField(max_length=100)  # "в пределах до 100"
    params = models.JSONField()  # Храним настройки: {"min": 0, "max": 100, "count": 50}

    def __str__(self):
        return f"{self.topic.title} ({self.label})"


class TrainingSession(models.Model):
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
    student = models.ForeignKey('users.StudentProfile', on_delete=models.CASCADE, related_name='homeworks')
    teacher = models.ForeignKey('users.TeacherProfile', on_delete=models.CASCADE)
    hw_type = models.CharField("Тип задания", max_length=20, choices=TYPE_CHOICES)
    title = models.CharField("Название", max_length=255)
    content = models.TextField("Содержание (текст)", blank=True, null=True)
    simulator_config = models.ForeignKey('courses.SimulatorConfig', on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Конфигурация тренажера")
    deadline = models.DateTimeField("Срок сдачи", null=True, blank=True)
    is_active = models.BooleanField(default=True) # Для Soft Delete