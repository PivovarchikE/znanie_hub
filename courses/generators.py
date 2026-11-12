import random

from courses.services import generate_math_tasks_addition_and_substraction


def _int(value, lo, hi, default):
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _unique(make, count):
    """Собирает до count уникальных примеров; make() -> (вопрос, ответ)."""
    seen, result = set(), []
    for _ in range(count * 40):
        question, answer = make()
        if question in seen:
            continue
        seen.add(question)
        result.append({"question": question, "answer": str(answer)})
        if len(result) >= count:
            break
    return result


# ====================== ТАБЛИЦА УМНОЖЕНИЯ ======================

def generate_multiplication_table_tasks(params):
    """
    params:
      factor     — "1".."10" или "all" (по умолчанию "all")
      count      — число примеров для одной таблицы (по умолчанию 20)
      all_count  — число примеров для «всей таблицы» (по умолчанию 40)
    Только умножение. Сомножители выдаются в обоих порядках (7 × 3 и 3 × 7).
    """
    choice = str(params.get('factor', 'all'))
    if choice == 'all':
        # «вся таблица»: сомножители 2..10, 40 случайных примеров
        pairs = [(a, b) for a in range(2, 11) for b in range(2, 11)]
        count = _int(params.get('all_count'), 1, 81, 40)
    else:
        n = _int(choice, 1, 10, 1)
        # Генерация примеров строго для выбранного множителя n (например, n × 1 ... n × 10 и 1 × n ... 10 × n)
        pairs = [(n, b) for b in range(1, 11)] + [(b, n) for b in range(1, 11)]
        # Убираем дубликаты (например, если n * n) и перемешиваем
        pairs = list(set(pairs))
        count = _int(params.get('count'), 1, 19, 19)

    random.shuffle(pairs)
    # Берем нужное количество (или все доступные, если их меньше count)
    selected_pairs = pairs[:min(count, len(pairs))]
    return [{"question": f"{a} × {b}", "answer": str(a * b)} for a, b in selected_pairs]


# ====================== УМНОЖЕНИЕ И ДЕЛЕНИЕ ======================

SIMPLE_OPS = ('mul_1', 'div_1', 'mul_2', 'div_2', 'mul_3', 'div_3')
ALL_OPS = SIMPLE_OPS + ('mixed', 'chain')

LEVELS = {
    #            размеры (разрядность) сомножителей  диапазон «+/−»   диапазон делителей в цепочке
    'easy':   {'pairs': [(1, 1)],                 'add': (1, 9),     'div': (2, 9)},
    'medium': {'pairs': [(2, 1), (2, 2), (3, 1)], 'add': (10, 99),   'div': (2, 99)},
    'hard':   {'pairs': [(3, 2), (3, 3)],         'add': (100, 999), 'div': (10, 999)},
}


def _digits(d):
    lo, hi = {1: (2, 9), 2: (10, 99), 3: (100, 999)}[d]
    return random.randint(lo, hi)


def _mul(kind):
    if kind == 'mul_1':      # многозначное × однозначное
        a, b = random.randint(10, 999), random.randint(2, 9)
        if random.random() < 0.5:
            a, b = b, a
    elif kind == 'mul_2':
        a, b = random.randint(10, 99), random.randint(10, 99)
    else:                    # mul_3
        a, b = random.randint(100, 999), random.randint(100, 999)
    return f"{a} × {b}", a * b


