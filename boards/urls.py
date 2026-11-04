from django.urls import path, re_path
from . import views, consumers

app_name = "boards"

urlpatterns = [
    path('board/open/<str:entity_type>/<int:entity_id>/', views.open_entity_board, name='open_entity_board'),
    path('board/<uuid:board_id>/', views.board_room_view, name='board_room'),
    path('board/<uuid:board_id>/participants/', views.manage_board_participants, name='manage_board_participants'),
    path('board/<uuid:board_id>/api/data/', views.board_data_api, name='board_data_api'),
    path('board/<uuid:board_id>/api/participants/', views.board_participants_api, name='board_participants_api'),
]

websocket_urlpatterns = [
    re_path(r'ws/board/(?P<board_id>[0-9a-f-]+)/$', consumers.BoardConsumer.as_asgi()),
]