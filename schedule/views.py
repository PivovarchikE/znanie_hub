import json
from calendar import monthrange
from datetime import datetime, timedelta, date
from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods

from .models import Lesson, RecurringRule
from .services import (
    check_lesson_overlap,
    create_recurring_lessons,
    delete_recurring_lessons,
    calculate_schedule_analytics
)


@login_required
def schedule_dashboard_view(request):
    """Основной рендер страницы расписания для учителя"""
    teacher_profile = getattr(request.user, 'teacher_profile', None)

    # Если зашел не учитель — выдать 403 ошибку
    if not teacher_profile:
        raise PermissionDenied("Доступ к расписанию есть только у учителей.")

    # 1. Формируем список словарей для учеников
    my_students_qs = teacher_profile.my_students.select_related('user').all()
    students_data = [
        {
            'id': str(student.id),
            'name': student.user.full_name or student.user.username,
            'school_class': str(student.school_class) if student.school_class else None,
        }
        for student in my_students_qs
    ]

    # 2. Формируем список словарей для предметов
    subjects_data = list(teacher_profile.subjects.values('id', 'name'))
    # Приводим UUID (если используется) к строковому формату для JSON
    for sub in subjects_data:
        sub['id'] = str(sub['id'])

    context = {
        'students': students_data,
        'subjects': subjects_data,
    }
    return render(request, 'schedule/schedule_list.html', context)


@login_required
@require_http_methods(['GET'])
def get_week_schedule_api(request):
    """API получения уроков и аналитики (поддерживает week и month)"""
    teacher = request.user.teacher_profile

    # Парсинг даты (по умолчанию текущая)
    date_str = request.GET.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            target_date = date.today()
    else:
        target_date = date.today()

    view_type = request.GET.get('view_type', 'week')
    student_id = request.GET.get('student_id')

    # Динамический расчет временного диапазона в зависимости от view_type
    if view_type == 'month':
        # 1. Границы целевого месяца для АНАЛИТИКИ
        analytics_start = target_date.replace(day=1)
        _, last_day_num = monthrange(target_date.year, target_date.month)
        analytics_end = target_date.replace(day=last_day_num)

        # 2. Расширенный диапазон сетки для ОТОБРАЖЕНИЯ (включая серые дни)
        start_date = analytics_start - timedelta(days=analytics_start.weekday())
        end_date = analytics_end + timedelta(days=(6 - analytics_end.weekday()))
    else:
        # Режим 'week': Расчет понедельника и воскресенья недели
        start_date = target_date - timedelta(days=target_date.weekday())
        end_date = start_date + timedelta(days=6)

        # Для недели границы аналитики совпадают с границами периода
        analytics_start = start_date
        analytics_end = end_date

    # 1. Загружаем ВСЕ уроки преподавателя за период сетки
    all_period_lessons = list(
        Lesson.objects.filter(
            teacher=teacher,
            date__range=[start_date, end_date]
        ).select_related('student__user', 'subject')
    )

    # 2. Фильтруем список для отдачи на фронтенд, если выбран конкретный ученик
    if student_id:
        display_lessons = [l for l in all_period_lessons if str(l.student_id) == str(student_id)]
    else:
        display_lessons = all_period_lessons

    lessons_data = []

    # 3. Наполняем массив с учетом флага наложения
    for l in display_lessons:
        if l.status == Lesson.Status.CANCELED:
            has_overlap = False
        else:
            has_overlap = any(
                other.id != l.id and
                other.date == l.date and
                other.status != Lesson.Status.CANCELED and
                other.start_time < l.end_time and
                other.end_time > l.start_time
                for other in all_period_lessons
            )

        lessons_data.append({
            'id': str(l.id),
            'student_id': str(l.student.id),
            'student_name': getattr(l.student.user, 'full_name', None) or l.student.user.username,
            'subject_id': str(l.subject.id) if l.subject else None,
            'subject_name': l.subject.name if l.subject else 'Без предмета',
            'date': l.date.strftime('%Y-%m-%d'),
            'start_time': l.start_time.strftime('%H:%M'),
            'end_time': l.end_time.strftime('%H:%M'),
            'duration_minutes': l.duration_minutes,
            'status': str(l.status),
            'payment_status': str(l.payment_status),
            'price': float(l.price) if l.price else 0.0,
            'topic': l.topic or '',
            'is_recurring': bool(getattr(l, 'recurring_rule_id', None)),
            'is_overlapping': has_overlap
        })

    # Передаем точные границы целевого месяца/недели в аналитику
    analytics = calculate_schedule_analytics(teacher, analytics_start, analytics_end, student_id)

    return JsonResponse({
        'period_start': start_date.strftime('%Y-%m-%d'),
        'period_end': end_date.strftime('%Y-%m-%d'),
        'week_start': start_date.strftime('%Y-%m-%d'),
        'week_end': end_date.strftime('%Y-%m-%d'),
        'lessons': lessons_data,
        'analytics': analytics
    })


