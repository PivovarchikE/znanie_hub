import uuid
from django.db import models
from django.db.models import Q
from users.models import User, StudentProfile, StudentGroup, TeacherProfile


class Board(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255, verbose_name="Название доски")

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, null=True, blank=True,
                                related_name='personal_boards')
    group = models.ForeignKey(StudentGroup, on_delete=models.CASCADE, null=True, blank=True,
                              related_name='group_boards')
    teacher = models.ForeignKey(TeacherProfile, on_delete=models.CASCADE, related_name='teacher_boards')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            # Доска принадлежит либо ученику, либо группе — но не обоим сразу и не никому
            models.CheckConstraint(   # Django < 5.1: параметр называется check=, а не condition=
                condition=(Q(student__isnull=False, group__isnull=True) |
                           Q(student__isnull=True, group__isnull=False)),
                name='board_student_xor_group',
            ),
            # Одна личная доска на пару «учитель — ученик».
            # NULL в уникальных индексах не считаются равными, поэтому групповые доски не мешают.
            models.UniqueConstraint(fields=['teacher', 'student'], name='uniq_board_teacher_student'),
            # Одна доска на пару «учитель — группа»
            models.UniqueConstraint(fields=['teacher', 'group'], name='uniq_board_teacher_group'),
        ]

    def __str__(self):
        return f"Доска: {self.title} (Учитель: {self.teacher.user.username})"


class BoardParticipant(models.Model):
    """Участники доски (кроме учителя-владельца)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='board_accesses')
    can_edit = models.BooleanField(default=True, verbose_name="Может редактировать")
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('board', 'user')


class BoardObject(models.Model):
    """Элементы доски (Fabric.js)"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    board = models.ForeignKey(Board, on_delete=models.CASCADE, related_name='board_objects')
    object_id = models.CharField(max_length=100)   # было unique=True — теперь уникально в пределах доски
    data = models.JSONField(verbose_name="JSON-данные объекта Fabric.js")
    created_at = models.DateTimeField(auto_now_add=True)   # для стабильного порядка слоёв
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['board', 'object_id'], name='uniq_boardobject_board_objectid'),
        ]
        ordering = ['created_at']

    def __str__(self):
        return f"Объект {self.object_id} для доски {self.board.title}"