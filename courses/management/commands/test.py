import re

from courses.models import Topic

topics_list = [
                "Десятичные дроби — вычисления, перевод между дробями и десятичной записью",
                "Проценты и задачи на проценты",
                "Координатная прямая — расположение чисел, координаты точек",
                "Пропорции и отношения — сравнение величин и решение задач через пропорции",
                "Начальные элементы алгебры — выражения, переменные, простые уравнения",
                "Работа с графиками — чтение простых графиков и построение зависимостей"
            ]

for topic in topics_list:
    # clean_name = re.sub(r'[^\w\s]', '', topic.lower()).replace(' ', '_')
    clean_name = re.sub(r'[^a-zA-Zа-яА-ЯёЁ]+', '_', topic.lower().strip('_'))
    print(clean_name)


topics = Topic.objects.all()

for topic in topics:
    print(topic)