@login_required
@require_http_methods(['POST'])
@transaction.atomic
def save_lesson_api(request):
    """API создания или редактирования урока (с поддержкой серии по RecurringRule)"""
    teacher = request.user.teacher_profile
    data = json.loads(request.body)

    # Приводим типы данных из JSON к безопасным типам
    lesson_id = int(data['id']) if data.get('id') else None
    student_id = int(data['student_id']) if data.get('student_id') else None
    subject_id = int(data['subject_id']) if data.get('subject_id') else None

    date_val = datetime.strptime(data['date'], '%Y-%m-%d').date()
    start_time = datetime.strptime(data['start_time'], '%H:%M').time()
    end_time = datetime.strptime(data['end_time'], '%H:%M').time()
    price = Decimal(str(data.get('price', 0)))
    status = data.get('status', Lesson.Status.SCHEDULED)
    payment_status = data.get('payment_status', Lesson.PaymentStatus.UNPAID)
    topic = data.get('topic', '')

    is_recurring = data.get('is_recurring', False)
    update_mode = data.get('update_mode', 'this_only')  # 'this_only' или 'future'

    force_save = data.get('force_save', False)

    # 1. Проверка на пересечение по времени
    overlap = check_lesson_overlap(teacher, date_val, start_time, end_time, exclude_lesson_id=lesson_id)

    # Если наложение есть, но пользователь ещё не подтвердил сохранение — возвращаем предупреждение
    if overlap and status != Lesson.Status.CANCELED and not force_save:
        overlap_student = overlap.student.user.full_name or overlap.student.user.username
        return JsonResponse({
            'success': False,
            'warning_overlap': True,
            'message': f"Внимание! В {overlap.start_time.strftime('%H:%M')} у вас уже есть урок с учеником {overlap_student}. Сохранить всё равно?"
        }, status=200)  # Возвращаем 200 OK, чтобы фронтенд обработал мягкое предупреждение

    # 2. Создание НОВОЙ серии уроков
    if is_recurring and not lesson_id:
        days_of_week = data.get('days_of_week', [date_val.weekday()])
        weeks_count = int(data.get('weeks_count', 4))
        end_date = date_val + timedelta(weeks=weeks_count)

        student = get_object_or_404(teacher.my_students, id=student_id)
        subject = teacher.subjects.filter(id=subject_id).first() if subject_id else None

        create_recurring_lessons(
            teacher=teacher,
            student=student,
            subject=subject,
            days_of_week=days_of_week,
            start_time=start_time,
            end_time=end_time,
            price=price,
            start_date=date_val,
            end_date=end_date
        )
        return JsonResponse({'success': True, 'message': "Серия уроков успешно добавлена"})

    # 3. РЕДАКТИРОВАНИЕ существующего урока (или создание одиночного)
    if lesson_id:
        current_lesson = get_object_or_404(Lesson, id=lesson_id, teacher=teacher)
        student = get_object_or_404(teacher.my_students, id=student_id) if student_id else None
        subject = teacher.subjects.filter(id=subject_id).first() if subject_id else None

        # ЕСЛИ вы выбрали обновить «Этот и будущие» УРОКИ СЕРИИ
        if update_mode == 'future' and current_lesson.recurring_rule:
            rule = current_lesson.recurring_rule
            delta_days = (date_val - current_lesson.date).days

            # Фильтруем все неоплаченные/неотмененные будущие уроки этой серии
            future_lessons_qs = Lesson.objects.filter(
                recurring_rule=rule,
                date__gte=current_lesson.date
            ).exclude(
                payment_status=Lesson.PaymentStatus.PAID
            ).exclude(
                status=Lesson.Status.CANCELED
            )

            # Обновляем все уроки серии
            updated_count = 0
            for lesson_item in future_lessons_qs:
                lesson_item.student = student
                lesson_item.subject = subject
                lesson_item.start_time = start_time
                lesson_item.end_time = end_time
                lesson_item.price = price

                # Если сместили дату у редактируемого урока — сдвигаем всю серию на delta_days
                if delta_days != 0:
                    lesson_item.date = lesson_item.date + timedelta(days=delta_days)

                lesson_item.save()
                updated_count += 1

            # Обновляем параметры самого правила RecurringRule (на будущее)
            rule.student = student
            rule.subject = subject
            rule.start_time = start_time
            rule.end_time = end_time
            rule.price = price
            rule.save()

            return JsonResponse({
                'success': True,
                'message': f"Успешно обновлено уроков в серии: {updated_count}"
            })

        # ИНАЧЕ (редактирование только одного конкретного урока)
        lesson = current_lesson
    else:
        lesson = Lesson(teacher=teacher)

    # Сохраняем одиночный урок
    lesson.student_id = student_id
    lesson.subject_id = subject_id
    lesson.date = date_val
    lesson.start_time = start_time
    lesson.end_time = end_time
    lesson.price = price
    lesson.status = status
    lesson.payment_status = payment_status
    lesson.topic = topic
    lesson.save()

    return JsonResponse({'success': True, 'message': "Занятие сохранено"})


@login_required
@require_http_methods(['POST'])
def delete_lesson_api(request, lesson_id):
    """Удаление урока с учетом режимов серии"""
    teacher = request.user.teacher_profile
    lesson = get_object_or_404(Lesson, id=lesson_id, teacher=teacher)

    data = json.loads(request.body)
    mode = data.get('mode', 'this_only')  # 'this_only', 'future', 'all'

    delete_recurring_lessons(lesson, mode=mode)
    return JsonResponse({'success': True, 'message': "Урок удален"})
