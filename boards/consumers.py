import json

from asgiref.sync import sync_to_async
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache
from django.core.exceptions import ValidationError

from .access import get_board_access
from .models import Board

CONN_TTL = 90                       # секунд; клиент пингует каждые 25 с и продлевает ключ
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # 10 МБ (картинки идут как data-URL)


def conn_key(board_id, user_id):
    # Единый формат ключа: его же использует board_participants_api
    return f'board_conn_{board_id}_{user_id}'


# ---- Счётчик соединений пользователя (атомарные incr/decr, а не get/set набора) ----

@sync_to_async
def _conn_open(key):
    try:
        n = cache.incr(key)
    except ValueError:            # ключа ещё нет
        cache.set(key, 1, CONN_TTL)
        n = 1
    cache.touch(key, CONN_TTL)
    return n


@sync_to_async
def _conn_close(key):
    try:
        n = cache.decr(key)
    except ValueError:            # ключ уже истёк
        n = 0
    if n <= 0:
        cache.delete(key)
        n = 0
    return n


@sync_to_async
def _conn_touch(key):
    if not cache.touch(key, CONN_TTL):
        cache.set(key, 1, CONN_TTL)


@database_sync_to_async
def _get_access(user, board_id):
    try:
        board = Board.objects.select_related('teacher').get(pk=board_id)
    except (Board.DoesNotExist, ValueError, ValidationError):
        return None, False
    return get_board_access(user, board)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


class BoardConsumer(AsyncWebsocketConsumer):
    registered = False   # прошёл ли пользователь проверку и попал в группу

    async def connect(self):
        self.board_id = str(self.scope['url_route']['kwargs']['board_id'])
        self.room_group_name = f'board_{self.board_id}'
        self.user = self.scope['user']

        # Принимаем и сразу закрываем с кодом: клиент увидит 4401/4403 и не будет переподключаться.
        # В группу при этом не добавляем, так что ничего из доски не утекает.
        if not self.user.is_authenticated:
            await self.accept()
            await self.close(code=4401)
            return

        self.role, self.can_edit = await _get_access(self.user, self.board_id)
        if self.role is None:
            await self.accept()
            await self.close(code=4403)
            return

        self.user_id = str(self.user.id)
        self.user_name = self.user.get_full_name() or self.user.username
        self.conn_key = conn_key(self.board_id, self.user_id)

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        self.registered = True

        # Уведомляем остальных только при первом соединении пользователя (не при второй вкладке)
        if await _conn_open(self.conn_key) == 1:
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'user_joined_board',
                'user_id': self.user_id,
                'user_name': self.user_name,
            })

    async def disconnect(self, close_code):
        if not self.registered:
            return
        self.registered = False

        fully_left = (await _conn_close(self.conn_key)) == 0
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

        # «Ушёл» — только когда закрылась последняя вкладка
        if fully_left:
            await self.channel_layer.group_send(self.room_group_name, {
                'type': 'user_left_board',
                'user_id': self.user_id,
            })

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data or not self.registered or len(text_data) > MAX_MESSAGE_SIZE:
            return
        try:
            content = json.loads(text_data)
        except json.JSONDecodeError:
            return
        if not isinstance(content, dict):
            return

        event_type = content.get('type')

        if event_type == 'ping':
            await _conn_touch(self.conn_key)
            await self.send(text_data=json.dumps({'type': 'pong'}))
            return

        # Собираем исходящее сообщение сами, из белого списка полей
        if event_type == 'cursor_move':
            x, y = content.get('x'), content.get('y')
            if not (_is_num(x) and _is_num(y)):
                return
            msg = {'type': 'cursor_move', 'x': x, 'y': y}

        elif event_type == 'teacher_sync':
            if self.role != 'teacher':            # синхронизировать вид может только учитель
                return
            zoom, vpt = content.get('zoom'), content.get('vpt')
            if not (_is_num(zoom) and isinstance(vpt, list) and len(vpt) == 6
                    and all(_is_num(v) for v in vpt)):
                return
            msg = {'type': 'teacher_sync', 'zoom': zoom, 'vpt': vpt}

        elif event_type == 'canvas_action':
            if not self.can_edit:                 # режим «только просмотр»
                return
            sub = content.get('subType')
            if sub == 'save' and isinstance(content.get('object'), dict):
                msg = {'type': 'canvas_action', 'subType': 'save', 'object': content['object']}
            elif sub == 'remove' and isinstance(content.get('object_id'), str):
                msg = {'type': 'canvas_action', 'subType': 'remove', 'object_id': content['object_id']}
            elif sub == 'clear':
                if self.role != 'teacher':        # очищать доску целиком может только учитель
                    return
                msg = {'type': 'canvas_action', 'subType': 'clear'}
            else:
                return
        else:
            return

        # userId и userName всегда берём с сервера, а не из сообщения клиента
        msg['userId'] = self.user_id
        msg['userName'] = self.user_name

        await self.channel_layer.group_send(self.room_group_name, {
            'type': 'board_message',
            'content': msg,
            'sender': self.channel_name,
        })

    # ---- Обработчики событий группы ----

    async def board_message(self, event):
        if event.get('sender') == self.channel_name:   # себе не шлём
            return
        await self.send(text_data=json.dumps(event['content']))

    async def user_joined_board(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_joined_board',
            'user_id': event['user_id'],
            'user_name': event['user_name'],
        }))

    async def user_left_board(self, event):
        await self.send(text_data=json.dumps({
            'type': 'user_left_board',
            'user_id': event['user_id'],
        }))

    async def access_revoked(self, event):
        # Учитель исключил пользователя — разрываем его соединение
        if event['user_id'] == self.user_id:
            await self.close(code=4403)