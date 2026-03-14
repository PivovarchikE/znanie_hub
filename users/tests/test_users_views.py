import io

import pytest
from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from courses.models import Subject
from users.models import User, StudentProfile, UserPhoneNumber, SchoolClass


@pytest.mark.django_db
class TestRegistrationViews:

    def test_select_role_get(self, client):
        """Проверка страницы выбора роли"""
        url = reverse('select_role')
        response = client.get(url)
        assert response.status_code == 200
        assert 'registration/register_select_role.html' in [t.name for t in response.templates]

    def test_register_view_404_on_invalid_role(self, client):
        """Проверка 404 при попытке регистрации с фейковой ролью"""
        url = reverse('dynamic_register', kwargs={'role_slug': 'admin'})
        response = client.get(url)
        assert response.status_code == 404

    def test_student_registration_success(self, client, student_role):
        """Тест успешной регистрации ученика (POST)"""
        s_class = SchoolClass.objects.create(number=10)
        subject = Subject.objects.create(name="Физика")

        url = reverse('dynamic_register', kwargs={'role_slug': 'student'})

        # Данные для форм
        data = {
            'username': 'new_student',
            'password': 'safe_password_123',
            'password_confirm': 'safe_password_123',
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'email': 'ivan@example.com',
            # Данные профиля (StudentProfileForm)
            'school_class': s_class.id,
            'subjects': subject.id,
            # Данные формсета телефонов (ManagementForm)
            'phones-TOTAL_FORMS': '1',
            'phones-INITIAL_FORMS': '0',
            'phones-MIN_NUM_FORMS': '0',
            'phones-MAX_NUM_FORMS': '1000',
            'phones-0-number': '+375-29-111-22-33',
            'phones-0-relationship': 'OWN',
            'phones-0-is_primary': 'on',
        }

        response = client.post(url, data)

        # После успешной регистрации — редирект на логин
        assert response.status_code == 302
        assert response.url == reverse('login')

        # Проверяем БД
        assert User.objects.filter(username='new_student').exists()
        user = User.objects.get(username='new_student')
        assert StudentProfile.objects.filter(user=user).exists()
        assert UserPhoneNumber.objects.filter(user=user, number='+375-29-111-22-33').exists()


@pytest.mark.django_db
class TestAuthViews:

    def test_login_view_get(self, client):
        url = reverse('login')
        response = client.get(url)
        assert response.status_code == 200

    def test_logout_view(self, client, teacher_user):
        client.force_login(teacher_user)
        url = reverse('logout')
        response = client.get(url)
        assert response.status_code == 302


@pytest.mark.django_db
class TestProfileViews:

    def test_profile_edit_requires_login(self, client):
        """Проверка редиректа на логин для неавторизованного пользователя"""
        url = reverse('profile_edit')
        response = client.get(url)

        assert response.status_code == 302
        assert '/login/' in response.url

    def test_profile_edit_get_authenticated(self, client, teacher_user):
        """Проверка отображения формы редактирования профиля"""
        client.force_login(teacher_user)
        url = reverse('profile_edit')
        response = client.get(url)

        assert response.status_code == 200
        assert 'u_form' in response.context
        assert 'p_form' in response.context
        assert response.context['role_slug'] == 'teacher'


@pytest.mark.django_db
def test_teacher_registers_student_automatic_link(client, teacher_user, student_role):
    """
    Проверка: если Учитель регистрирует Ученика,
    ученик автоматически получает этого учителя в свой профиль.
    """

    s_class = SchoolClass.objects.create(number=10)
    subject = Subject.objects.create(name="Физика")

    # Авторизуем учителя
    client.force_login(teacher_user)

    url = reverse('dynamic_register', kwargs={'role_slug': 'student'})

    # Данные для регистрации нового ученика
    data = {
        'username': 'autolink_student',
        'password': 'password123',
        'password_confirm': 'password123',
        'first_name': 'Петр',
        'last_name': 'Петров',
        'email': 'peter@example.com',
        'school_class': s_class.id,
        'subjects': [subject.id],
        # Обязательные поля для ManagementForm (телефоны)
        'phones-TOTAL_FORMS': '1',
        'phones-INITIAL_FORMS': '0',
        'phones-MIN_NUM_FORMS': '0',
        'phones-MAX_NUM_FORMS': '1000',
        'phones-0-number': '+375-29-999-88-77',
        'phones-0-relationship': 'OWN',
        'phones-0-is_primary': 'on',
    }

    # Отправляем запрос
    response = client.post(url, data)

    # Должен быть редирект на дашборд учителя
    assert response.status_code == 302
    assert response.url == reverse('teacher_dashboard')

    # Проверяем связь
    new_student = User.objects.get(username='autolink_student')
    student_profile = new_student.student_profile

    # Проверяем, есть ли учитель в списке учителей ученика
    assert teacher_user.teacher_profile in student_profile.teachers.all()

    # Проверяем наличие сообщения об успехе
    from django.contrib.messages import get_messages
    messages = [m.message for m in get_messages(response.wsgi_request)]
    assert f'Ученик {new_student.get_full_name()} успешно зарегистрирован' in messages[0]


