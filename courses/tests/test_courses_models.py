import pytest
from django.utils import timezone
from courses.models import Subject, Section, Topic, SimulatorConfig, Homework, TrainingSession
from django.core.exceptions import ValidationError
from freezegun import freeze_time


@pytest.mark.django_db
class TestCoursesModels:
    # --- Тесты разделов (Section) ---

    def test_section_hierarchy(self, subject):
        # Создаем цепочку: Математика -> 1 класс -> Сложение
        root_section = Section.objects.create(subject=subject, title="1 класс", order=1)
        sub_section = Section.objects.create(subject=subject, title="Сложение", parent=root_section)

        # Проверяем метод get_ancestors, который ты написал в моделях
        ancestors = sub_section.get_ancestors()

        assert len(ancestors) == 1
        assert ancestors[0].title == "1 класс"
        assert str(sub_section) == "1 класс -> Сложение"

    def test_section_soft_delete_cascade(self, subject, section, topic):
        """Проверка мягкого удаления: раздел -> тема"""
        section.delete()
        # Раздел помечен удаленным
        assert section.deleted_at is not None
        # Тема тоже должна быть "удалена" через каскад
        topic.refresh_from_db()
        assert topic.deleted_at is not None
        # Но в базе они физически есть
        assert Topic.all_objects.filter(id=topic.id).exists()

    # --- Тесты тренажеров и сессий ---

    def test_simulator_config_json_params(self, topic):
        """Проверка сохранения параметров в JSON"""
        params = {"min": 1, "max": 10, "count": 20}
        config = SimulatorConfig.objects.create(
            topic=topic,
            label="Тест",
            params=params
        )
        assert config.params["max"] == 10

    def test_training_session_duration(self, teacher_user, topic):
        config = SimulatorConfig.objects.create(topic=topic, label="Тренажер", params={})

        with freeze_time("2026-03-10 12:00:00"):
            session = TrainingSession.objects.create(
                student=teacher_user,
                config=config
            )

        with freeze_time("2026-03-10 12:05:00"):
            session.end_time = timezone.now()
            session.save()

        assert session.duration.total_seconds() == 300

    # --- Тесты домашних заданий ---

    def test_homework_status_logic_theory(self, student_user, teacher_user, subject, topic):
        """Проверка статуса домашки типа 'Теория'"""
        teacher_profile = teacher_user.teacher_profile
        student_profile = student_user.student_profile

        hw = Homework.objects.create(
            student=student_profile,
            teacher=teacher_profile,
            subject=subject,
            topic=topic,
            hw_type='theory',
            title="Читай теорию",
            is_theory_read=False
        )

        # Сначала не выполнено
        assert hw.get_status_for_student(student_user) is False

        # Ставим отметку о прочтении
        hw.is_theory_read = True
        hw.save()
        assert hw.get_status_for_student(student_user) is True

    def test_homework_score_validators(self, student_user, teacher_user, subject, topic):
        """Проверка валидатора оценки (от 0 до 10)"""
        hw = Homework(
            student=student_user.student_profile,
            teacher=teacher_user.teacher_profile,
            subject=subject,
            topic=topic,
            title="Тест оценки",
            actual_score=11  # Больше max
        )
        # внутри этого менеджера ожидается ошибка. Если её не будет, то тест упадет
        with pytest.raises(ValidationError):
            # full clean нужен, чтобы запустить валидаторы, т.к. при сохранении в БД они не срабатывают
            hw.full_clean()

    def test_homework_simulator_status(self, student_user, teacher_user, subject, topic):
        """Связь домашки со статусом прохождения тренажера"""
        config = SimulatorConfig.objects.create(topic=topic, label="Тренажер", params={})
        hw = Homework.objects.create(
            student=student_user.student_profile,
            teacher=teacher_user.teacher_profile,
            subject=subject,
            topic=topic,
            hw_type='simulator',
            simulator_config=config,
            title="Пройди тренажер"
        )

        # Сессии еще нет
        assert hw.get_status_for_student(student_user) is False

        # Создаем завершенную сессию
        TrainingSession.objects.create(
            student=student_user,
            config=config,
            end_time=timezone.now()
        )

        assert hw.get_status_for_student(student_user) is True

    def test_homework_status_practice(self, student_user, teacher_user, subject, topic):
        """Тест статуса для практики: выполнено, если выставлен балл (actual_score)"""
        hw = Homework.objects.create(
            student=student_user.student_profile,
            teacher=teacher_user.teacher_profile,
            subject=subject,
            topic=topic,
            hw_type='practice',
            title="Решить задачи в тетради"
        )

        # Оценки нет — статус False
        assert hw.get_status_for_student(student_user) is False

        # Учитель ставит оценку (валидную, от 0 до 10)
        hw.actual_score = 9
        hw.save()

        # Ожидаем True
        assert hw.get_status_for_student(student_user) is True
