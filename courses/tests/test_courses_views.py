import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from courses.models import Subject, Section, Topic, TrainingSession, Homework, HomeworkResponseFile
from users.models import StudentProfile


@pytest.mark.django_db
class TestGlobalSearch:

    def test_search_access_denied_for_anonymous(self, client):
        """Проверка, что без логина поиск недоступен."""
        url = reverse('global_search')
        response = client.get(url)
        assert response.status_code == 302
        assert 'login' in response.url

    def test_short_query_returns_none(self, client, student_user):
        """Запрос меньше 2 символов не возвращает результаты."""
        client.force_login(student_user)
        url = reverse('global_search')

        response = client.get(url, {'q': 'М'})

        assert response.status_code == 200
        assert response.context['results'] is None
        # Проверяем, что вернулся именно partial (выпадашка)
        assert 'partials/search_dropdown.html' in [t.name for t in response.templates]

    def test_search_finds_subject(self, client, student_user, subject):
        """Поиск успешно находит предмет по названию."""
        client.force_login(student_user)
        url = reverse('global_search')

        response = client.get(url, {'q': 'Мат'})

        assert response.status_code == 200
        subjects = response.context['results']['subjects']
        assert subject in subjects
        assert subjects.count() == 1

    def test_search_htmx_header(self, client, student_user, topic):
        """Проверка логики htmx (возврат partial шаблона)."""
        client.force_login(student_user)
        url = reverse('global_search')

        # Эмулируем HTMX запрос через заголовок
        response = client.get(url, {'q': 'Слож'}, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        assert 'partials/search_dropdown.html' in [t.name for t in response.templates]
        assert topic.title in response.content.decode('utf-8')

    def test_search_excludes_deleted_items(self, client, student_user, subject):
        """Поиск не должен выдавать удаленные объекты (Soft Delete)."""
        client.force_login(student_user)
        url = reverse('global_search')

        # Помечаем предмет как удаленный
        from django.utils import timezone
        subject.deleted_at = timezone.now()
        subject.save()

        response = client.get(url, {'q': 'Мат'})

        assert subject not in response.context['results']['subjects']

    def test_search_topic_content(self, client, student_user, topic):
        """Поиск ищет не только по названию, но и по контенту темы."""
        client.force_login(student_user)
        url = reverse('global_search')

        topic.text_content = "Тут важная информация про вычитание"
        topic.save()

        response = client.get(url, {'q': 'информация'})

        assert topic in response.context['results']['topics']


@pytest.mark.django_db
class TestEducationViews:
    """Тесты учебного процесса"""
    def test_math_index(self, client, subject):
        """Проверка главной страницы математики и префетча разделов"""
        url = reverse('math_index')
        response = client.get(url)
        assert response.status_code == 200
        assert subject.name in response.content.decode('utf-8')

    def test_topic_detail_with_homework(self, client, student_user, topic, homework):
        """Проверка страницы темы при переходе из домашки (hw в GET)"""
        client.force_login(student_user)
        url = reverse('topic_detail', args=[topic.id])
        response = client.get(url, {'hw': homework.id})

        assert response.status_code == 200
        assert response.context['current_homework'] == homework
        # Проверка, что конфиг подтянулся из домашки
        assert response.context['preset_config_id'] == str(homework.simulator_config.id)

    def test_save_training_result_theory(self, client, student_user, homework):
        """Тест отметки прочтения теории через AJAX"""
        client.force_login(student_user)
        url = reverse('save_training_result')
        data = {
            'homework_id': homework.id,
            'is_theory_only': True
        }
        response = client.post(url, data=data, content_type='application/json')

        assert response.status_code == 200
        homework.refresh_from_db()
        assert homework.is_completed is True
        assert homework.score == 100

    def test_save_training_result_simulator(self, client, student_user, homework, simulator_config):
        """Тест сохранения результата тренажера и создания сессии"""
        client.force_login(student_user)
        url = reverse('save_training_result')
        payload = {
            'config_id': simulator_config.id,
            'homework_id': homework.id,
            'total': 10,
            'correct': 8,
            'details': [{'q': '1+1', 'user_a': '2', 'is_correct': True}]
        }
        response = client.post(url, data=payload, content_type='application/json')

        assert response.status_code == 200
        assert TrainingSession.objects.filter(student=student_user).exists()
        homework.refresh_from_db()
        assert homework.score == 80  # (8/10 * 100)


@pytest.mark.django_db
class TestTeacherDashboard:
    """Тесты личного кабинета учителя (дашборд и добавление ДЗ)"""
    def test_teacher_dashboard_access(self, client, teacher_user, student_user):
        """Только учитель видит дашборд учителя"""
        url = reverse('teacher_dashboard')

        # Ученик -> Редирект
        client.force_login(student_user)
        response = client.get(url)
        assert response.status_code == 302

        # Учитель -> OK
        client.force_login(teacher_user)
        # Связываем ученика с учителем для теста
        teacher_user.teacher_profile.my_students.add(student_user.student_profile)
        response = client.get(url)
        assert response.status_code == 200
        assert student_user.username in response.content.decode('utf-8')

    def test_add_homework_post(self, client, teacher_user, student_user, subject, section, topic, simulator_config):
        """Тест создания домашки с учетом динамических кверисетов формы"""
        client.force_login(teacher_user)
        student_profile = student_user.student_profile
        teacher_user.teacher_profile.my_students.add(student_profile)

        url = reverse('add_homework', args=[student_profile.id])

        form_data = {
            'title': 'Новое задание',
            'subject': subject.id,
            'section': section.id,  # ОБЯЗАТЕЛЬНО: чтобы форма "увидела" темы этого раздела
            'topic': topic.id,
            'hw_type': 'simulator',
            'simulator_config': simulator_config.id,
            'deadline': '2026-12-31T23:59',  # Соответствует DateTimeInput(type='datetime-local')
            # Поля формсета
            'files-TOTAL_FORMS': '0',
            'files-INITIAL_FORMS': '0',
            'files-MIN_NUM_FORMS': '0',
            'files-MAX_NUM_FORMS': '1000',
        }

        response = client.post(url, data=form_data)

        assert response.status_code == 302
        assert Homework.objects.filter(title='Новое задание').exists()

    def test_delete_student_relation(self, client, teacher_user, student_user):
        """Учитель удаляет ученика (отвязывает от себя), а не удаляет объект"""
        client.force_login(teacher_user)
        teacher_prof = teacher_user.teacher_profile
        student_prof = student_user.student_profile
        teacher_prof.my_students.add(student_prof)

        url = reverse('delete_student', args=[student_prof.id])
        response = client.post(url)

        assert response.status_code == 302
        assert student_prof not in teacher_prof.my_students.all()
        # Проверяем, что сам профиль в базе остался
        assert StudentProfile.objects.filter(id=student_prof.id).exists()


@pytest.mark.django_db
class TestCoursesAPI:
    """Тесты API и AJAX"""

    def test_get_topics_ajax(self, client, section, topic):
        """Тест возврата JSON списка тем для раздела"""
        url = reverse('ajax_get_topics')
        response = client.get(url, {'section_id': section.id}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        assert response.status_code == 200
        data = response.json()
        assert data[0]['title'] == topic.title
        assert data[0]['has_theory'] is False

    def test_get_section_accordion_htmx(self, client, teacher_user, section):
        """Тест подгрузки HTML-куска для аккордеона через AJAX"""
        client.force_login(teacher_user)
        url = reverse('ajax_get_accordion')
        response = client.get(url, {'section_id': section.id}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')

        assert response.status_code == 200
        content = response.content.decode('utf-8')

        assert 'recursive-container' in content
        assert 'accordion-select-' in content
        assert f'accordion-select-{section.id}' in content


@pytest.mark.django_db
class TestHomeworkFiles:
    """Тест загрузки файлов в ДЗ"""
    def test_add_homework_with_files(self, client, teacher_user, student_user, subject, section, topic):
        """Тест: Учитель создает ДЗ и прикрепляет к нему методичку (файл)"""
        client.force_login(teacher_user)
        student_prof = student_user.student_profile
        teacher_user.teacher_profile.my_students.add(student_prof)

        url = reverse('add_homework', args=[student_prof.id])

        # Создаем фейковый PDF-файл
        fake_pdf = SimpleUploadedFile(
            "manual.pdf",
            b"file_content",
            content_type="application/pdf"
        )

        form_data = {
            'title': 'Задание с файлом',
            'subject': subject.id,
            'section': section.id,
            'topic': topic.id,
            'hw_type': 'practice',
            # Данные формсета
            'files-TOTAL_FORMS': '1',
            'files-INITIAL_FORMS': '0',
            'files-MIN_NUM_FORMS': '0',
            'files-MAX_NUM_FORMS': '1000',
            'files-0-file': fake_pdf, # Передаем файл в первый слот формсета
        }

        response = client.post(url, data=form_data)

        assert response.status_code == 302
        hw = Homework.objects.get(title='Задание с файлом')
        # Проверяем, что файл прикрепился к объекту HomeworkFile (через related_name)
        assert hw.files.count() == 1
        saved_file_name = hw.files.first().file.name
        assert "manual" in saved_file_name
        assert saved_file_name.endswith(".pdf")

    def test_upload_hw_response_student(self, client, student_user, homework):
        """Тест: Ученик загружает фото выполненной работы (ответ на ДЗ)"""
        client.force_login(student_user)
        url = reverse('upload_hw_response', args=[homework.id])

        # Имитируем загрузку двух фотографий
        img1 = SimpleUploadedFile("solution1.jpg", b"data1", content_type="image/jpeg")
        img2 = SimpleUploadedFile("solution2.jpg", b"data2", content_type="image/jpeg")

        response = client.post(url, {'files': [img1, img2]})

        assert response.status_code == 302
        # Проверяем создание записей в HomeworkResponseFile
        assert HomeworkResponseFile.objects.filter(homework=homework).count() == 2
