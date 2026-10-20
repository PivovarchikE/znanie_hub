import random

from django.db import transaction

from courses.models import Homework, HomeworkFile


def generate_math_tasks_addition_and_substraction(config_params):
    """
    Принимает словарь параметров, например: {"min": 1, "max": 20, "operations": ["+", "-"]}
    Возвращает список из 50 словарей с условием и ответом.
    """
    problems = []
    min_val = config_params.get('min', 1)
    max_val = config_params.get('max', 100)
    operations = config_params.get('operations', ['+', '-'])

    for _ in range(5):
        a = random.randint(min_val, max_val)
        b = random.randint(min_val, max_val)
        op = random.choice(operations)

        # Гарантируем положительный результат для вычитания, если нужно
        if op == '-' and a < b:
            a, b = b, a

        expression = f"{a} {op} {b}"
        answer = eval(expression)

        problems.append({
            "question": expression,
            "answer": str(answer)
        })
    return problems


@transaction.atomic
def assign_homework_to_group(teacher_profile, group, homework_data, files=None):
    students = group.students.all()
    created_homeworks = []

    for student in students:
        hw = Homework.objects.create(
            teacher=teacher_profile,
            student=student,
            group=group,
            **homework_data
        )
        if files:
            for f in files:
                HomeworkFile.objects.create(homework=hw, file=f)
        created_homeworks.append(hw)

    return created_homeworks
