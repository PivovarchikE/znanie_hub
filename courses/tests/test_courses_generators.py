import re
import pytest
from courses.generators import generate_tasks, PICKER_SCHEMAS, get_picker, sanitize_selection, describe_selection

ALL_OPS = ['mul_1', 'div_1', 'mul_2', 'div_2', 'mul_3', 'div_3', 'mixed', 'chain']


def evaluate(question):
    """Независимая проверка: считаем по обычным правилам приоритета."""
    return eval(question.replace('×', '*').replace('÷', '//').replace('−', '-'))


def test_table_single_factor_only_multiplication():
    tasks = generate_tasks({"kind": "multiplication_table"}, {"factor": "7"})
    assert tasks and all('×' in t["question"] and '÷' not in t["question"] for t in tasks)
    for t in tasks:
        a, b = (int(x) for x in t["question"].split(' × '))
        assert 7 in (a, b) and int(t["answer"]) == a * b


def test_table_all_has_40():
    assert len(generate_tasks({"kind": "multiplication_table"}, {"factor": "all"})) == 40


@pytest.mark.parametrize("level", ["easy", "medium", "hard"])
def test_chain_answers_are_exact_and_nonnegative(level):
    for _ in range(30):
        tasks = generate_tasks({"kind": "multiplication_division"},
                               {"operations": ["chain"], "level": level})
        for t in tasks:
            q = t["question"].replace('×', '*').replace('÷', '/').replace('−', '-')
            # каждое деление должно быть нацело: сравниваем точное и целочисленное значение
            assert eval(q) == eval(q.replace('/', '//')) == int(t["answer"]) >= 0


@pytest.mark.parametrize("op", ALL_OPS)
def test_every_operation_is_correct(op):
    tasks = generate_tasks({"kind": "multiplication_division"}, {"operations": [op]})
    assert tasks
    for t in tasks:
        assert evaluate(t["question"]) == int(t["answer"])


def test_division_two_digit_by_two_digit_shape():
    for t in generate_tasks({"kind": "multiplication_division", "count": 30}, {"operations": ["div_2"]}):
        a, b = (int(x) for x in t["question"].split(' ÷ '))
        assert 10 <= a <= 99 and 10 <= b <= 99 and a % b == 0


def test_locked_config_ignores_selection():
    params = {"kind": "multiplication_table", "locked": True, "factor": "7"}
    tasks = generate_tasks(params, {"factor": "3"})
    assert all('7' in t["question"].split(' × ') for t in tasks)
    assert get_picker(params) is None


def test_invalid_selection_does_not_crash():
    assert generate_tasks({"kind": "multiplication_division"}, {"operations": ["rm -rf"], "level": "zzz"})
    assert generate_tasks({"kind": "multiplication_table"}, {"factor": "abc"})


def test_pickers_exist_for_both_kinds():
    assert set(PICKER_SCHEMAS) == {"multiplication_table", "multiplication_division"}


def test_sanitize_drops_unknown_keys_and_validates():
    p = {"kind": "multiplication_table"}
    assert sanitize_selection(p, {"factor": "7", "evil": 1}) == {"factor": "7"}
    assert sanitize_selection(p, {}) == {"factor": "all"}
    with pytest.raises(ValueError):
        sanitize_selection(p, {"factor": "11"})


def test_sanitize_multi():
    p = {"kind": "multiplication_division"}
    assert sanitize_selection(p, {"operations": ["mul_2", "chain", "mul_2"], "level": "hard"}) == \
        {"operations": ["mul_2", "chain"], "level": "hard"}
    for bad in ({"operations": []}, {"operations": ["x"]}, {"operations": "mul_1"}):
        with pytest.raises(ValueError):
            sanitize_selection(p, bad)


def test_sanitize_returns_none_for_plain_config():
    assert sanitize_selection({"min": 1, "max": 10}, {"factor": "7"}) is None


def test_describe_selection():
    assert describe_selection({"kind": "multiplication_table"}, {"factor": "7"}) == "Умножение на 7"
    assert "Вся таблица" in describe_selection({"kind": "multiplication_table"}, {"factor": "all"})
    text = describe_selection({"kind": "multiplication_division"},
                              {"operations": ["mul_1", "chain"], "level": "medium"})
    assert "Операции" in text and "средний" in text