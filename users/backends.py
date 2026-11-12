from django.contrib.auth.backends import ModelBackend


class ApprovalModelBackend(ModelBackend):
    """
    Как ModelBackend, но authenticate() не отсекает неактивных пользователей —
    это нужно, чтобы форма входа могла показать «ожидает подтверждения»
    вместо «неверный логин или пароль».

    get_user() (проверка уже существующей сессии) по-прежнему требует is_active,
    поэтому деактивированный администратором пользователь сразу теряет доступ.
    """

    def user_can_authenticate(self, user):
        return True

    def get_user(self, user_id):
        user = super().get_user(user_id)
        return user if user is not None and user.is_active else None
