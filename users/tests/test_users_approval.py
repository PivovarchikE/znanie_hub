import pytest
from django.urls import reverse

from courses.models import Subject
from users.models import User, SchoolClass


def _student_post_data(username='new_student'):
    s_class = SchoolClass.objects.create(number=10)
    subject = Subject.objects.create(name="Физика")
    return {
        'username': username,
        'password': 'safe_password_123',
        'password_confirm': 'safe_password_123',
        'first_name': 'Иван',
        'last_name': 'Иванов',
        'school_class': s_class.id,
        'subjects': subject.id,
        'phones-TOTAL_FORMS': '1',
        'phones-INITIAL_FORMS': '0',
        'phones-MIN_NUM_FORMS': '0',
        'phones-MAX_NUM_FORMS': '1000',
        'phones-0-number': '+375-29-111-22-33',
        'phones-0-relationship': 'OWN',
        'phones-0-is_primary': 'on',
    }


@pytest.mark.django_db
class TestSelfRegistrationApproval:

    def test_self_registered_user_is_inactive_and_admin_notified(
            self, client, student_role, settings, mailoutbox):
        settings.ADMIN_NOTIFICATION_EMAILS = ['admin@example.com']

        response = client.post(
            reverse('dynamic_register', kwargs={'role_slug': 'student'}),
            _student_post_data(),
        )

        assert response.status_code == 302
        user = User.objects.get(username='new_student')
        assert user.is_active is False
        assert user.is_validate is False

        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ['admin@example.com']
        assert 'new_student' in mailoutbox[0].body

    def test_falls_back_to_superuser_email(self, client, student_role, settings, mailoutbox):
        settings.ADMIN_NOTIFICATION_EMAILS = []
        User.objects.create_superuser('root', 'root@example.com', 'pass12345')

        client.post(reverse('dynamic_register', kwargs={'role_slug': 'student'}), _student_post_data())

        assert len(mailoutbox) == 1
        assert mailoutbox[0].to == ['root@example.com']

    def test_pending_user_cannot_login(self, client, student_role, settings):
        settings.ADMIN_NOTIFICATION_EMAILS = ['admin@example.com']
        client.post(reverse('dynamic_register', kwargs={'role_slug': 'student'}), _student_post_data())

        response = client.post(reverse('login'), {
            'username': 'new_student', 'password': 'safe_password_123',
        })

        assert response.status_code == 200
        assert '_auth_user_id' not in client.session
        assert 'подтверждения' in str(response.context['form'].non_field_errors())

    def test_approved_user_can_login(self, client, student_role, settings):
        settings.ADMIN_NOTIFICATION_EMAILS = ['admin@example.com']
        client.post(reverse('dynamic_register', kwargs={'role_slug': 'student'}), _student_post_data())

        from users.services import approve_user
        approve_user(User.objects.get(username='new_student'))

        response = client.post(reverse('login'), {
            'username': 'new_student', 'password': 'safe_password_123',
        })
        assert response.status_code == 302
        assert '_auth_user_id' in client.session

    def test_wrong_password_still_generic_error(self, client, teacher_user):
        response = client.post(reverse('login'), {'username': 'teacher_bill', 'password': 'wrong'})
        assert response.status_code == 200
        assert '_auth_user_id' not in client.session

    def test_student_registered_by_teacher_is_active_without_notification(
            self, client, teacher_user, student_role, settings, mailoutbox):
        settings.ADMIN_NOTIFICATION_EMAILS = ['admin@example.com']
        client.force_login(teacher_user)

        client.post(reverse('dynamic_register', kwargs={'role_slug': 'student'}), _student_post_data())

        user = User.objects.get(username='new_student')
        assert user.is_active is True
        assert user.is_validate is True
        assert len(mailoutbox) == 0


@pytest.mark.django_db
def test_admin_action_approves_users_and_emails_them(admin_client, student_user, mailoutbox):
    student_user.is_active = False
    student_user.is_validate = False
    student_user.email = 'student@example.com'
    student_user.save()

    response = admin_client.post(reverse('admin:users_user_changelist'), {
        'action': 'approve_users',
        '_selected_action': [student_user.pk],
    })

    assert response.status_code == 302
    student_user.refresh_from_db()
    assert student_user.is_active is True
    assert student_user.is_validate is True
    assert [m.to for m in mailoutbox] == [['student@example.com']]
