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
