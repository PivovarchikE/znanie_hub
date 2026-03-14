import pytest

from courses.models import Subject, Section, Topic
from users.models import Role


@pytest.fixture
def teacher_role(db):
    return Role.objects.create(name="Учитель", slug="teacher")


@pytest.fixture
def student_role(db):
    return Role.objects.create(name="Ученик", slug="student")


@pytest.fixture
def teacher_user(db):
    from users.models import User, Role, TeacherProfile
    role = Role.objects.create(name="Учитель", slug="teacher")
    user = User.objects.create_user(username="teacher_bill", password="password")
    user.role = role
    user.save()
    TeacherProfile.objects.create(user=user)
    return user


@pytest.fixture
def student_user(db):
    from users.models import User, Role, StudentProfile
    role = Role.objects.create(name="Ученик", slug="student")
    user = User.objects.create_user(username="student_max", password="password")
    user.role = role
    user.save()
    StudentProfile.objects.create(user=user)
    return user


@pytest.fixture
def subject(db):
    return Subject.objects.create(name="Математика")


@pytest.fixture
def section(subject):
    return Section.objects.create(subject=subject, title="Арифметика", order=1)


@pytest.fixture
def topic(section):
    return Topic.objects.create(section=section, title="Сложение", order=1)


@pytest.fixture
def simulator_config(topic):
    from courses.models import SimulatorConfig
    return SimulatorConfig.objects.create(
        topic=topic,
        label="Тест сложения",
        config_type="practice",
        params={"min_val": 1, "max_val": 10, "count": 5}
    )

@pytest.fixture
def homework(student_user, teacher_user, subject, topic, simulator_config):
    from courses.models import Homework
    return Homework.objects.create(
        student=student_user.student_profile,
        teacher=teacher_user.teacher_profile,
        subject=subject,
        topic=topic,
        simulator_config=simulator_config,
        title="ДЗ по математике",
        hw_type="simulator"
    )