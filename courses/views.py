import json
import sys

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, logger
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from courses.forms import HomeworkForm, HomeworkFileFormSet
from courses.models import Subject, Topic, TrainingSession, SimulatorConfig, Homework, Section
from courses.services import generate_math_tasks_addition_and_substraction
from users import models
from users.forms import StudentProfileForm, StudentEditForm, PhoneFormSet
from users.models import StudentProfile, TeacherProfile

import logging

logger = logging.getLogger(__name__)


@require_GET
def math_index(request):
    # Получаем предмет именно с названием "Математика"
    # prefetch_related('sections__topics') оптимизирует запросы к БД
    subject = get_object_or_404(Subject.objects.prefetch_related('sections__topics'), name="Математика")

    context = {
        'subject': subject,
        'sections': subject.sections.all()
    }
    return render(request, 'math_index.html', context)


@require_GET
def topic_detail(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)

    preset_config_id = request.GET.get('config')
    homework_id = request.GET.get('hw')

    # Если это тренажер
    if topic.content_type == 'simulator':
        configs = topic.configs.all()
        all_problems_data = {}

        for conf in configs:
            # Генерируем задачи для каждого конфига
            problems = generate_math_tasks_addition_and_substraction(conf.params)
            all_problems_data[str(conf.id)] = {
                'label': conf.label,
                'problems': problems
            }

        # Проверяем домашку, если ID передан
        is_completed = False
        if homework_id:
            homework = Homework.objects.filter(id=homework_id).first()
            if homework:
                is_completed = homework.is_completed

        context = {
            'topic': topic,
            'configs': configs,
            'all_configs_json': all_problems_data,
            'preset_config_id': preset_config_id,
            'homework_id': homework_id,
            'is_already_completed': is_completed,
        }
        return render(request, 'simulator_setup.html', context)

    # Если это теория (или любой другой тип)
    return render(request, 'theory_detail.html', {'topic': topic})


