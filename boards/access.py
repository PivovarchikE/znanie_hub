from boards.models import BoardParticipant


def get_board_access(user, board):
    """Возвращает (роль, может_редактировать). Роль: 'teacher' | 'student' | 'participant' | None."""
    teacher = getattr(user, 'teacher_profile', None)
    if teacher and board.teacher_id == teacher.pk:
        return 'teacher', True

    student = getattr(user, 'student_profile', None)
    if student:
        if board.student_id == student.pk:
            return 'student', True
        if board.group_id and board.group.students.filter(pk=student.pk).exists():  # ПРЕДПОЛОЖЕНИЕ: StudentGroup.students
            return 'student', True

    participant = BoardParticipant.objects.filter(board=board, user=user).first()
    if participant:
        return 'participant', participant.can_edit

    return None, False