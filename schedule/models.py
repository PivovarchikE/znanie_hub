import uuid
from datetime import datetime, timedelta, date, time
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from users.models import BaseModel, TeacherProfile, StudentProfile
from courses.models import Subject


class RecurringRule(BaseModel):
    """
    Правило повторяющихся занятий.
    Хранит параметры генерации серии уроков.
    """

    class Frequency(models.TextChoices):
        WEEKLY = 'WEEKLY', 'Каждую неделю'

    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name='recurring_rules'
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='recurring_rules'
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    # Дни недели в формате JSON/List: [0, 2] (0 - Понедельник, 1 - Вторник, ..., 6 - Воскресенье)
    days_of_week = models.JSONField(
        default=list,
        help_text="Список дней недели (0=Пн, 1=Вт, ..., 6=Вс)"
    )
    start_time = models.TimeField("Время начала")
    end_time = models.TimeField("Время окончания")
    price = models.DecimalField("Стоимость занятия", max_digits=10, decimal_places=2)

    start_date = models.DateField("Дата первого урока")
    end_date = models.DateField("Дата окончания серии")

    def __str__(self):
        return f"Правило повтора #{self.id} для {self.student.user.full_name}"


class Lesson(BaseModel):
    """
    Конкретное занятие в расписании.
    """

    class Status(models.TextChoices):
        SCHEDULED = 'SCHEDULED', 'Назначено'
        COMPLETED = 'COMPLETED', 'Проведено'
        CANCELED = 'CANCELED', 'Отменено'

    class PaymentStatus(models.TextChoices):
        UNPAID = 'UNPAID', 'Не оплачено'
        PAID = 'PAID', 'Оплачено'

    teacher = models.ForeignKey(
        TeacherProfile,
        on_delete=models.CASCADE,
        related_name='lessons',
        verbose_name="Преподаватель"
    )
    student = models.ForeignKey(
        StudentProfile,
        on_delete=models.CASCADE,
        related_name='lessons',
        verbose_name="Ученик"
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Предмет"
    )

    date = models.DateField("Дата занятия")
    start_time = models.TimeField("Время начала")
    end_time = models.TimeField("Время окончания")

    # Поле для хранения длительности занятия в минутах
    duration_minutes = models.PositiveIntegerField("Длительность (мин)", default=0)

    status = models.CharField(
        "Статус занятия",
        max_length=20,
        choices=Status.choices,
        default=Status.SCHEDULED
    )
    payment_status = models.CharField(
        "Статус оплаты",
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.UNPAID
    )

    price = models.DecimalField("Стоимость (руб)", max_digits=10, decimal_places=2, default=Decimal("0.00"))
    topic = models.CharField("Тема урока", max_length=255, blank=True, null=True)
    cancellation_reason = models.TextField("Причина отмены", blank=True, null=True)

    # Связь с правилом серии (если урок сгенерирован автоматически)
    recurring_rule = models.ForeignKey(
        RecurringRule,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='lessons'
    )

    is_recurring = models.BooleanField(default=False)
    parent_lesson = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='recurring_children'
    )

    class Meta:
        ordering = ['date', 'start_time']
        verbose_name = "Занятие"
        verbose_name_plural = "Занятия"
        indexes = [
            models.Index(fields=['teacher', 'date']),
            models.Index(fields=['student', 'date']),
        ]

    def clean(self):
        super().clean()
        if self.start_time and self.end_time and self.start_time >= self.end_time:
            raise ValidationError({'end_time': "Время окончания должно быть позже времени начала."})

    def save(self, *args, **kwargs):
        # Автоматический расчет длительности перед сохранением
        self.full_clean()

        if self.start_time and self.end_time:
            dt_dummy = date.today()
            t_start = datetime.combine(dt_dummy, self.start_time)
            t_end = datetime.combine(dt_dummy, self.end_time)

            # Если время окончания меньше или равно времени начала (ночной перенос)
            if t_end <= t_start:
                t_end += timedelta(days=1)

            self.duration_minutes = max(0, int((t_end - t_start).total_seconds() // 60))

        super().save(*args, **kwargs)

    @property
    def has_overlap(self):
        """Проверка на наложение по времени с другими уроками этого же учителя"""
        overlapping = Lesson.objects.filter(
            teacher=self.teacher,
            date=self.date,
            start_time__lt=self.end_time,
            end_time__gt=self.start_time
        ).exclude(pk=self.pk).exclude(status=Lesson.Status.CANCELED)
        return overlapping.exists()