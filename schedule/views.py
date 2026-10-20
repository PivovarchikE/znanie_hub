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

    if not teacher_profile:
        raise PermissionDenied("Доступ к расписанию есть только у учителей.")

    # 1. Список индивидуальных учеников
    my_students_qs = teacher_profile.my_students.select_related('user', 'school_class').all()
    students_data = [
        {
            'id': str(student.id),
            'name': student.user.full_name or student.user.username,
            'school_class': str(student.school_class.number) if student.school_class else None,
        }
        for student in my_students_qs
    ]

    # 2. Список активных групп с составом участников
    my_groups_qs = teacher_profile.student_groups.filter(status='active').prefetch_related('students__user').all()
    groups_data = [
        {
            'id': str(group.id),
            'name': group.name,
            'students': [
                {
                    'id': str(st.id),
                    'name': st.user.full_name or st.user.username
                }
                for st in group.students.all()
            ]
        }
        for group in my_groups_qs
    ]

    # 3. Список предметов учителя
    subjects_data = list(teacher_profile.subjects.values('id', 'name'))
    for sub in subjects_data:
        sub['id'] = str(sub['id'])

    context = {
        'students': students_data,
        'groups': groups_data,
        'subjects': subjects_data,
    }
    return render(request, 'schedule/schedule_list.html', context)


@login_required
@require_http_methods(['GET'])
def get_week_schedule_api(request):
    """API получения уроков и аналитики (поддерживает week и month)"""
    teacher = request.user.teacher_profile

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
    group_id = request.GET.get('group_id')

    if view_type == 'month':
        analytics_start = target_date.replace(day=1)
        _, last_day_num = monthrange(target_date.year, target_date.month)
        analytics_end = target_date.replace(day=last_day_num)

        start_date = analytics_start - timedelta(days=analytics_start.weekday())
        end_date = analytics_end + timedelta(days=(6 - analytics_end.weekday()))
    else:
        start_date = target_date - timedelta(days=target_date.weekday())
        end_date = start_date + timedelta(days=6)
        analytics_start = start_date
        analytics_end = end_date

    all_period_lessons = list(
        Lesson.objects.filter(
            teacher=teacher,
            date__range=[start_date, end_date]
        ).select_related('student__user', 'group', 'subject')
    )

    # Фильтрация уроков на сетке
    if student_id:
        display_lessons = [l for l in all_period_lessons if str(l.student_id) == str(student_id)]
    elif group_id:
        display_lessons = [l for l in all_period_lessons if str(l.group_id) == str(group_id)]
    else:
        display_lessons = all_period_lessons

    lessons_data = []

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
            'target_type': 'group' if l.group_id else 'student',
            'student_id': str(l.student_id) if l.student_id else None,
            'student_name': (l.student.user.full_name or l.student.user.username) if l.student_id else None,
            'group_id': str(l.group_id) if l.group_id else None,
            'group_name': l.group.name if l.group_id else None,
            'subject_id': str(l.subject_id) if l.subject_id else None,
            'subject_name': l.subject.name if l.subject else 'Без предмета',
            'date': l.date.strftime('%Y-%m-%d'),
            'start_time': l.start_time.strftime('%H:%M'),
            'end_time': l.end_time.strftime('%H:%M'),
            'status': str(l.status),
            'payment_status': str(l.payment_status),
            'price': float(l.price) if l.price else 0.0,
            'topic': l.topic or '',
            'is_recurring': bool(getattr(l, 'recurring_rule_id', None)),
            'is_overlapping': has_overlap
        })

    analytics = calculate_schedule_analytics(teacher, analytics_start, analytics_end, student_id)

    return JsonResponse({
        'period_start': start_date.strftime('%Y-%m-%d'),
        'period_end': end_date.strftime('%Y-%m-%d'),
        'lessons': lessons_data,
        'analytics': analytics
    })


@login_required
@require_http_methods(['POST'])
@transaction.atomic
def save_lesson_api(request):
    """API создания или редактирования урока"""
    teacher = request.user.teacher_profile
    data = json.loads(request.body)

    lesson_id = int(data['id']) if data.get('id') else None
    target_type = data.get('target_type', 'student')

    student_id = int(data['student_id']) if target_type == 'student' and data.get('student_id') else None
    group_id = int(data['group_id']) if target_type == 'group' and data.get('group_id') else None
    subject_id = int(data['subject_id']) if data.get('subject_id') else None

    date_val = datetime.strptime(data['date'], '%Y-%m-%d').date()
    start_time = datetime.strptime(data['start_time'], '%H:%M').time()
    end_time = datetime.strptime(data['end_time'], '%H:%M').time()
    price = Decimal(str(data.get('price', 0)))
    status = data.get('status', Lesson.Status.SCHEDULED)
    payment_status = data.get('payment_status', Lesson.PaymentStatus.UNPAID)
    topic = data.get('topic', '')

    is_recurring = data.get('is_recurring', False)
    update_mode = data.get('update_mode', 'this_only')
    force_save = data.get('force_save', False)

    # 1. Проверка на пересечение по времени
    overlap = check_lesson_overlap(teacher, date_val, start_time, end_time, exclude_lesson_id=lesson_id)

    if overlap and status != Lesson.Status.CANCELED and not force_save:
        if overlap.group:
            overlap_target = f"группой «{overlap.group.name}»"
        else:
            overlap_target = f"учеником {overlap.student.user.full_name or overlap.student.user.username}"

        return JsonResponse({
            'success': False,
            'warning_overlap': True,
            'message': f"Внимание! В {overlap.start_time.strftime('%H:%M')} у вас уже есть урок с {overlap_target}. Сохранить всё равно?"
        }, status=200)

    # 2. Создание новой серии уроков
    if is_recurring and not lesson_id:
        days_of_week = data.get('days_of_week', [date_val.weekday()])
        weeks_count = int(data.get('weeks_count', 4))
        end_date = date_val + timedelta(weeks=weeks_count)

        student = teacher.my_students.filter(id=student_id).first() if student_id else None
        group = teacher.student_groups.filter(id=group_id).first() if group_id else None
        subject = teacher.subjects.filter(id=subject_id).first() if subject_id else None

        create_recurring_lessons(
            teacher=teacher,
            student=student,
            group=group,
            subject=subject,
            days_of_week=days_of_week,
            start_time=start_time,
            end_time=end_time,
            price=price,
            start_date=date_val,
            end_date=end_date
        )
        return JsonResponse({'success': True, 'message': "Серия уроков успешно добавлена"})

    # 3. Сохранение одиночного урока или обновление серии
    if lesson_id:
        lesson = get_object_or_404(Lesson, id=lesson_id, teacher=teacher)
    else:
        lesson = Lesson(teacher=teacher)

    lesson.student_id = student_id
    lesson.group_id = group_id
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