@login_required
@require_http_methods(["POST"])
def save_training_result(request):
    try:
        data = json.loads(request.body)
        homework_id = data.get('homework_id') # Получаем ID из JS

        # 1. Создаем запись о тренировке (общая статистика)
        session = TrainingSession.objects.create(
            student=request.user,
            config_id=data.get('config_id'),
            total_questions=data.get('total'),
            solved_count=data.get('total'),
            correct_count=data.get('correct'),
            detailed_results=data.get('details'),
            end_time=timezone.now()
        )

        total = session.total_questions
        correct = session.correct_count
        percent = int((correct / total) * 100) if total > 0 else 0

        # 2. Если тренировка запущена из ДЗ, отмечаем его как выполненное
        if homework_id:
            # Ищем домашку, которая принадлежит этому ученику
            homework = Homework.objects.filter(
                id=homework_id,
                student__user=request.user
            ).first()

            # ЕСЛИ ЗАДАНИЕ УЖЕ ВЫПОЛНЕНО - НЕ СОХРАНЯЕМ НОВЫЙ РЕЗУЛЬТАТ
            if homework and homework.is_completed:
                logger.warning(f"Homework {homework_id} marked as completed for {request.user} and don't saves")
                return JsonResponse({
                    'status': 'error',
                    'message': 'Задание уже было выполнено ранее. Повторное сохранение невозможно.'
                }, status=403)

            if homework:
                homework.is_completed = True
                homework.score = percent
                homework.save()
                logger.info(f"Homework {homework_id} marked as completed for {request.user}")

        logger.info(f"Save training result: session for {request.user} saved")
        return JsonResponse({'status': 'success'})

    except Exception as e:
        logger.error(f"Save training result error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def get_homework_results_api(request, hw_id):
    # Берем домашку (проверяем, что учитель имеет к ней доступ)
    homework = get_object_or_404(Homework, id=hw_id, teacher=request.user.teacher_profile)

    # Ищем сессию
    session = TrainingSession.objects.filter(
        student=homework.student.user,
        config=homework.simulator_config,
        end_time__isnull=False
    ).order_by('-end_time').first()

    if not session:
        # Если сессия не найдена
        return JsonResponse({
            'error': 'Сессия не найдена',
            'details': f'Student ID: {homework.student.user.id}, Config ID: {homework.simulator_config.id}'
        }, status=404)

    return JsonResponse({
        'title': homework.title,
        'results': session.detailed_results,
        'score': homework.score
    })


def get_sections(request):
    subject_id = request.GET.get('subject_id')
    sections = Section.objects.filter(subject_id=subject_id).values('id', 'title')
    return JsonResponse(list(sections), safe=False)


def get_topics(request):
    section_id = request.GET.get('section_id')
    topics = Topic.objects.filter(section_id=section_id).values('id', 'title')
    return JsonResponse(list(topics), safe=False)


def get_configs(request):
    topic_id = request.GET.get('topic_id')
    configs = SimulatorConfig.objects.filter(topic_id=topic_id).values('id', 'label')
    return JsonResponse(list(configs), safe=False)


@login_required
def teacher_dashboard_view(request):
    if request.user.role.slug != 'teacher':
        return redirect('index')  # пока учеников редиректим на стратовую

    # Получаем профиль учителя и его учеников
    teacher_profile = request.user.teacher_profile
    students = teacher_profile.my_students.filter(deleted_at__isnull=True).select_related('user', 'school_class')
    return render(request, 'dashboard_teacher_index.html', {
        'students': students,
    })


@login_required
def student_detail_view(request, student_id):
    if request.user.role.slug != 'teacher':
        return redirect('index')

    student = get_object_or_404(
        StudentProfile.objects.select_related('user'),
        id=student_id,
        teachers=request.user.teacher_profile
    )

    homeworks = student.homeworks.filter(deleted_at__isnull=True).order_by('-created_at')

    return render(request, 'dashboard_teacher_detail_student.html', {
        'student': student,
        'homeworks': homeworks,
    })


@login_required
def add_homework_view(request, student_id):
    """
    Создание домашнего задания с файлами.
    GET: Отображение форм.
    POST: Валидация, сохранение задания и файлов в одной транзакции.
    """
    # Проверка прав (Role-based access control)
    if not hasattr(request.user, 'role') or request.user.role.slug != 'teacher':
        logger.warning(f"User {request.user.id} attempted to access teacher view without permission.")
        messages.error(request, "Доступ только для учителей.")
        return redirect('index')

    student = get_object_or_404(
        StudentProfile,
        id=student_id,
        teachers=request.user.teacher_profile
    )

    # --- ОБРАБОТКА POST (LOGIC) ---
    if request.method == 'POST':
        logger.info(f"Teacher {request.user.id} is creating homework for student {student_id}")

        form = HomeworkForm(request.POST)
        formset = HomeworkFileFormSet(request.POST, request.FILES)

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    # Сохраняем основное задание
                    homework = form.save(commit=False)
                    homework.student = student
                    homework.teacher = request.user.teacher_profile
                    homework.save()

                    # Сохраняем M2M (если есть в форме)
                    form.save_m2m()

                    # Сохраняем файлы через формсет
                    instances = formset.save(commit=False)
                    for instance in instances:
                        instance.homework = homework
                        # Сохраняем оригинальное имя файла для логов
                        original_name = instance.file.name
                        instance.save()
                        logger.debug(f"File '{original_name}' attached to HW {homework.id}")

                    # Финализируем сохранение формсета (включая удаления)
                    formset.save_m2m()

                logger.info(f"Successfully created HW ID {homework.id} for student {student.user.id}")
                messages.success(request, f"Задание '{homework.title}' успешно отправлено!")
                return redirect('student_detail', student_id=student.id)

            except Exception as e:
                logger.error(f"Transaction failed while creating HW for student {student_id}: {str(e)}", exc_info=True)
                messages.error(request, "Системная ошибка при сохранении. Попробуйте позже.")
        else:
            logger.warning(
                f"Form validation failed for HW creation. Teacher: {request.user.id}, Errors: {form.errors} {formset.errors}")
            messages.error(request, "Пожалуйста, проверьте правильность заполнения полей.")

    # --- ОБРАБОТКА GET (DISPLAY) ---
    else:
        form = HomeworkForm()
        formset = HomeworkFileFormSet()
        logger.debug(f"Displaying empty homework form for student {student_id}")

    return render(request, 'dashboard_teacher_add_hw.html', {
        'form': form,
        'formset': formset,
        'student': student,
        'title': "Новое задание"
    })


@login_required
def homework_view_detail(request, hw_id):
    homework = get_object_or_404(
        Homework.objects.select_related(
            'subject',
            'section',
            'topic',
            'simulator_config',
            'student__user'
        ),
        id=hw_id
    )
    return render(request, 'homework_view_detail.html', {'homework': homework})


# Редактирование задания
@login_required
def edit_homework_view(request, hw_id):
    # Проверяем, что это учитель
    if not hasattr(request.user, 'teacher_profile'):
        return redirect('student_dashboard')  # Отправляем ученика домой

    homework = get_object_or_404(Homework, id=hw_id, teacher=request.user.teacher_profile)
    student = homework.student

    if request.method == 'POST':
        form = HomeworkForm(request.POST, instance=homework)
        formset = HomeworkFileFormSet(request.POST, request.FILES, instance=homework)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            return redirect('student_detail', student_id=student.id)
    else:
        form = HomeworkForm(instance=homework)
        formset = HomeworkFileFormSet(instance=homework)

    return render(request, 'dashboard_teacher_add_hw.html', {
        'form': form,
        'formset': formset,
        'student': student,
        'edit_mode': True
    })


@login_required
def delete_homework_view(request, hw_id):
    if not hasattr(request.user, 'role') or request.user.role.slug != 'teacher':
        return redirect('index')

    # Ищем задание, проверяя, что оно принадлежит именно этому учителю
    homework = get_object_or_404(Homework, id=hw_id, teacher=request.user.teacher_profile)
    student_id = homework.student.id

    if request.method == 'POST':
        homework.delete()
        homework.save()

        logger.info(f"Soft delete: Homework ID {hw_id} deactivated by teacher {request.user.id}")
        messages.success(request, f"Задание '{homework.title}' удалено.")
        return redirect('student_detail', student_id=student_id)

    return redirect('student_detail', student_id=student_id)


@login_required
@transaction.atomic
def edit_student_view(request, student_id):
    student_profile = get_object_or_404(
        StudentProfile.objects.select_related('user'),
        id=student_id,
        teachers=request.user.teacher_profile
    )
    user = student_profile.user
    role_slug = 'student'

    if request.method == 'POST':
        user_form = StudentEditForm(request.POST, instance=user)
        profile_form = StudentProfileForm(request.POST, instance=student_profile)
        phone_formset = PhoneFormSet(request.POST, instance=user, form_kwargs={'role_slug': role_slug})

        if user_form.is_valid() and profile_form.is_valid() and phone_formset.is_valid():
            user_form.save()
            profile_form.save()
            phone_formset.save()
            messages.success(request, f"Профиль {user.get_full_name()} обновлен.")
            return redirect('student_detail', student_id=student_profile.id)
    else:
        user_form = StudentEditForm(instance=user)
        profile_form = StudentProfileForm(instance=student_profile)
        phone_formset = PhoneFormSet(instance=user, form_kwargs={'role_slug': role_slug})
        if user.phones.exists():
            phone_formset.extra = 0

    return render(request, 'edit_student.html', {
        'user_form': user_form,
        'profile_form': profile_form,
        'phone_formset': phone_formset,
        'student': student_profile
    })


@login_required
@require_POST
def delete_student_view(request, student_id):
    student = get_object_or_404(
        StudentProfile,
        id=student_id,
        teachers=request.user.teacher_profile
    )

    teacher_profile = request.user.teacher_profile

    # Вместо удаления объекта, удаляем только связь с текущим учителем
    student.teachers.remove(teacher_profile)

    messages.success(
        request,
        f"Ученик {student.user.get_full_name()} успешно удален из вашего списка."
    )
    return redirect('teacher_dashboard')


@login_required
def student_dashboard_view(request):
    if request.user.role.slug != 'student':
        return redirect('index')

    student_profile = request.user.student_profile

    homeworks = Homework.objects.filter(
        student=student_profile,
        deleted_at__isnull=True
    ).select_related('teacher__user', 'subject').order_by('-created_at')

    teachers = student_profile.teachers.all().select_related('user').prefetch_related('subjects')

    logger.info(f'Student dashboard view: student {request.user} open dashboard')

    return render(request, 'student_dashboard.html', {
        'homeworks': homeworks,
        'teachers': teachers,
        'student': student_profile
    })

