import json
import uuid

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from users.models import StudentGroup, StudentProfile, TeacherProfile, User
from .access import get_board_access
from .consumers import conn_key
from .models import Board, BoardParticipant


# ---------- Вспомогательные функции ----------

def _full_name(user):
    return user.get_full_name() or user.username


def _resolve_board(user, entity_type, entity_id):
    """
    Находит или создаёт доску для текущего пользователя.
    Учитель: entity_type = 'student' | 'group'
    Ученик:  entity_type = 'teacher' | 'group'
    """
    teacher = getattr(user, 'teacher_profile', None)
    student = getattr(user, 'student_profile', None)

    if teacher:
        if entity_type == 'student':
            target = get_object_or_404(StudentProfile, pk=entity_id, teachers=teacher)
            board, _ = Board.objects.get_or_create(
                teacher=teacher, student=target,
                defaults={'title': f"Доска: {_full_name(target.user)}"},
            )
            return board
        if entity_type == 'group':
            group = get_object_or_404(StudentGroup, pk=entity_id, teacher=teacher)
            board, _ = Board.objects.get_or_create(
                teacher=teacher, group=group,
                defaults={'title': f"Группа: {group.name}"},
            )
            return board

    if student:
        if entity_type == 'teacher':
            target = get_object_or_404(student.teachers, pk=entity_id)
            board, _ = Board.objects.get_or_create(
                teacher=target, student=student,
                defaults={'title': f"Доска: {_full_name(student.user)}"},
            )
            return board
        if entity_type == 'group':
            group = get_object_or_404(
                StudentGroup.objects.select_related('teacher'),
                pk=entity_id, students=student,
            )
            board, _ = Board.objects.get_or_create(
                teacher=group.teacher, group=group,
                defaults={'title': f"Группа: {group.name}"},
            )
            return board

    return None

# ---------- Вход на доску ----------

@login_required
def open_entity_board(request, entity_type, entity_id):
    board = _resolve_board(request.user, entity_type, entity_id)
    if board is None:
        raise PermissionDenied("У вас нет доступа к этой доске.")
    return redirect('boards:board_room', board_id=board.id)


@login_required
def get_or_create_board(request, target_type, target_id):
    """Оставлено для совместимости с существующими urls."""
    return open_entity_board(request, target_type, target_id)


@login_required
def board_room_view(request, board_id):
    board = get_object_or_404(Board.objects.select_related('teacher__user'), pk=board_id)
    user = request.user
    role, can_edit = get_board_access(user, board)

    if role is None:
        # Вход по ссылке-приглашению: только ученики ЭТОГО учителя
        student = getattr(user, 'student_profile', None)
        if not (student and student.teachers.filter(pk=board.teacher_id).exists()):
            raise PermissionDenied("У вас нет доступа к этой доске.")
        role, can_edit = 'participant', True

    # Все, кроме учителя-владельца, фиксируются как участники (в т.ч. основной ученик)
    if role != 'teacher':
        BoardParticipant.objects.get_or_create(board=board, user=user)

    return render(request, 'boards/board_room.html', {
        'board': board,
        'is_teacher': role == 'teacher',
        'can_edit': can_edit,
    })


# ---------- API ----------

@login_required
@require_POST
def manage_board_participants(request, board_id):
    board = get_object_or_404(Board, pk=board_id, teacher__user=request.user)
    action = request.POST.get('action')
    user_id = request.POST.get('user_id')

    if action == 'add':
        # добавлять можно только своих учеников
        student_user = get_object_or_404(User, pk=user_id, student_profile__teachers=board.teacher)
        BoardParticipant.objects.get_or_create(board=board, user=student_user)
        return JsonResponse({'status': 'success', 'message': 'Ученик добавлен на доску'})

    if action == 'remove':
        BoardParticipant.objects.filter(board=board, user_id=user_id).delete()
        async_to_sync(get_channel_layer().group_send)(
            f'board_{board.id}', {'type': 'access_revoked', 'user_id': str(user_id)}
        )
        return JsonResponse({'status': 'success', 'message': 'Ученик исключен с доски'})

    return JsonResponse({'status': 'error'}, status=400)


@login_required
@require_http_methods(['GET', 'POST'])
def board_data_api(request, board_id):
    board = get_object_or_404(Board, pk=board_id)
    role, can_edit = get_board_access(request.user, board)
    if role is None:
        return JsonResponse({'status': 'error', 'message': 'forbidden'}, status=403)

    if request.method == 'GET':
        objects = list(board.board_objects.order_by('created_at').values('object_id', 'data'))
        return JsonResponse({'status': 'success', 'objects': objects})

    if not can_edit:
        return JsonResponse({'status': 'error', 'message': 'read-only'}, status=403)

    try:
        payload = json.loads(request.body)
    except ValueError:
        return JsonResponse({'status': 'error', 'message': 'bad json'}, status=400)

    action = payload.get('action')

    if action == 'save':
        obj_data = payload.get('object')
        if not isinstance(obj_data, dict):
            return JsonResponse({'status': 'error', 'message': 'object required'}, status=400)
        obj_id = str(obj_data.get('id') or uuid.uuid4())
        if len(obj_id) > 100:
            return JsonResponse({'status': 'error', 'message': 'id too long'}, status=400)
        obj_data['id'] = obj_id
        board.board_objects.update_or_create(object_id=obj_id, defaults={'data': obj_data})
        return JsonResponse({'status': 'success', 'object_id': obj_id})

    if action == 'remove':
        board.board_objects.filter(object_id=payload.get('object_id')).delete()
        return JsonResponse({'status': 'success'})

    if action == 'clear':
        # Полная очистка доски — только учитель-владелец (ученик получает 403, даже если подделает запрос)
        if role != 'teacher':
            return JsonResponse({'status': 'error', 'message': 'teacher only'}, status=403)
        deleted, _ = board.board_objects.all().delete()
        return JsonResponse({'status': 'success', 'deleted': deleted})

    return JsonResponse({'status': 'error', 'message': 'unknown action'}, status=400)


@login_required
def board_participants_api(request, board_id):
    board = get_object_or_404(Board, pk=board_id, teacher__user=request.user)

    participants = list(BoardParticipant.objects.filter(board=board).select_related('user'))
    keys = {conn_key(board_id, p.user_id): p for p in participants}
    online = cache.get_many(keys.keys())          # {ключ: число соединений}

    data = [{
        'id': str(p.user.id),
        'name': _full_name(p.user),
        'joined_at': p.joined_at.strftime('%H:%M %d.%m.%Y'),
    } for key, p in keys.items() if online.get(key, 0) > 0]
    return JsonResponse({'status': 'success', 'participants': data})