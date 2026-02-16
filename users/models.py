# не забыть сделать файл для инициализации БД: классы, предметы, роли и т.д.

from datetime import date

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Now
from django.utils.timezone import now
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.conf import settings


# Запись не удаляется из БД (помечается удаленной через deleted at)
class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class BaseModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_default=Now())
    updated_at = models.DateTimeField(auto_now=True, db_default=Now())
    deleted_at = models.DateTimeField(blank=True, null=True)

    # Основной менеджер. Фильтрует данные так, что objects.all доставал только "живые записи"
    objects = SoftDeleteManager()
    # all_objects.all позволяет доставать записи, помеченные как удаленные
    all_objects = models.Manager()

    # Помечаем, что для BaseModel не надо создавать таблицу в БД
    class Meta:
        abstract = True

    # Удаление записи
    def delete(self, using=None, keep_parents=False):
        self.deleted_at = now()
        self.save()
        # Если у модели есть связанные объекты, которые тоже должны "удалиться"
        # Django не сделает это автоматически при Soft Delete

    # Восстановление записи
    def restore(self):
        self.deleted_at = None
        self.save()

    # Флаг obj.is_deleted
    @property
    def is_deleted(self):
        return self.deleted_at is not None


class Role(BaseModel):
    name = models.CharField()
    slug = models.SlugField()


class User(AbstractUser, BaseModel):
    role = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True)

    def get_role_display(self):
        return self.role

    '''
    Нужно доработать.
    Флаг проверки пользователя администратором, который получает уведомление
    при самостоятельной регистрации пользователя.
    Если пользователя ученика регистрирует учитель, то флаг автоматически True
    '''
    is_validate = models.BooleanField(default=False)

    middle_name = models.CharField(max_length=255, blank=True, null=True)

    date_of_birth = models.DateField(blank=True, null=True)

    def clean(self):
        super().clean()
        if self.date_of_birth and self.date_of_birth > date.today():
            raise ValidationError({'date_of_birth': "Дата рождения не может быть в будущем."})

    # Отображение в админке + сортировка
    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

    @property
    def full_name(self):
        return f"{self.last_name} {self.first_name} {self.middle_name or ''}".strip()


class SchoolClass(BaseModel):
    number = models.PositiveSmallIntegerField(verbose_name="Цифра класса")  # 1, 2, 11

    class Meta:
        verbose_name = "Класс"
        verbose_name_plural = "Классы"
        ordering = ['number']

    def __str__(self):
        return f"{self.number}"


class TeacherProfile(BaseModel):
    # Связь "один-к-оному" с User
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teacher_profile')

    subjects = models.ManyToManyField(
        'courses.Subject',
        related_name='teachers',
        verbose_name='Предметы обучения',
        blank=False
    )

    school_classes = models.ManyToManyField(
        SchoolClass,
        verbose_name="Классы",
        related_name='teachers',
        blank=False
    )

    def __str__(self):
        return f"Профиль учителя: {self.user.username}"


class StudentProfile(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='student_profile')

    school_class = models.ForeignKey(
        SchoolClass,
        null=True,
        on_delete=models.SET_NULL,
        verbose_name="Класс",
        related_name='students',
        blank=False
    )

    subjects = models.ManyToManyField(
        'courses.Subject',
        related_name='students',
        verbose_name='Изучаемые предметы',
        blank=False
    )

    def __str__(self):
        return f"Профиль ученика: {self.user.username}"


# Определяем маску: +375 и далее 9 цифр (по 2-3-2-2)
phone_regex = RegexValidator(
    regex=r'^\+375-\d{2}-\d{3}-\d{2}-\d{2}$',
    message="Номер телефона должен быть в формате: '+375-XX-XXX-XX-XX'."
)


class UserPhoneNumber(BaseModel):

    class RelationshipType(models.TextChoices):
        OWN = "OWN", "Личный"
        MOTHER = "MOTHER", "Мама"
        FATHER = "FATHER", "Папа"
        GRANDMOTHER = "GRANDMOTHER", "Бабушка"
        GRANDFATHER = "GRANDFATHER", "Дедушка"
        OTHER = "OTHER", "Другое"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='phones'
    )

    number = models.CharField(
        validators=[phone_regex],
        max_length=17,
        unique=False
    )

    # Чей это номер? (по умолчанию - личный)
    relationship = models.CharField(
        max_length=20,
        choices=RelationshipType.choices,
        default=RelationshipType.OWN,
        verbose_name="Чей номер"
    )

    # Имя родственника (заполняется, если номер не личный)
    owner_name = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name="Имя владельца"
    )

    is_primary = models.BooleanField(default=False, verbose_name="Основной")

    def save(self, *args, **kwargs):
        # Если это первый номер пользователя, делаем его основным принудительно
        if not UserPhoneNumber.objects.filter(user=self.user).exists():
            self.is_primary = True

        # Если этот номер ставится основным, убираем флаг у других
        if self.is_primary:
            UserPhoneNumber.objects.filter(user=self.user, is_primary=True).exclude(pk=self.pk).update(is_primary=False)

        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Номер телефона"
        verbose_name_plural = "Номера телефонов"
        # Гарантируем, что один и тот же номер не привяжут к одному юзеру дважды
        constraints = [
            models.UniqueConstraint(fields=['user', 'number'], name='unique_user_phone')
        ]

    def __str__(self):
        # Если есть имя владельца, выводим его вместе с номером
        if self.owner_name:
            return f"{self.number} ({self.owner_name} - {self.get_relationship_display()})"
        return f"{self.number} (Личный)"
