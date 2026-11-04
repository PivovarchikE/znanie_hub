import operator
import random

from django.db import transaction

from courses.models import Homework, HomeworkFile

# Белый список операций: ничего, кроме этого, не вычисляется
ALLOWED_OPERATIONS = {
    '+': operator.add,
    '-': operator.sub,
}
MAX_ABS_VALUE = 1_000_000


def _safe_int(value, default):
    """Приводит значение из JSON-конфига к int и ограничивает диапазон."""
    try:
        return max(-MAX_ABS_VALUE, min(MAX_ABS_VALUE, int(value)))
    except (TypeError, ValueError):
        return default


def generate_math_tasks_addition_and_substraction(config_params):
    """
    Принимает словарь параметров, например: {"min": 1, "max": 20, "operations": ["+", "-"]}
    Возвращает список словарей с условием и ответом.
    """
    min_val = _safe_int(config_params.get('min'), 1)
    max_val = _safe_int(config_params.get('max'), 100)
    if min_val > max_val:
        min_val, max_val = max_val, min_val

    requested = config_params.get('operations') or ['+', '-']
    operations = [
        op for op in requested
        if isinstance(op, str) and op in ALLOWED_OPERATIONS
    ] or ['+', '-']

    problems = []
    for _ in range(5):   # TODO: в docstring и seed_db подразумевается 50 (params["count"])
        a = random.randint(min_val, max_val)
        b = random.randint(min_val, max_val)
        op = random.choice(operations)

        # Гарантируем неотрицательный результат для вычитания
        if op == '-' and a < b:
            a, b = b, a

        answer = ALLOWED_OPERATIONS[op](a, b)   # вместо eval(expression)

        problems.append({
            "question": f"{a} {op} {b}",
            "answer": str(answer),
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
