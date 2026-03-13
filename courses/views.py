import json
import sys

from django.contrib import messages
from django.contrib.postgres.search import SearchVector
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import logger
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from courses.forms import HomeworkForm, HomeworkFileFormSet
from courses.models import Subject, Topic, TrainingSession, SimulatorConfig, Homework, Section, HomeworkResponseFile, \
    HomeworkComment
from courses.services import generate_math_tasks_addition_and_substraction
from users import models
from users.forms import StudentProfileForm, StudentEditForm, PhoneFormSet
from users.models import StudentProfile, TeacherProfile

import logging

logger = logging.getLogger(__name__)


@require_GET
def math_index(request):
    subject = get_object_or_404(
        Subject.objects.prefetch_related(
            'sections__topics',
            'sections__subsections__topics',
            'sections__subsections__subsections__topics'
        ),
        name="Математика"
    )

    root_sections = subject.sections.filter(parent__isnull=True)

    context = {
        'subject': subject,
        'sections': root_sections
    }
    return render(request, 'math_index.html', context)


@require_GET
def topic_detail(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)

    homework_id = request.GET.get('hw')
    preset_config_id = request.GET.get('config')
    all_configs = topic.configs.all()

    is_completed = False
    current_homework = None

    if homework_id:
        current_homework = Homework.objects.filter(
            id=homework_id,
            student__user=request.user
        ).first()

        if current_homework:
            is_completed = current_homework.is_completed
            # Если в URL не было конфига, берем его из домашки
            if not preset_config_id and current_homework.simulator_config:
                preset_config_id = str(current_homework.simulator_config.id)

    all_problems_data = {}

    for conf in all_configs:
        # Логика генерации (случайные или фиксированные)
        if conf.config_type == 'exam':
            problems = conf.params.get('fixed_tasks', [])
        else:
            problems = generate_math_tasks_addition_and_substraction(conf.params)

        all_problems_data[str(conf.id)] = {
            'label': conf.label,
            'config_type': conf.config_type,
            'problems': problems
        }

    raw_content = topic.text_content or ""
    slides = [s.strip() for s in raw_content.split('===') if s.strip()]

    context = {
        'topic': topic,
        'slides': slides,
        'slides_count': len(slides),
        'configs': all_configs,
        'practice_configs': all_configs.filter(config_type='practice'),
        'exam_configs': all_configs.filter(config_type='exam'),
        'all_configs_json': all_problems_data,

        # Данные для JS-скрипта тренажера
        'preset_config_id': preset_config_id,
        'homework_id': homework_id,
        'is_already_completed': is_completed,
        'current_homework': current_homework,
    }

    return render(request, 'topic_universal_view.html', context)


@login_required
@require_http_methods(["POST"])
def save_training_result(request):
    try:
        data = json.loads(request.body)
        homework_id = data.get('homework_id')
        is_theory_only = data.get('is_theory_only', False)

        # --- БЛОК ОБРАБОТКИ ТЕОРИИ ---
        if is_theory_only and homework_id:
            homework = Homework.objects.filter(
                id=homework_id,
                student__user=request.user
            ).first()

            if homework:
                if homework.is_completed:
                    return JsonResponse({'status': 'success', 'message': 'Уже выполнено'})

                homework.is_completed = True
                homework.score = 100
                homework.save()
                logger.info(f"Теория ДЗ {homework_id} отмечена как прочитанная для {request.user}")
                return JsonResponse({'status': 'success'})
            return JsonResponse({'status': 'error', 'message': 'ДЗ не найдено'}, status=404)

        # --- СТАНДАРТНАЯ ЛОГИКА ТРЕНАЖЕРА ---
        # Создаем запись о тренировке
        session = TrainingSession.objects.create(
            student=request.user,
            config_id=data.get('config_id'),
            total_questions=data.get('total', 0),
            solved_count=data.get('total', 0),
            correct_count=data.get('correct', 0),
            detailed_results=data.get('details', []),
            end_time=timezone.now()
        )

        total = session.total_questions
        correct = session.correct_count
        percent = int((correct / total) * 100) if total > 0 else 0

        # Обработка ДЗ для тренажера
        if homework_id:
            homework = Homework.objects.filter(
                id=homework_id,
                student__user=request.user
            ).first()

            if homework:
                # Проверка на соответствие конфига (только для тренажеров)
                if str(homework.simulator_config_id) != str(data.get('config_id')):
                    return JsonResponse({'status': 'error', 'message': 'Неверный конфиг'}, status=400)

                if homework.is_completed:
                    return JsonResponse({'status': 'error', 'message': 'Задание уже выполнено'}, status=403)

                homework.is_completed = True
                homework.score = percent
                homework.save()

        return JsonResponse({'status': 'success'})

    except Exception as e:
        logger.error(f"Save training result error: {e}")
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


