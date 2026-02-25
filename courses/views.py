import json

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout
from django.core.paginator import Paginator
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from courses.forms import HomeworkForm
from courses.models import Subject, Topic, TrainingSession, SimulatorConfig
from courses.services import generate_math_tasks_addition_and_substraction
from users import models
from users.models import StudentProfile


@require_GET
def index(request):
    return render(request, 'index.html')

@require_GET
def thanks(request):
    return render(request, 'thanks.html')


def math_index(request):
    # Получаем предмет именно с названием "Математика"
    # prefetch_related('sections__topics') оптимизирует запросы к БД
    subject = get_object_or_404(Subject.objects.prefetch_related('sections__topics'), name="Математика")

    context = {
        'subject': subject,
        'sections': subject.sections.all()
    }
    return render(request, 'math_index.html', context)


def topic_detail(request, topic_id):
    topic = get_object_or_404(Topic, pk=topic_id)

    if topic.content_type == 'simulator':
        configs = topic.configs.all()

        # Создаем словарь: id_конфига -> сгенерированные_задачи
        all_problems_data = {}
        for conf in configs:
            problems = generate_math_tasks_addition_and_substraction(conf.params)
            all_problems_data[str(conf.id)] = {
                'label': conf.label,
                'problems': problems
            }

        context = {
            'topic': topic,
            'configs': configs,
            # Передаем ВСЕ данные в один большой JSON-объект
            'all_configs_json': all_problems_data,
        }
        return render(request, 'simulator_setup.html', context)

    return render(request, 'theory_detail.html', {'topic': topic})


# сохранение тренировок для личных кабиентов
@login_required
def save_training_result(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)

            # Сопоставляем данные из JS с полями вашей модели
            TrainingSession.objects.create(
                student=request.user,  # В модели student, а не user
                config_id=data.get('config_id'),
                total_questions=data.get('total'),  # В модели total_questions
                solved_count=data.get('total'),  # Сколько всего решил
                correct_count=data.get('correct'),  # В модели correct_count
                detailed_results=data.get('details'),  # Наш JSON-список ответов
                end_time=timezone.now()  # Фиксируем время окончания
            )

            return JsonResponse({'status': 'success'})

        except Exception as e:
            print(f"Ошибка сохранения: {e}")
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

    return JsonResponse({'status': 'method not allowed'}, status=405)


@login_required
def teacher_dashboard_view(request):
    if request.user.role.slug != 'teacher':
        return redirect('index')  # пока учеников редиректим на стратовую

    # Получаем профиль учителя и его учеников
    teacher_profile = request.user.teacher_profile
    students = teacher_profile.my_students.all().select_related('user', 'school_class')

    return render(request, 'dashboard_teacher_index.html', {
        'students': students,
    })


@login_required
def student_detail_view(request, student_id):
    if request.user.role.slug != 'teacher':
        return redirect('index')

    # Получаем ученика, проверяя, что он привязан к текущему учителю
    student = get_object_or_404(StudentProfile, user_id=student_id, teacher=request.user.teacher_profile)

    # Получаем его домашние задания
    homeworks = student.homeworks.all().order_by('-created_at')

    return render(request, 'dashboard_teacher_detail_student.html', {
        'student': student,
        'homeworks': homeworks,
    })


@login_required
def add_homework_view(request, student_id):
    if request.user.role.slug != 'teacher':
        return redirect('index')

    student = get_object_or_404(StudentProfile, user_id=student_id, teacher=request.user.teacher_profile)

    if request.method == 'POST':
        form = HomeworkForm(request.POST)
        if form.is_valid():
            homework = form.save(commit=False)
            homework.student = student
            homework.teacher = request.user.teacher_profile
            homework.save()
            messages.success(request, f"Задание '{homework.title}' добавлено для {student.user.full_name}")
            return redirect('dashboard_teacher_detail_student.html', student_id=student.user.id)
    else:
        form = HomeworkForm()

    return render(request, 'dashboard_teacher_add_hw.html', {
        'form': form,
        'student': student
    })