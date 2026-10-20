import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.timezone import now, timedelta
from users.models import User, Role, UserPhoneNumber, SchoolClass


@pytest.mark.django_db
class TestBaseModelSoftDelete:
    """Тестирование логики мягкого удаления"""

    def test_soft_delete_marks_deleted_at(self, teacher_role):
        role = teacher_role
        role.delete()

        assert role.deleted_at is not None
        assert role.is_deleted is True
        # Проверяем, что objects.all() не видит удаленную запись
        assert Role.objects.count() == 0
        # Проверяем, что через all_objects запись доступна
        assert Role.all_objects.count() == 1

    def test_restore_model(self, teacher_role):
        role = teacher_role
        role.delete()
        role.restore()

        assert role.deleted_at is None
        assert Role.objects.count() == 1


@pytest.mark.django_db
def test_user_soft_delete_logic(teacher_user):
    """Проверка, что пользователь не исчезает из базы физически"""
    user_id = teacher_user.id

    teacher_user.delete()

    assert User.objects.filter(id=user_id).count() == 0

    deleted_user = User.all_objects.get(id=user_id)
    assert deleted_user.deleted_at is not None
    assert isinstance(deleted_user.deleted_at, timezone.datetime)


@pytest.mark.django_db
def test_cascade_soft_delete_issue(teacher_user):
    """
    Проверяем, что происходит со связанными данными.
    Если в модели ForeignKey стоит on_delete=models.CASCADE,
    то при удалении юзера его телефоны могут удалиться ФИЗИЧЕСКИ.
    """
    phone = UserPhoneNumber.objects.create(
        user=teacher_user,
        number="+375291234567"
    )

    teacher_user.delete()

    phone_exists = UserPhoneNumber.all_objects.filter(id=phone.id).exists()

    # Если этот ассерт упадет — значит номер удален из таблицы полностью
    assert phone_exists, "Связанный телефон был удален физически! CASCADE сработал мимо Soft Delete."


@pytest.mark.django_db
class TestUserModel:
    """Тестирование модели User"""

    def test_full_name_property(self, teacher_role):
        user = User(
            username="test_user",
            first_name="Евгений",
            last_name="Пивоварчик",
            middle_name="Александрович",
            role=teacher_role
        )
        assert user.full_name == "Пивоварчик Евгений Александрович"

    def test_date_of_birth_future_validation(self, teacher_role):
        future_date = now().date() + timedelta(days=1)
        user = User(username="user", date_of_birth=future_date, role=teacher_role)

        with pytest.raises(ValidationError) as excinfo:
            user.full_clean()
        assert 'date_of_birth' in excinfo.value.message_dict


@pytest.mark.django_db
class TestUserPhoneNumber:
    """Тестирование сложной логики номеров телефонов"""

    def test_phone_regex_validation(self, db, admin_user):
        # Неверный формат (без тире или не +375)
        invalid_phone = "+375291234567"
        phone = UserPhoneNumber(user=admin_user, number=invalid_phone)

        with pytest.raises(ValidationError):
            phone.full_clean()

    def test_first_phone_becomes_primary_automatically(self, db, admin_user):
        phone = UserPhoneNumber.objects.create(
            user=admin_user,
            number="+375-29-111-22-33"
        )
        assert phone.is_primary is True

    def test_only_one_primary_phone(self, db, admin_user):
        phone1 = UserPhoneNumber.objects.create(
            user=admin_user, number="+375-29-111-11-11", is_primary=True
        )
        phone2 = UserPhoneNumber.objects.create(
            user=admin_user, number="+375-29-222-22-22", is_primary=True
        )

        # Перечитываем первый номер из базы
        phone1.refresh_from_db()
        assert phone1.is_primary is False
        assert phone2.is_primary is True

    def test_unique_user_phone_constraint(self, db, admin_user):
        number = "+375-29-111-11-11"
        UserPhoneNumber.objects.create(user=admin_user, number=number)

        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            UserPhoneNumber.objects.create(user=admin_user, number=number)


@pytest.mark.django_db
def test_phone_is_primary_logic(teacher_user):
    # Создаем первый номер (он станет основным)
    phone1 = UserPhoneNumber.objects.create(
        user=teacher_user,
        number="+375-29-111-11-11",
        is_primary=True
    )

    # Создаем второй номер и тоже ставим is_primary=True
    phone2 = UserPhoneNumber.objects.create(
        user=teacher_user,
        number="+375-29-222-22-22",
        is_primary=True
    )

    phone1.refresh_from_db()
    # Проверяем, что первый номер ПЕРЕСТАЛ быть основным
    assert phone1.is_primary is False
    assert phone2.is_primary is True