@login_required
def get_homework_results_api(request, hw_id):
    homework = get_object_or_404(Homework, id=hw_id)

    is_student_owner = homework.student.user == request.user

    is_teacher_owner = False
    if hasattr(request.user, 'teacher_profile'):
        if homework.teacher == request.user.teacher_profile:
            is_teacher_owner = True

    if not (is_student_owner or is_teacher_owner):
        return JsonResponse({'error': 'Доступ запрещен'}, status=403)

    session = TrainingSession.objects.filter(
        student=homework.student.user,
        config=homework.simulator_config,
        end_time__isnull=False
    ).order_by('-end_time').first()

    if not session:
        return JsonResponse({
            'error': 'Сессия не найдена',
            'details': f'Student ID: {homework.student.user.id}, Config ID: {homework.simulator_config.id}'
        }, status=404)

    return JsonResponse({
        'title': homework.title,
        'results': session.detailed_results,
        'score': homework.score
    })


@require_GET
def get_sections(request):
    subject_id = request.GET.get('subject_id')
    sections = Section.objects.filter(subject_id=subject_id, parent__isnull=True)
    data = [{'id': s.id, 'title': s.title} for s in sections]
    return JsonResponse(data, safe=False)


@require_GET
def get_topics(request):
    """Проверка параметров темы (теория, конфиги) через JS"""
    section_id = request.GET.get('section_id')
    if not section_id:
        return JsonResponse([], safe=False)

    # Собираем все темы раздела и его прямых подразделов в плоский список
    # (нужно для быстрой проверки наличия теории в JS)
    topics = Topic.objects.filter(
        section_id=section_id
    ) | Topic.objects.filter(
        section__parent_id=section_id
    )

    data = [{
        'id': t.id,
        'title': t.title,
        'has_theory': bool(t.text_content and t.text_content.strip()),
        'parent_id': t.section_id
    } for t in topics]

    return JsonResponse(data, safe=False)


@login_required
@require_GET
def get_section_accordion(request):
    section_id = request.GET.get('section_id')
    logger.debug(f"AJAX: Fetching accordion for Section ID {section_id} (Requested by User {request.user.id})")

    try:
        section = get_object_or_404(Section, id=section_id)
        return render(request, 'includes/section_recursive_selectable.html', {
            'current_section': section
        })
    except Exception as e:
        logger.error(f"AJAX ERROR: Failed to render accordion for Section {section_id}. Error: {e}")
        return HttpResponse("Ошибка загрузки списка тем", status=500)


def get_configs(request):
    topic_id = request.GET.get('topic_id')
    configs = SimulatorConfig.objects.filter(topic_id=topic_id).values('id', 'label')
    return JsonResponse(list(configs), safe=False)


@login_required
@require_GET
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
@require_GET
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
@require_http_methods(['POST', 'GET'])
def add_homework_view(request, student_id):
    # Логируем попытку доступа к странице
    logger.info(f"User ID {request.user.id} (Teacher) accessed HW creation page for Student ID {student_id}")

    if not hasattr(request.user, 'role') or request.user.role.slug != 'teacher':
        logger.warning(f"Access denied: User {request.user.id} tried to create HW without teacher role.")
        messages.error(request, "Доступ только для учителей.")
        return redirect('index')

    student = get_object_or_404(
        StudentProfile,
        id=student_id,
        teachers=request.user.teacher_profile
    )

    if request.method == 'POST':
        # Логируем входящие данные (без чувствительной инфы, если нужно)
        logger.info(f"Processing HW submission: Teacher={request.user.id}, Student={student.user.id}")

        form = HomeworkForm(request.POST)
        formset = HomeworkFileFormSet(request.POST, request.FILES)

        if form.is_valid() and formset.is_valid():
            try:
                with transaction.atomic():
                    homework = form.save(commit=False)
                    homework.student = student
                    homework.teacher = request.user.teacher_profile
                    homework.save()

                    form.save_m2m()  # Для тегов или других ManyToMany

                    # Сохранение файлов
                    instances = formset.save(commit=False)
                    for instance in instances:
                        instance.homework = homework
                        instance.save()
                        logger.debug(f"File attached: HW_ID={homework.id}, File={instance.file.name}")

                    formset.save_m2m()

                logger.info(
                    f"SUCCESS: HW ID {homework.id} created for Student {student.user.id} by Teacher {request.user.id}")
                messages.success(request, f"Задание '{homework.title}' успешно отправлено!")
                return redirect('student_detail', student_id=student.id)

            except Exception as e:
                # Логируем критическую ошибку транзакции с трейсбеком
                logger.error(f"DATABASE ERROR: Transaction failed for Student {student_id}. Error: {str(e)}",
                             exc_info=True)
                messages.error(request, "Системная ошибка при сохранении в базу данных.")
        else:
            # Логируем ошибки валидации, чтобы знать, на чем спотыкаются учителя
            logger.warning(
                f"VALIDATION FAILED: Teacher={request.user.id}. Form errors: {form.errors.as_json()}. Formset errors: {formset.errors}")
            messages.error(request, "Пожалуйста, проверьте правильность заполнения полей.")

    else:
        form = HomeworkForm()
        formset = HomeworkFileFormSet()

    return render(request, 'dashboard_teacher_add_hw.html', {
        'form': form,
        'formset': formset,
        'student': student,
        'title': "Новое задание"
    })