def _div(kind):
    """Делимое строится из делителя и частного, значит деление всегда нацело."""
    if kind == 'div_1':      # на однозначное
        b = random.randint(2, 9)
        q = random.randint(max(2, -(-10 // b)), 999 // b)
    elif kind == 'div_2':    # двузначное ÷ двузначное
        b = random.randint(10, 49)
        q = random.randint(2, 99 // b)
    else:                    # div_3: трёхзначное ÷ трёхзначное
        b = random.randint(100, 499)
        q = random.randint(2, 999 // b)
    return f"{b * q} ÷ {b}", q


def _term(level):
    """Один шаг × или ÷ с размерами чисел по уровню."""
    da, db = random.choice(LEVELS[level]['pairs'])
    x, y = _digits(da), _digits(db)
    if random.random() < 0.5:
        x, y = y, x
    if random.random() < 0.5:
        return f"{x} × {y}", x * y
    return f"{x * y} ÷ {y}", x


def _chain(level, actions):
    """Цепочка слева направо: a × b ÷ c [× d ...], каждое деление нацело."""
    cfg = LEVELS[level]
    da, db = random.choice(cfg['pairs'])
    a, b = _digits(da), _digits(db)
    text, value = f"{a} × {b}", a * b
    for i in range(actions - 1):
        if i == 0 or random.random() < 0.5:
            lo, hi = cfg['div']
            divisors = [d for d in range(lo, hi + 1) if value % d == 0 and value // d >= 2]
            if divisors:
                d = random.choice(divisors)
                text += f" ÷ {d}"
                value //= d
                continue
        n = _digits(1)
        text += f" × {n}"
        value *= n
    return text, value


def _expression(level):
    """2–3 действия: × ÷ + −. Результат всегда целый и неотрицательный."""
    lo, hi = LEVELS[level]['add']

    def const():
        v = random.randint(lo, hi)
        return str(v), v

    if random.random() < 0.5:   # 2 действия
        shape = random.choice(('term_c', 'c_term', 'chain'))
        if shape == 'chain':
            return _chain(level, 2)
        items = [_term(level), const()]
        if shape == 'c_term':
            items.reverse()
    else:                       # 3 действия
        shape = random.choice(('term_term', 'chain_c', 'chain3'))
        if shape == 'chain3':
            return _chain(level, 3)
        if shape == 'term_term':
            items = [_term(level), _term(level)]
        else:
            items = [_chain(level, 2), const()]
            random.shuffle(items)

    op = random.choice(('+', '-'))
    (t1, v1), (t2, v2) = items
    if op == '-' and v1 < v2:
        (t1, v1), (t2, v2) = (t2, v2), (t1, v1)
    return f"{t1} {op.replace('-', '−')} {t2}", (v1 + v2 if op == '+' else v1 - v2)


def _make(kind, level):
    if kind == 'mixed':
        kind = random.choice(SIMPLE_OPS)
    if kind == 'chain':
        return _expression(level)
    return _mul(kind) if kind.startswith('mul') else _div(kind)


def generate_mult_div_tasks(params):
    """
    params:
      operations — список из: mul_1, div_1, mul_2, div_2, mul_3, div_3, mixed, chain
      level      — easy | medium | hard (только для chain)
      count      — число примеров (1..50, по умолчанию 20)
    """
    raw = params.get('operations')
    ops = [o for o in (raw if isinstance(raw, list) else []) if o in ALL_OPS] or ['mul_1']
    level = params.get('level') if params.get('level') in LEVELS else 'easy'
    count = _int(params.get('count'), 1, 50, 20)
    return _unique(lambda: _make(random.choice(ops), level), count)


# ====================== РЕЕСТР И ВЫБОР НА ФРОНТЕ ======================

# kind -> (генератор, какие ключи разрешено менять выбором на фронте)
KINDS = {
    'multiplication_table': (generate_multiplication_table_tasks, ('factor',)),
    'multiplication_division': (generate_mult_div_tasks, ('operations', 'level')),
}

# Описание формы выбора, которое рисует task_picker.js
PICKER_SCHEMAS = {
    'multiplication_table': {
        'mode': 'single', 'key': 'factor', 'title': 'На что умножаем?', 'default': 'all',
        'options': [{'value': str(n), 'label': str(n)} for n in range(1, 11)]
                   + [{'value': 'all', 'label': 'Вся таблица умножения'}],
    },
    'multiplication_division': {
        'mode': 'multi', 'key': 'operations', 'title': 'Выберите типы операций',
        'default': ['mul_1'],
        'options': [
            {'value': 'mul_1', 'label': '✖️ Умножение на однозначное'},
            {'value': 'div_1', 'label': '➗ Деление на однозначное'},
            {'value': 'mul_2', 'label': '✖️ Двузначное × Двузначное'},
            {'value': 'div_2', 'label': '➗ Двузначное ÷ Двузначное'},
            {'value': 'mul_3', 'label': '✖️ Трёхзначное × Трёхзначное'},
            {'value': 'div_3', 'label': '➗ Трёхзначное ÷ Трёхзначное'},
            {'value': 'mixed', 'label': '🔀 Смешанные действия (умножение и деление вразброс)'},
            {'value': 'chain', 'label': '⛓ Цепочки действий (2–3 действия, все числа делятся нацело)'},
        ],
        'level': {
            'key': 'level', 'shown_when': 'chain', 'title': 'Сложность цепочек', 'default': 'easy',
            'options': [
                {'value': 'easy', 'label': 'Лёгкий — однозначные числа: 3 × 2 + 5'},
                {'value': 'medium', 'label': 'Средний — до трёхзначных на однозначные, двузначные на двузначные: 12 × 5 + 48 ÷ 16'},
                {'value': 'hard', 'label': 'Сложный — трёхзначные на двузначные и трёхзначные'},
            ],
        },
    },
}


def get_picker(params):
    """Схема выбора для фронта; None, если у конфига выбор отключен ("locked": true)."""
    params = params or {}
    if params.get('locked'):
        return None
    return PICKER_SCHEMAS.get(params.get('kind'))


def generate_tasks(params, selection=None, count=None):
    """
    Единая точка входа. selection — выбор ученика с фронта; применяется только к
    разрешенным ключам и только если конфиг не заблокирован учителем ("locked": true).
    count — количество заданий из SimulatorConfig.tasks_count (перекрывает count в params).
    """
    params = params or {}
    if count:
        params = {**params, 'count': count, 'all_count': count}
    entry = KINDS.get(params.get('kind'))
    if not entry:
        return generate_math_tasks_addition_and_substraction(params)
    generator, allowed = entry
    if selection and not params.get('locked'):
        params = {**params, **{k: v for k, v in selection.items() if k in allowed and v is not None}}
    return generator(params)


def sanitize_selection(params, selection):
    """
    Проверяет настройки, пришедшие с формы учителя, и оставляет только известные ключи.
    Возвращает чистый словарь, None для конфигов без выбора, ValueError при мусоре.
    """
    schema = PICKER_SCHEMAS.get((params or {}).get('kind'))
    if not schema:
        return None
    selection = selection if isinstance(selection, dict) else {}
    allowed = {o['value'] for o in schema['options']}
    key = schema['key']

    if schema['mode'] == 'single':
        value = str(selection.get(key, schema['default']))
        if value not in allowed:
            raise ValueError('Недопустимое значение')
        return {key: value}

    raw = selection.get(key, schema['default'])
    if not isinstance(raw, list) or not raw or any(v not in allowed for v in raw):
        raise ValueError('Выберите хотя бы один тип операций')
    result = {key: list(dict.fromkeys(raw))}

    level = schema.get('level')
    if level:
        level_value = selection.get(level['key'], level['default'])
        if level_value not in {o['value'] for o in level['options']}:
            raise ValueError('Недопустимая сложность')
        result[level['key']] = level_value
    return result


def describe_selection(params, selection):
    schema = PICKER_SCHEMAS.get((params or {}).get('kind'))
    if not schema or not isinstance(selection, dict):
        return ''
    labels = {o['value']: o['label'] for o in schema['options']}
    raw = selection.get(schema['key'])

    if schema['mode'] == 'single':
        value = str(raw)
        if value == 'all':
            return labels['all']
        return f"Умножение на {value}" if value in labels else ''

    values = [v for v in (raw if isinstance(raw, list) else []) if v in labels]
    if not values:
        return ''
    text = "Операции: " + ", ".join(labels[v] for v in values)
    level = schema.get('level')
    if level and level['shown_when'] in values:
        names = {'easy': 'легкий', 'medium': 'средний', 'hard': 'сложный'}
        text += f"; цепочки — {names.get(selection.get(level['key']), '')}"
    return text