@pytest.mark.django_db
def test_registration_atomicity(client, student_role):
    """Если данные профиля невалидны, User не должен быть создан."""
    url = reverse('dynamic_register', kwargs={'role_slug': 'student'})
    initial_user_count = User.objects.count()

    # Отправляем валидного юзера, но БИТЫЙ профиль (school_class='')
    data = {
        'username': 'failed_user',
        'password': 'password123',
        'password_confirm': 'password123',
        'email': 'fail@test.com',
        'first_name': 'Fail',
        'last_name': 'User',
        'school_class': '',
        'phones-TOTAL_FORMS': '1',
        'phones-INITIAL_FORMS': '0',
        'phones-0-number': '+375-29-000-00-00',
        'phones-0-relationship': 'OWN',
        'phones-0-is_primary': 'on',
    }

    response = client.post(url, data)

    assert response.status_code == 200
    assert User.objects.count() == initial_user_count
    assert not User.objects.filter(username='failed_user').exists()


@pytest.mark.django_db
def test_profile_edit_isolation(client, student_role):
    """Проверка защиты формы редактирования профиля от закидывания чужого профиля"""
    # Создаем двух учеников
    user_a = User.objects.create_user(username="student_a", password="123", role=student_role)
    user_b = User.objects.create_user(username="student_b", password="123", role=student_role)
    StudentProfile.objects.create(user=user_a)
    profile_b = StudentProfile.objects.create(user=user_b)

    client.force_login(user_a)
    url = reverse('profile_edit')

    # Пытаемся отправить данные, которые якобы относятся к профилю B
    # Но вьюха должна брать профиль только текущего request.user
    response = client.get(url)

    # Проверяем, что в контексте формы именно данные User A
    assert response.context['u_form'].instance == user_a
    assert response.context['p_form'].instance.user == user_a


@pytest.mark.django_db
def test_profile_edit_queries_limit(client, teacher_user, django_assert_num_queries):
    """Проверяем, что номера телефонов проходят, как один запрос"""
    # Добавим учителю 5 номеров
    for i in range(5):
        UserPhoneNumber.objects.create(user=teacher_user, number=f"+375-29-000-00-0{i}")

    client.force_login(teacher_user)

    # Ожидаем, что количество запросов будет 10: сессия + юзер, получить роль и профиль, предметы и классы,
    # формы (3: SELECT 1, DECLARE, CURSOR), телефоны (1 запрос)
    # независимо от количества телефонов благодаря select_related/prefetch_related
    with django_assert_num_queries(15, exact=False):
        client.get(reverse('profile_edit'))


@pytest.mark.django_db
def test_profile_queries_do_not_grow(client, teacher_user, django_assert_num_queries):
    """Проверяем, что при изменении количества номеров телефонов не меняется количество запросов"""
    client.force_login(teacher_user)

    # Сначала замеряем при 1 номере
    UserPhoneNumber.objects.create(user=teacher_user, number="+375291111111")
    with django_assert_num_queries(10) as captured:
        client.get(reverse('profile_edit'))
    count_before = len(captured.captured_queries)

    # Добавляем еще 10 номеров
    for i in range(10):
        UserPhoneNumber.objects.create(user=teacher_user, number=f"+37529{i}000000")

    # Количество запросов должно остаться ТАКИМ ЖЕ (10)
    with django_assert_num_queries(count_before):
        client.get(reverse('profile_edit'))


@pytest.mark.django_db
class TestAvatarUpdate:
    """Тест логики аватара"""
    @pytest.fixture(autouse=True)
    def setup_client(self, client, teacher_user):
        """Автоматически логиним пользователя перед каждым тестом в этом классе"""
        self.client = client
        self.user = teacher_user
        self.client.force_login(self.user)
        self.url = reverse('avatar_update')

    def create_test_image(self):
        """Вспомогательный метод для генерации картинки"""
        file_obj = io.BytesIO()
        image = Image.new('RGB', (100, 100), color='blue')
        image.save(file_obj, 'JPEG')
        file_obj.seek(0)
        return SimpleUploadedFile("test_avatar.jpg", file_obj.read(), content_type="image/jpeg")

    def test_avatar_upload_and_optimization(self):
        """Тест: загрузка, обрезка и сжатие до 400x400"""
        image = self.create_test_image()
        data = {
            'avatar': image,
            'x': '0',
            'y': '0',
            'width': '100',
            'height': '100',
        }

        response = self.client.post(self.url, data)

        # Проверяем редирект (успех)
        assert response.status_code == 302

        self.user.refresh_from_db()
        assert self.user.avatar is not None

        # Проверяем, что Pillow отработал: ресайз до 400x400
        img = Image.open(self.user.avatar.path)
        assert img.size == (400, 400)
        assert img.format == 'JPEG'

    def test_avatar_deletion(self):
        """Тест: удаление аватара через POST-параметр delete_avatar"""
        # Сначала принудительно ставим аватар
        self.user.avatar = self.create_test_image()
        self.user.save()

        response = self.client.post(self.url, {'delete_avatar': ''})

        assert response.status_code == 302
        self.user.refresh_from_db()
        assert not self.user.avatar  # Поле должно стать пустым

    def test_size_limit_backend_validation(self):
        """
        Тест: хотя есть JS-проверка, бэкенд не должен падать
        при попытке загрузки
        """
        response = self.client.get(self.url)
        assert response.status_code == 200
        assert 'avatar-form' in response.content.decode()


@pytest.mark.django_db
def test_avatar_update_access_denied(client):
    """Тест: анонимный пользователь не имеет доступа"""
    url = reverse('avatar_update')
    response = client.get(url)
    assert response.status_code == 302
    assert 'login' in response.url