@login_required
@require_http_methods(['GET', 'POST'])
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


@login_required
def edit_homework_view(request, hw_id):
    """Редактирование задания"""
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
@require_http_methods(['POST'])
def grade_practice(request, pk):
    homework = get_object_or_404(Homework, pk=pk, teacher=request.user.teacherprofile)
    if request.method == 'POST':
        score = request.POST.get('actual_score')
        homework.actual_score = score
        homework.is_completed = True
        homework.save()
        return redirect('homework_view_detail', pk=pk)


@login_required
@require_http_methods(['POST', 'GET'])
def upload_hw_response(request, hw_id):
    homework = get_object_or_404(Homework, id=hw_id)

    if request.method == 'POST':
        files = request.FILES.getlist('files')
        if not files:
            messages.warning(request, "Вы не выбрали ни одного файла.")
            return redirect('homework_view_detail', pk=hw_id)

        for f in files:
            HomeworkResponseFile.objects.create(homework=homework, file=f)

        messages.success(request, f"Успешно загружено файлов: {len(files)}. Ожидайте проверки учителем.")

    return redirect('homework_view_detail', hw_id=hw_id)


@login_required
@require_http_methods(['POST', 'GET'])
def grade_homework(request, hw_id):
    homework = get_object_or_404(Homework, id=hw_id)
    if request.method == 'POST' and request.user.role.slug == 'teacher':
        action = request.POST.get('action')
        score = request.POST.get('actual_score')
        comment_text = request.POST.get('teacher_comment')

        if comment_text:
            HomeworkComment.objects.create(
                homework=homework,
                author=request.user,
                text=comment_text
            )

        if action == 'accept':
            homework.status = 'completed'
            homework.is_completed = True
            homework.actual_score = score
        elif action == 'reject':
            homework.status = 'correction'
            homework.is_completed = False

        homework.save()
    return redirect('homework_view_detail', hw_id=hw_id)


@login_required
@require_http_methods(['POST', 'GET'])
def mark_theory_read(request, hw_id):
    homework = get_object_or_404(Homework, id=hw_id)

    if request.user.role.slug == 'teacher' and not homework.is_completed:
        if request.method == 'POST':
            homework.is_completed = True
            # Для теории баллы не выставляем (остается None или 0)
            homework.save()
            messages.success(request, f"Теория по теме «{homework.title}» подтверждена.")

    return redirect('homework_view_detail', hw_id=hw_id)


@login_required
@require_http_methods(['POST', 'GET'])
def submit_homework(request, hw_id):
    homework = get_object_or_404(Homework, id=hw_id, student__user=request.user)
    if request.method == 'POST':
        comment_text = request.POST.get('student_comment')
        if comment_text:
            HomeworkComment.objects.create(
                homework=homework,
                author=request.user,
                text=comment_text
            )

        homework.status = 'review'
        homework.save()
        messages.success(request, "Работа отправлена на проверку!")
    return redirect('homework_view_detail', hw_id=hw_id)


@login_required
@require_http_methods(['POST', 'GET'])
def delete_homework_view(request, hw_id):
    if not hasattr(request.user, 'role') or request.user.role.slug != 'teacher':
        return redirect('index')

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
@require_http_methods(['POST', 'GET'])
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
@require_GET
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


@login_required
@require_GET
def global_search_view(request):
    query = request.GET.get('q', '').strip()

    if len(query) < 2:
        return render(request, 'partials/search_dropdown.html', {'results': None})

    results = {
        'subjects': Subject.objects.filter(
            name__icontains=query,
            deleted_at__isnull=True
        ),
        'sections': Section.objects.filter(
            Q(title__icontains=query),
            deleted_at__isnull=True
        ).select_related('subject'),
        'topics': Topic.objects.filter(
            Q(title__icontains=query) | Q(text_content__icontains=query),
            deleted_at__isnull=True
        ).select_related('section__subject'),
        'simulators': SimulatorConfig.objects.filter(
            Q(label__icontains=query) | Q(params__icontains=query),
            deleted_at__isnull=True
        ).select_related('topic'),
    }

    context = {'results': results, 'query': query}

    if request.htmx:
        return render(request, 'partials/search_dropdown.html', context)

    try:
        return render(request, 'search_full_results.html', context)
    except:
        return render(request, 'partials/search_dropdown.html', context)
