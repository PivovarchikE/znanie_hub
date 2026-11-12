import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.urls import reverse

logger = logging.getLogger(__name__)


def _admin_recipients():
    """
    Кому слать уведомления: ADMIN_NOTIFICATION_EMAILS из настроек,
    а если список пуст — email'ы активных суперпользователей.
    """
    emails = list(getattr(settings, 'ADMIN_NOTIFICATION_EMAILS', []))
    if emails:
        return emails
    User = get_user_model()
    return list(
        User.objects.filter(is_superuser=True, is_active=True)
        .exclude(email='')
        .values_list('email', flat=True)
    )


def notify_admins_about_registration(user, request=None):
    """Письмо администратору: новый пользователь ждёт подтверждения."""
    recipients = _admin_recipients()
    if not recipients:
        logger.warning(
            'Новый пользователь %s ждёт подтверждения, но не найдено ни одного '
            'адреса администратора (ADMIN_NOTIFICATION_EMAILS / email суперпользователя).',
            user.username,
        )
        return False

    admin_path = reverse('admin:users_user_change', args=[user.pk])
    admin_url = request.build_absolute_uri(admin_path) if request else admin_path

    phones = ', '.join(p.number for p in user.phones.all()) or '—'
    role_name = user.role.name if user.role else '—'

    body = (
        'Зарегистрировался новый пользователь и ожидает подтверждения.\n\n'
        f'Логин: {user.username}\n'
        f'ФИО: {user.full_name or "—"}\n'
        f'Роль: {role_name}\n'
        f'Email: {user.email or "—"}\n'
        f'Телефоны: {phones}\n\n'
        f'Открыть в админке и подтвердить: {admin_url}\n'
        '(Либо выберите пользователя в списке и примените действие '
        '«Подтвердить выбранных пользователей».)'
    )
    try:
        send_mail(
            subject=f'Новая регистрация: {user.username} ({role_name})',
            message=body,
            from_email=None,  # DEFAULT_FROM_EMAIL
            recipient_list=recipients,
            fail_silently=False,
        )
    except Exception:
        # Ошибка почты не должна ломать регистрацию
        logger.exception('Не удалось отправить уведомление администратору о %s', user.username)
        return False
    return True


def approve_user(user, request=None):
    """Подтверждает пользователя: он становится активным и может войти."""
    user.is_validate = True
    user.is_active = True
    user.save(update_fields=['is_validate', 'is_active', 'updated_at'])
    notify_user_approved(user, request)


def notify_user_approved(user, request=None):
    """Письмо пользователю о подтверждении (если он указал email)."""
    if not user.email:
        return False
    login_path = reverse('login')
    login_url = request.build_absolute_uri(login_path) if request else login_path
    try:
        send_mail(
            subject='Ваш аккаунт подтверждён',
            message=(
                f'Здравствуйте, {user.get_full_name() or user.username}!\n\n'
                f'Администратор подтвердил вашу регистрацию. Теперь вы можете войти: {login_url}'
            ),
            from_email=None,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        logger.exception('Не удалось отправить письмо о подтверждении %s', user.username)
        return False
    return True
