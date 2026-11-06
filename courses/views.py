import json
import os
import sys
import uuid

from PIL import Image

from django.contrib import messages
from django.contrib.postgres.search import SearchVector
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files import File
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from courses.forms import HomeworkForm, HomeworkFileFormSet
from courses.models import Subject, Topic, TrainingSession, SimulatorConfig, Homework, Section, HomeworkResponseFile, \
    HomeworkComment, HomeworkFile
from courses.generators import generate_tasks, get_picker
from decorators import ajax_required
from users.models import StudentGroup
from users.forms import StudentProfileForm, StudentEditForm, PhoneFormSet
from users.models import StudentProfile, TeacherProfile

import logging


logger = logging.getLogger(__name__)


def _files_valid(form, formset):
    """Для типов без файлов формсет не проверяем и не сохраняем."""
    hw_type = form.cleaned_data.get('hw_type')
    return True if hw_type not in Homework.FILE_TYPES else formset.is_valid()


def _group_batch(group, teacher, hw):
    """Все ДЗ одного назначения группе (старые записи без batch_id ищем по полям)."""
    if hw.batch_id:
        return Homework.objects.filter(group=group, teacher=teacher, batch_id=hw.batch_id)
    return Homework.objects.filter(group=group, teacher=teacher, batch_id__isnull=True,
                                   title=hw.title, subject=hw.subject, hw_type=hw.hw_type)


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
    if preset_config_id and not preset_config_id.isdigit():
        preset_config_id = None

    all_configs = topic.configs.all()

    is_completed = False
    current_homework = None

    # Домашнее задание подтягиваем только для авторизованного ученика-владельца
    is_teacher_preview = False
    if homework_id and homework_id.isdigit() and request.user.is_authenticated:
        current_homework = Homework.objects.filter(
            Q(student__user=request.user) | Q(teacher__user=request.user),
            id=homework_id,
        ).select_related('student__user', 'teacher__user').first()

        if current_homework:
            is_teacher_preview = current_homework.student.user_id != request.user.id
            is_completed = current_homework.is_completed and not is_teacher_preview
            if not preset_config_id and current_homework.simulator_config:
                preset_config_id = str(current_homework.simulator_config.id)

    all_problems_data = {}

    hw_settings = None
    if current_homework and current_homework.hw_type == 'simulator':
        hw_settings = current_homework.simulator_settings or None

    for conf in all_configs:
        fixed_by_hw = bool(hw_settings) and conf.id == current_homework.simulator_config_id
        if conf.config_type == 'exam':
            problems = conf.params.get('fixed_tasks', [])
        else:
            problems = generate_tasks(conf.params, hw_settings if fixed_by_hw else None)

        all_problems_data[str(conf.id)] = {
            'label': conf.label,
            'config_type': conf.config_type,
            'problems': problems,
            'picker': None if fixed_by_hw else get_picker(conf.params),
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
        'homework_settings_label': current_homework.simulator_settings_label if current_homework else '',
        'is_teacher_preview': is_teacher_preview,
        'homework_type': current_homework.hw_type if current_homework else None,

        # Данные для JS-скрипта тренажера
        'preset_config_id': preset_config_id,
        'homework_id': current_homework.id if current_homework else None,
        'is_already_completed': is_completed,
        'current_homework': current_homework,
    }

    return render(request, 'topic_universal_view.html', context)


@require_GET
@ajax_required
def generate_tasks_api(request):
    """Генерирует задания по выбору ученика (какая таблица, какие операции и т.д.)."""
    conf = get_object_or_404(SimulatorConfig, pk=request.GET.get('config_id') or 0, config_type='practice')
    selection = {}
    if 'factor' in request.GET:
        selection['factor'] = request.GET['factor']
    if 'operations' in request.GET:
        selection['operations'] = [o for o in request.GET['operations'].split(',') if o]
    if 'level' in request.GET:
        selection['level'] = request.GET['level']
    return JsonResponse({'problems': generate_tasks(conf.params, selection)})


