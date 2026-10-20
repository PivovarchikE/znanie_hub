from datetime import datetime, timedelta, date, time
from decimal import Decimal
from django.db import transaction
from django.db.models import Q, Sum, Count
from .models import Lesson, RecurringRule


def check_lesson_overlap(teacher, date_val, start_time, end_time, exclude_lesson_id=None):
    """
    Проверяет пересечение времени урока с существующими уроками учителя.
    Возвращает найденный конфликтный урок или None.
    """
    qs = Lesson.objects.filter(
        teacher=teacher,
        date=date_val,
        start_time__lt=end_time,
        end_time__gt=start_time
    ).exclude(status=Lesson.Status.CANCELED)

    if exclude_lesson_id:
        qs = qs.exclude(pk=exclude_lesson_id)

    return qs.select_related('student__user').first()


@transaction.atomic
def create_recurring_lessons(teacher, student, subject, days_of_week, start_time, end_time, price, start_date, end_date):
    """
    Создает правило повтора и генерирует уроки на указанный диапазон дат.
    days_of_week: список индексов дней [0, 2] (0=Пн, 1=Вт, ..., 6=Вс)
    """
    rule = RecurringRule.objects.create(
        teacher=teacher,
        student=student,
        subject=subject,
        days_of_week=days_of_week,
        start_time=start_time,
        end_time=end_time,
        price=price,
        start_date=start_date,
        end_date=end_date
    )

    lessons_to_create = []
    current_date = start_date

    while current_date <= end_date:
        if current_date.weekday() in days_of_week:
            lessons_to_create.append(
                Lesson(
                    teacher=teacher,
                    student=student,
                    subject=subject,
                    date=current_date,
                    start_time=start_time,
                    end_time=end_time,
                    price=price,
                    recurring_rule=rule
                )
            )
        current_date += timedelta(days=1)

    created_lessons = Lesson.objects.bulk_create(lessons_to_create)
    return rule, created_lessons


def delete_recurring_lessons(lesson, mode='this_only'):
    """
    Режимы удаления повторяющихся уроков:
    - 'this_only': Удалить только текущий
    - 'future': Удалить этот и все будущие в серии
    - 'all': Удалить все уроки этой серии
    """
    if not lesson.recurring_rule:
        lesson.delete()
        return

    rule = lesson.recurring_rule

    if mode == 'this_only':
        lesson.delete()
    elif mode == 'future':
        Lesson.objects.filter(
            recurring_rule=rule,
            date__gte=lesson.date
        ).delete()
    elif mode == 'all':
        Lesson.objects.filter(recurring_rule=rule).delete()
        rule.delete()


def calculate_schedule_analytics(teacher, start_date, end_date, student_id=None):
    """Универсальный расчет аналитики за произвольный период (неделя/месяц)."""
    queryset = Lesson.objects.filter(
        teacher=teacher,
        date__range=[start_date, end_date]
    )

    if student_id:
        queryset = queryset.filter(student_id=student_id)

    total_lessons = queryset.count()
    completed_lessons = queryset.filter(status=Lesson.Status.COMPLETED).count()
    canceled_lessons = queryset.filter(status=Lesson.Status.CANCELED).count()

    paid_lessons = queryset.exclude(status=Lesson.Status.CANCELED).filter(
        payment_status=Lesson.PaymentStatus.PAID
    ).count()

    # Фактический доход (оплаченные уроки)
    total_revenue_agg = queryset.exclude(status=Lesson.Status.CANCELED).filter(
        payment_status=Lesson.PaymentStatus.PAID
    ).aggregate(total=Sum('price'))['total'] or 0

    # Ожидается к поступлению (проведенные, но неоплаченные)
    expected_revenue_agg = queryset.filter(
        status=Lesson.Status.COMPLETED,
        payment_status=Lesson.PaymentStatus.UNPAID
    ).aggregate(total=Sum('price'))['total'] or 0

    total_minutes = sum(l.duration_minutes for l in queryset if l.duration_minutes)
    total_hours = round(total_minutes / 60, 1)

    return {
        'total_lessons': total_lessons,
        'completed_lessons': completed_lessons,
        'canceled_lessons': canceled_lessons,
        'paid_lessons': paid_lessons,
        'total_hours': total_hours,
        'total_revenue': float(total_revenue_agg),
        'expected_revenue': float(expected_revenue_agg)
    }
