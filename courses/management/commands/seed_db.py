import os
import re

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from users.models import Role, SchoolClass
from courses.models import Subject, Section, Topic, SimulatorConfig


class Command(BaseCommand):
    help = 'Наполнение БД начальными данными'

    def handle(self, *args, **options):
        # Оборачиваем всё в транзакцию
        try:
            with transaction.atomic():
                self.stdout.write("Начало транзакции...")
                self.perform_seeding()
                self.stdout.write(self.style.SUCCESS("Транзакция успешно зафиксирована (Committed)!"))
        except Exception as e:
            # Если что-то пошло не так внутри perform_seeding,
            # управление попадет сюда, а в БД изменений не будет.
            self.stderr.write(self.style.ERROR(f"Произошла ошибка: {e}"))
            self.stderr.write(self.style.WARNING("База данных откачена до исходного состояния."))

    def perform_seeding(self):
        self.stdout.write("Проверка таблиц...")
        tables = connection.introspection.table_names()
        for model in [Role, SchoolClass, Subject, Section, Topic, SimulatorConfig]:
            if model._meta.db_table not in tables:
                self.stderr.write(f"Ошибка: Таблица {model._meta.db_table} не создана. Сначала выполните migrate.")
                return

        # --- Роли и Классы ---
        for slug, name in [('teacher', 'Учитель'), ('student', 'Ученик')]:
            Role.objects.get_or_create(slug=slug, defaults={'name': name})

        self.stdout.write(self.style.SUCCESS("Роли заполнены успешно"))

        for i in range(1, 12):
            SchoolClass.objects.get_or_create(number=i)

        self.stdout.write(self.style.SUCCESS("Классы заполнены успешно"))

        # --- Предметы ---
        math_subject, _ = Subject.objects.get_or_create(name='Математика')
        Subject.objects.get_or_create(name='Физика')
        Subject.objects.get_or_create(name='Химия')

        self.stdout.write(self.style.SUCCESS("Предметы заполнены успешно"))

        # --- Основные разделы (Level 0) ---
        section_arithmetic, _ = Section.objects.get_or_create(subject=math_subject, title='Арифметика', defaults={'order': 10})
        section_math, _ = Section.objects.get_or_create(subject=math_subject, title='Математика', defaults={'order': 20})
        section_algebra, _ = Section.objects.get_or_create(subject=math_subject, title='Алгебра', defaults={'order': 30})
        section_geometry, _ = Section.objects.get_or_create(subject=math_subject, title='Геометрия', defaults={'order': 40})

        self.stdout.write(self.style.SUCCESS("Основные разделы заполнены успешно"))

        # --- АРИФМЕТИКА ---
        arithmetic_list = [
            "Сложение и вычитание", "Таблица умножения", "Умножение и деление",
            "Устный счёт — развитие навыка считать без письменных вычислений",
            "Десятичный состав числа — разряды, десятки, сотни, разложение числа",
            "Единицы длины, массы, времени — измерения и перевод единиц",
            "Простейшие текстовые задачи — задачи на логику и арифметические действия"
        ]
        for i, topic in enumerate(arithmetic_list, start=1):
            Topic.objects.get_or_create(section=section_arithmetic, title=topic, defaults={'order': i * 10})

        # --- МАТЕМАТИКА (Классы как Level 1, Темы как Level 2, за исключением обыкновенных дробей в 5 классе) ---
        # 5 класс
        math_5_structure = [
                "Натуральные числа и действия — расширенные правила вычислений и свойства операций",
                "Делимость, простые и составные числа — признаки делимости, разложение на множители",
                "Обыкновенные дроби",
                "Начальные элементы геометрии — виды углов, многоугольники, окружность",
                "Площади простых фигур — формулы площади прямоугольника, треугольника, параллелограмма"
            ]

        # Создаем 5 класс как уровень 1
        section_5_class, _ = Section.objects.get_or_create(
            subject=math_subject, title="5 класс", parent=section_math, defaults={'order': 10}
        )

        # Проходим по списку и распределяем: что тема, а что раздел
        for i, item_title in enumerate(math_5_structure, start=1):
            current_order = i * 10

            if item_title == 'Обыкновенные дроби':
                # Создаем раздел "Обыкновенные дроби"
                section_fractions, _ = Section.objects.update_or_create(
                    subject=math_subject,
                    title=item_title,
                    parent=section_5_class,
                    defaults={'order': current_order}
                )

                # Наполняем темами
                fractions_topics = [
                    "Сложение и вычитание обыкновенных дробей и смешанных чисел",
                    "Умножение и деление обыкновенных дробей и смешанных чисел",
                    "Основные типы задач на части",
                    "Правильные и неправильные дроби. Смешанные числа. Сравнение и сокращение дробей",
                ]

                for j, subtopic_title in enumerate(fractions_topics, start=1):
                    Topic.objects.update_or_create(
                        section=section_fractions,
                        title=subtopic_title,
                        defaults={
                            'order': j * 10,
                        }
                    )
            else:
                # Создаем обычную тему
                Topic.objects.update_or_create(
                    section=section_5_class,
                    title=item_title,
                    defaults={
                        'order': current_order,
                    }
                )

        # 6 класс
        math_6_structure = {
            "6 класс": [
                "Десятичные дроби — вычисления, перевод между дробями и десятичной записью",
                "Проценты и задачи на проценты",
                "Координатная прямая — расположение чисел, координаты точек",
                "Пропорции и отношения — сравнение величин и решение задач через пропорции",
                "Начальные элементы алгебры — выражения, переменные, простые уравнения",
                "Работа с графиками — чтение простых графиков и построение зависимостей"
            ]
        }
        self._fill_hierarchy(math_subject, section_math, math_6_structure)


        # --- АЛГЕБРА --- #
        algebra_structure = {
            "7 класс": ["Степень с натуральным и целым показателями", "Выражения и их преобразования",
                        "Линейные уравнения. Линейные неравенства. Линейная функция"],
            "8 класс": ["Квадратные корни и их свойства. Действительные числа", "Квадратные уравнения",
                        "Квадратичная функция", "Функции: обратная, кубическая, модуля, подкоренная"],
            "9 класс": ["Рациональные выражения", "Функции", "Дробно-рациональные уравнения и неравенства",
                        "Прогрессии"],
            "10 класс": ["Тригонометрия", "Корень n-й степени из числа", "Производная"],
            "11 класс": ["Обобщение понятия степени", "Показательная функция", "Логарифмическая функция"]
        }
        self._fill_hierarchy(math_subject, section_algebra, algebra_structure)
        # Исключение: Тема на 1 уровне (напрямую в раздел Алгебра)
        Topic.objects.get_or_create(section=section_algebra, title="Повторение курса алгебры — подготовка к цэ/цт", defaults={'order':999})

        # --- ГЕОМЕТРИЯ ---
        geom_structure = {
            "7 класс": ["Начальные понятия геометрии", "Признаки равенства треугольников",
                        "Параллельность прямых на плоскости", "Сумма углов треугольника", "Задачи на построение"],
            "8 класс": ["Площади многоугольников и их свойства", "Подобие треугольников", "Окружность"],
            "9 класс": ["Соотношения в прямоугольном треугольнике", "Вписанные и описанные окружности",
                        "Теорема синусов, теорема косинусов", "Правильные многоугольники"],
            "10 класс": ["Введение в стереометрию", "Параллельность прямых и плоскостей",
                         "Перпендикулярность прямых и плоскостей", "Координаты и векторы в пространстве"],
            "11 класс": ["Призма и цилиндр", "Пирамида и конус", "Сфера и шар"]
        }
        self._fill_hierarchy(math_subject, section_geometry, geom_structure)
        # Исключение: Тема на 1 уровне (напрямую в раздел Геометрия)
        Topic.objects.get_or_create(section=section_geometry, title="Повторение — подготовка к цт/цэ", defaults={'order': 999})

        # --- Наполнение тем теорией ---

        base_dir = os.path.dirname(__file__)

        topics = Topic.objects.all()
        text_content_for_write = ''

        for topic in topics:
            clean_name = re.sub(r'[^a-zA-Zа-яА-ЯёЁ]+', '_', topic.title.lower().strip('_'))
            file_path = os.path.join(base_dir, 'theory_data', f"{clean_name}.html")

            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    text_content_for_write = f.read()

                Topic.objects.filter(title=topic).update(text_content=text_content_for_write,)
                self.stdout.write(self.style.SUCCESS(f"Теория для темы '{topic}' добавлена"))

        # --- ТРЕНАЖЕРЫ ---
        arith_topic = Topic.objects.filter(section=section_arithmetic, title="Сложение и вычитание").first()
        if arith_topic:
            sims = [
                ('до 20', {"max": 20, "min": 0, "count": 50}),
                ('до 100', {"max": 100, "min": 0, "count": 50}),
                ('до 1000', {"max": 1000, "min": 0, "count": 50}),
            ]
            for label, params in sims:
                SimulatorConfig.objects.get_or_create(
                    topic=arith_topic,
                    label=label,
                    defaults={'params': params, 'config_type': 'practice'}
                )

        self.stdout.write(self.style.SUCCESS("База данных успешно заполнена!"))

    def _fill_hierarchy(self, subject, parent_sec, structure):
        """Вспомогательный метод для создания подраздела (класс) и тем в нем"""
        section_order = 10
        for class_name, topics in structure.items():
            # Создаем подраздел (Level 1)
            subject_sec, _ = Section.objects.get_or_create(
                subject=subject,
                title=class_name,
                parent=parent_sec,
                defaults={'order': section_order}
            )

            section_order += 10
            self.stdout.write(f"  - Раздел '{subject_sec}' обработан.")