@login_required
@require_http_methods(["POST"])
def save_training_result(request):
    try:
        data = json.loads(request.body)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'bad json'}, status=400)

    try:
        hw = None
        if data.get('homework_id'):
            hw = (Homework.objects
                  .filter(Q(student__user=request.user) | Q(teacher__user=request.user),
                          id=data['homework_id'])
                  .select_related('student__user').first())
            if not hw:
                return JsonResponse({'status': 'error', 'message': 'ДЗ не найдено'}, status=404)

            # Учитель проходит задание как предпросмотр: ничего не сохраняем
            if hw.student.user_id != request.user.id:
                return JsonResponse({'status': 'success', 'preview': True})

            if hw.uses_files:
                return JsonResponse({'status': 'error',
                                     'message': 'Это задание проверяет учитель'}, status=400)
            if hw.is_completed:
                return JsonResponse({'status': 'error', 'message': 'Задание уже выполнено'}, status=403)

        # Интерактивная теория: просто отметка о прохождении
        if data.get('is_theory_only'):
            if hw and hw.hw_type == 'interactive_theory':
                hw.complete_automatically(100)
            elif hw:
                return JsonResponse({'status': 'error', 'message': 'Неверный тип задания'}, status=400)
            return JsonResponse({'status': 'success'})

        if hw and hw.hw_type != 'simulator':
            return JsonResponse({'status': 'error', 'message': 'Неверный тип задания'}, status=400)
        if hw and str(hw.simulator_config_id) != str(data.get('config_id')):
            return JsonResponse({'status': 'error', 'message': 'Неверный конфиг'}, status=400)

        with transaction.atomic():
            session = TrainingSession.objects.create(
                student=request.user,
                config_id=data.get('config_id'),
                total_questions=data.get('total', 0),
                solved_count=data.get('total', 0),
                correct_count=data.get('correct', 0),
                detailed_results=data.get('details', []),
                end_time=timezone.now(),
            )
            if hw:
                total = session.total_questions
                percent = int(session.correct_count / total * 100) if total else 0
                hw.complete_automatically(percent)

        return JsonResponse({'status': 'success'})
    except Exception as e:
        logger.error(f"Save training result error: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'Ошибка сервера'}, status=500)


@login_required
@require_GET
@ajax_required
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
@ajax_required
def get_sections(request):
    subject_id = request.GET.get('subject_id')
    sections = Section.objects.filter(subject_id=subject_id, parent__isnull=True)
    data = [{'id': s.id, 'title': s.title} for s in sections]
    return JsonResponse(data, safe=False)


@require_GET
@ajax_required
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
@ajax_required
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


@require_GET
@ajax_required
def get_configs(request):
    configs = SimulatorConfig.objects.filter(topic_id=request.GET.get('topic_id'))
    return JsonResponse(
        [{'id': c.id, 'label': c.label, 'picker': get_picker(c.params)} for c in configs],
        safe=False,
    )


@login_required
@require_GET
def teacher_dashboard_view(request):
    if request.user.role.slug != 'teacher':
        return redirect('index')  # пока учеников редиректим на стратовую

    # Получаем профиль учителя и его учеников
    teacher_profile = request.user.teacher_profile
    students = teacher_profile.my_students.filter(deleted_at__isnull=True).select_related('user', 'school_class')
    groups = StudentGroup.objects.filter(teacher=teacher_profile)
    return render(request, 'dashboard_teacher_index.html', {
        'groups': groups,
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
        # Логируем входящие данные (без чувствительной инфы)
        logger.info(f"Processing HW submission: Teacher={request.user.id}, Student={student.user.id}")

        form = HomeworkForm(request.POST)
        formset = HomeworkFileFormSet(request.POST, request.FILES, prefix='files')

        if form.is_valid() and _files_valid(form, formset):
            try:
                with transaction.atomic():
                    homework = form.save(commit=False)
                    homework.student = student
                    homework.teacher = request.user.teacher_profile
                    homework.save()

                    # Сохранение файлов
                    if homework.uses_files:
                        for instance in formset.save(commit=False):
                            instance.homework = homework
                            instance.save()
                            logger.debug(f"File attached: HW_ID={homework.id}, File={instance.file.name}")


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
        formset = HomeworkFileFormSet(prefix='files')

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
        Homework.objects.filter(
            Q(student__user=request.user) | Q(teacher__user=request.user)
        ).select_related('student__user', 'teacher__user', 'topic', 'subject',
                         'section', 'simulator_config').prefetch_related('files'),
        id=hw_id,
    )
    is_teacher = homework.teacher.user_id == request.user.id

    launch_url = None
    if homework.is_auto_checked and homework.topic_id:
        launch_url = f"{reverse('topic_detail', args=[homework.topic_id])}?hw={homework.id}"
        if homework.simulator_config_id:
            launch_url += f"&config={homework.simulator_config_id}"

    return render(request, 'homework_view_detail.html', {
        'homework': homework, 'is_teacher': is_teacher, 'launch_url': launch_url,
    })


@login_required
def edit_homework_view(request, hw_id):
    """Редактирование задания"""
    if not hasattr(request.user, 'teacher_profile'):
        return redirect('student_dashboard')  # Отправляем ученика домой

    homework = get_object_or_404(Homework, id=hw_id, teacher=request.user.teacher_profile)
    student = homework.student

    if request.method == 'POST':
        form = HomeworkForm(request.POST, instance=homework)
        formset = HomeworkFileFormSet(request.POST, request.FILES, instance=homework, prefix='files')
        if form.is_valid() and _files_valid(form, formset):
            with transaction.atomic():
                homework = form.save(commit=False)
                homework.student = student
                homework.teacher = request.user.teacher_profile
                homework.save()
                if homework.uses_files:
                    for instance in formset.save(commit=False):
                        instance.homework = homework
                        instance.save()
                    for obj in formset.deleted_objects:
                        obj.delete()
                else:
                    homework.files.all().delete()
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


ALLOWED_IMAGE_FORMATS = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif'}
MAX_RESPONSE_FILE_SIZE = 10 * 1024 * 1024   # 10 МБ
MAX_RESPONSE_FILES = 10


def _clean_response_image(uploaded):
    """Проверяет, что файл — настоящая картинка разрешённого формата, и задаёт безопасное имя."""
    if uploaded.size > MAX_RESPONSE_FILE_SIZE:
        raise ValidationError(f"Файл «{uploaded.name}» больше 10 МБ.")
    try:
        img = Image.open(uploaded)
        img.verify()
        fmt = img.format
    except Exception:
        raise ValidationError(f"Файл «{uploaded.name}» не является изображением.")
    finally:
        uploaded.seek(0)

    ext = ALLOWED_IMAGE_FORMATS.get(fmt)
    if not ext:
        raise ValidationError(f"Формат файла «{uploaded.name}» не поддерживается.")

    # Расширение берём из реального формата, имя заменяем на случайное
    uploaded.name = f"{uuid.uuid4().hex}.{ext}"
    return uploaded


@login_required
@require_http_methods(['POST', 'GET'])
def upload_hw_response(request, hw_id):
    homework = get_object_or_404(Homework, id=hw_id, student__user=request.user)

    if request.method == 'POST':
        files = request.FILES.getlist('files')
        if not files:
            messages.warning(request, "Вы не выбрали ни одного файла.")
            return redirect('homework_view_detail', hw_id=hw_id)

        if len(files) > MAX_RESPONSE_FILES:
            messages.error(request, f"Можно загрузить не более {MAX_RESPONSE_FILES} файлов за раз.")
            return redirect('homework_view_detail', hw_id=hw_id)

        try:
            cleaned = [_clean_response_image(f) for f in files]
        except ValidationError as e:
            messages.error(request, e.messages[0])
            return redirect('homework_view_detail', hw_id=hw_id)

        for f in cleaned:
            HomeworkResponseFile.objects.create(homework=homework, file=f)

        messages.success(request, f"Успешно загружено файлов: {len(cleaned)}. Ожидайте проверки учителем.")

    return redirect('homework_view_detail', hw_id=hw_id)


@login_required
@require_POST
def grade_homework(request, hw_id):
    homework = get_object_or_404(Homework, id=hw_id, teacher__user=request.user)
    if homework.is_auto_checked:
        messages.error(request, "Это задание проверяется автоматически.")
        return redirect('homework_view_detail', hw_id=hw_id)

    action = request.POST.get('action')
    comment_text = (request.POST.get('teacher_comment') or '').strip()
    raw_score = (request.POST.get('actual_score') or '').strip()

    # Разрешаем действие 'correction' (и 'reject' на всякий случай)
    if action not in ('accept', 'correction', 'reject'):
        messages.error(request, "Неизвестное действие.")
        return redirect('homework_view_detail', hw_id=hw_id)

    score = None
    if raw_score and action == 'accept':
        try:
            score = int(raw_score)
        except ValueError:
            score = None
        if score is None or not 0 <= score <= 10:
            messages.error(request, "Балл должен быть целым числом от 0 до 10.")
            return redirect('homework_view_detail', hw_id=hw_id)

    if action == 'accept' and homework.needs_score and score is None:
        messages.error(request, "Необходимо выставить балл для принятия работы.")
        return redirect('homework_view_detail', hw_id=hw_id)

    with transaction.atomic():
        # Комментарий учителя сохраняется в любом случае
        if comment_text:
            HomeworkComment.objects.create(
                homework=homework, author=request.user, text=comment_text
            )

        if action == 'accept':
            homework.status = 'completed'
            homework.is_completed = True
            if homework.hw_type == 'theory':
                homework.is_theory_read = True
            else:
                homework.actual_score = score
        elif action in ('correction', 'reject'):
            # Логика отправки на доработку
            homework.status = 'correction'
            homework.is_completed = False
            if homework.hw_type == 'theory':
                homework.is_theory_read = False
            else:
                homework.actual_score = None

        homework.save()
        messages.success(request, "Статус задания успешно обновлен.")

    return redirect('homework_view_detail', hw_id=hw_id)


@login_required
@require_POST
def mark_theory_read(request, hw_id):
    homework = get_object_or_404(Homework, id=hw_id, teacher__user=request.user)

    if not homework.is_completed:
        homework.is_theory_read = True
        homework.is_completed = True
        # Для теории баллы не выставляем
        homework.save()
        messages.success(request, f"Теория по теме «{homework.title}» подтверждена.")

    return redirect('homework_view_detail', hw_id=hw_id)


@login_required
@require_http_methods(['POST', 'GET'])
def submit_homework(request, hw_id):
    homework = get_object_or_404(Homework, id=hw_id, student__user=request.user)
    if request.method == 'POST' and homework.uses_files and not homework.is_completed:
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

    # Группы, в которых состоит ученик (завершённые не показываем). Чтобы показать - убираем active статус
    groups = (StudentGroup.objects
              .filter(students=student_profile, status='active')
              .select_related('teacher__user')
              .prefetch_related('students')
              .order_by('name'))

    logger.info(f'Student dashboard view: student {request.user} open dashboard')

    return render(request, 'student_dashboard.html', {
        'homeworks': homeworks,
        'teachers': teachers,
        'groups': groups,
        'student': student_profile
    })


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

@login_required
def search_students_and_groups_api(request):
    """Эндпоинт для автокомплита в календаре / при назначении ДЗ"""
    query = request.GET.get('q', '').strip()
    teacher = request.user.teacher_profile

    students = StudentProfile.objects.filter(teachers=teacher)
    groups = StudentGroup.objects.filter(teacher=teacher, status='active')

    if query:
        students = students.filter(
            Q(user__first_name__icontains=query) |
            Q(user__last_name__icontains=query) |
            Q(user__username__icontains=query)
        )
        groups = groups.filter(name__icontains=query)

    data = {
        'students': [
            {'id': s.id, 'name': s.user.get_full_name() or s.user.username, 'class': str(s.school_class)}
            for s in students[:10]
        ],
        'groups': [
            {'id': g.id, 'name': g.name, 'students_count': g.students.count()}
            for g in groups[:10]
        ]
    }
    return JsonResponse(data)


@login_required
def group_add_hw_view(request, group_id):
    teacher_profile = getattr(request.user, 'teacher_profile', None)
    if not teacher_profile:
        messages.error(request, "Доступ разрешен только преподавателям.")
        return redirect('teacher_dashboard')

    group = get_object_or_404(StudentGroup, pk=group_id, teacher=teacher_profile)

    if group.status != 'active':
        messages.warning(request, "Нельзя назначать ДЗ группе со статусом «Обучение завершено».")
        return redirect('group_detail', pk=group.pk)

    all_students = group.students.all()
    if not all_students.exists():
        messages.warning(request, f'В группе "{group.name}" нет учеников.')
        return redirect('group_detail', pk=group.pk)

    if request.method == 'POST':
        form = HomeworkForm(request.POST)

        selected_student_ids = [int(sid) for sid in request.POST.getlist('selected_students') if sid.isdigit()]
        target_students = all_students.filter(id__in=selected_student_ids)

        if not selected_student_ids:
            messages.error(request, "Выберите хотя бы одного ученика для назначения домашнего задания.")

        topic_id = request.POST.get('topic')
        section_id = request.POST.get('section')

        if topic_id:
            form.fields['topic'].queryset = Topic.objects.filter(pk=topic_id)
        if section_id:
            form.fields['section'].queryset = Section.objects.filter(pk=section_id)

        formset = HomeworkFileFormSet(request.POST, request.FILES, prefix='files')

        # Проверяем файлы с учетом типа задания (как для индивидуального ДЗ)
        hw_type = form.data.get('hw_type')
        files_valid = True if hw_type not in Homework.FILE_TYPES else formset.is_valid()

        if selected_student_ids and form.is_valid() and files_valid:
            with transaction.atomic():
                batch_id = uuid.uuid4()
                created_homeworks = []
                for student in target_students:
                    hw = Homework(
                        subject=form.cleaned_data.get('subject'),
                        section=form.cleaned_data.get('section'),
                        topic=form.cleaned_data.get('topic'),
                        hw_type=form.cleaned_data.get('hw_type'),
                        title=form.cleaned_data.get('title'),
                        content=form.cleaned_data.get('content'),
                        simulator_config=form.cleaned_data.get('simulator_config'),
                        batch_id=batch_id,
                        deadline=form.cleaned_data.get('deadline'),
                        teacher=teacher_profile,
                        student=student,
                        group=group,
                        status='pending',
                        simulator_settings=form.cleaned_data.get('simulator_settings'),
                    )
                    created_homeworks.append(hw)

                created_homeworks = Homework.objects.bulk_create(created_homeworks)

                # Собираем файлы из валидного формсета (если тип задания их поддерживает)
                files_to_save = []
                if hw_type in Homework.FILE_TYPES and formset.is_valid():
                    files_to_save = [
                        f.cleaned_data.get('file')
                        for f in formset.forms
                        if f.cleaned_data and f.cleaned_data.get('file') and not f.cleaned_data.get('DELETE', False)
                    ]

                # Безопасное сохранение файлов: для каждого ученика создается своя копия на диске,
                # чтобы удаление у одного не стирало файл у других.
                if files_to_save and created_homeworks:
                    for uploaded_file in files_to_save:
                        for hw in created_homeworks:
                            uploaded_file.seek(0)
                            HomeworkFile.objects.create(
                                homework=hw,
                                file=File(uploaded_file, name=uploaded_file.name),
                                original_name=uploaded_file.name
                            )

            messages.success(request, f'Домашнее задание успешно назначено {len(created_homeworks)} ученикам группы "{group.name}"!')
            return redirect('group_detail', pk=group.pk)
        else:
            if not selected_student_ids:
                pass
            else:
                messages.error(request, "Пожалуйста, исправьте ошибки в форме.")
    else:
        form = HomeworkForm()
        formset = HomeworkFileFormSet(prefix='files')
        selected_student_ids = list(all_students.values_list('id', flat=True))

    return render(request, 'group_add_hw.html', {
        'form': form,
        'formset': formset,
        'group': group,
        'selected_student_ids': selected_student_ids,
    })


@login_required
def group_edit_hw_view(request, group_id, homework_id):
    teacher_profile = getattr(request.user, 'teacher_profile', None)
    if not teacher_profile:
        messages.error(request, "Доступ разрешен только преподавателям.")
        return redirect('teacher_dashboard')

    group = get_object_or_404(StudentGroup, pk=group_id, teacher=teacher_profile)
    all_students = group.students.all()

    base_hw = get_object_or_404(Homework, pk=homework_id, group=group, teacher=teacher_profile)

    group_homeworks = _group_batch(group, teacher_profile, base_hw)
    if not base_hw.batch_id:
        # старый пакет без номера: присваиваем ему номер один раз
        new_batch = uuid.uuid4()
        group_homeworks.update(batch_id=new_batch)
        base_hw.batch_id = new_batch
        group_homeworks = _group_batch(group, teacher_profile, base_hw)

    if request.method == 'POST':
        form = HomeworkForm(request.POST, instance=base_hw)
        selected_student_ids = [int(sid) for sid in request.POST.getlist('selected_students') if sid.isdigit()]

        if not selected_student_ids:
            messages.error(request, "Выберите хотя бы одного ученика.")

        topic_id = request.POST.get('topic')
        section_id = request.POST.get('section')

        if topic_id:
            form.fields['topic'].queryset = Topic.objects.filter(pk=topic_id)
        if section_id:
            form.fields['section'].queryset = Section.objects.filter(pk=section_id)

        formset = HomeworkFileFormSet(request.POST, request.FILES, instance=base_hw, prefix='files')

        hw_type = form.data.get('hw_type')
        files_valid = True if hw_type not in Homework.FILE_TYPES else formset.is_valid()

        if selected_student_ids and form.is_valid() and files_valid:
            with transaction.atomic():
                updated_fields = {
                    'subject': form.cleaned_data.get('subject'),
                    'section': form.cleaned_data.get('section'),
                    'topic': form.cleaned_data.get('topic'),
                    'hw_type': form.cleaned_data.get('hw_type'),
                    'title': form.cleaned_data.get('title'),
                    'content': form.cleaned_data.get('content'),
                    'simulator_config': form.cleaned_data.get('simulator_config'),
                    'deadline': form.cleaned_data.get('deadline'),
                    'simulator_settings': form.cleaned_data.get('simulator_settings')
                }

                # 1. Удаляем ДЗ у учеников, с которых сняли галочку
                removed_homeworks = group_homeworks.exclude(student_id__in=selected_student_ids)
                if removed_homeworks.exists():
                    HomeworkFile.objects.filter(homework__in=removed_homeworks).delete()
                    for hw in removed_homeworks: hw.delete()

                # 2. Обновляем существующие записи у выбранных учеников
                remaining_homeworks = group_homeworks.filter(student_id__in=selected_student_ids)
                remaining_homeworks.update(**updated_fields)

                # 3. Сохраняем файлы в base_hw (если поддерживается)
                if hw_type in Homework.FILE_TYPES:
                    formset.save()
                else:
                    base_hw.files.all().delete()

                # 4. Жесткая защита от дубликатов: проверяем по БД, у кого из выбранных учеников
                # УЖЕ ФАКТИЧЕСКИ ЕСТЬ задание из этого пакета, чтобы не плодить дубликаты
                existing_student_ids = set(
                    _group_batch(group, teacher_profile, base_hw)
                    .filter(student_id__in=selected_student_ids)
                    .values_list('student_id', flat=True)
                )

                new_student_ids = set(selected_student_ids) - existing_student_ids

                # 5. Создаем новые записи только для тех учеников, у которых их действительно еще не было
                if new_student_ids:
                    new_students = all_students.filter(id__in=new_student_ids)
                    new_hws = []
                    for st in new_students:
                        new_hws.append(Homework(
                            teacher=teacher_profile,
                            student=st,
                            group=group,
                            batch_id=base_hw.batch_id,
                            status='pending',
                            **updated_fields
                        ))
                    Homework.objects.bulk_create(new_hws)

                # 6. Синхронизация файлов для остальных учеников группы
                all_current_homeworks = _group_batch(group, teacher_profile, base_hw)
                other_homeworks = all_current_homeworks.exclude(pk=base_hw.pk)

                if other_homeworks.exists():
                    base_files = HomeworkFile.objects.filter(homework=base_hw)
                    HomeworkFile.objects.filter(homework__in=other_homeworks).delete()

                    if base_files.exists() and hw_type in Homework.FILE_TYPES:
                        new_shared_files = []
                        for hw in other_homeworks:
                            for b_file in base_files:
                                if b_file.file:
                                    try:
                                        b_file.file.open('rb')
                                        file_copy = File(b_file.file, name=b_file.original_name or os.path.basename(
                                            b_file.file.name))
                                        new_shared_files.append(
                                            HomeworkFile(
                                                homework=hw,
                                                file=file_copy,
                                                original_name=b_file.original_name
                                            )
                                        )
                                    except Exception:
                                        pass
                        if new_shared_files:
                            HomeworkFile.objects.bulk_create(new_shared_files)

            messages.success(request, f'Домашнее задание для группы "{group.name}" успешно обновлено!')
            return redirect('group_detail', pk=group.pk)
        else:
            if not selected_student_ids:
                pass
            else:
                messages.error(request, "Пожалуйста, исправьте ошибки в форме.")
    else:
        initial_data = {}
        if base_hw.topic:
            initial_data['subject'] = base_hw.topic.section.subject.id
            initial_data['section'] = base_hw.topic.section.id
            initial_data['topic'] = base_hw.topic.id

        form = HomeworkForm(instance=base_hw, initial=initial_data)

        subject_id = base_hw.topic.section.subject.id if base_hw.topic else (
            base_hw.section.subject.id if base_hw.section else None)
        if subject_id:
            form.fields['section'].queryset = Section.objects.filter(subject_id=subject_id)
        if base_hw.section_id:
            form.fields['topic'].queryset = Topic.objects.filter(section_id=base_hw.section_id)

        formset = HomeworkFileFormSet(instance=base_hw, prefix='files')
        selected_student_ids = list(group_homeworks.values_list('student_id', flat=True))

    return render(request, 'group_add_hw.html', {
        'form': form,
        'formset': formset,
        'group': group,
        'is_edit': True,
        'homework': base_hw,
        'selected_student_ids': selected_student_ids,
    })

@login_required
@require_POST
def group_delete_hw_view(request, group_id, homework_id):
    teacher_profile = getattr(request.user, 'teacher_profile', None)
    if not teacher_profile:
        raise PermissionDenied("Доступ разрешен только преподавателям.")

    group = get_object_or_404(StudentGroup, pk=group_id, teacher=teacher_profile)
    target_hw = get_object_or_404(
        Homework, pk=homework_id, group=group, teacher=teacher_profile
    )

    with transaction.atomic():
        batch = _group_batch(group, teacher_profile, target_hw)
        for hw in batch:
            hw.delete()   # soft delete с каскадом по связанным объектам

    messages.success(
        request,
        f'Домашнее задание "{target_hw.title}" успешно удалено для всех учеников группы.'
    )
    return redirect('group_detail', pk=group.pk)