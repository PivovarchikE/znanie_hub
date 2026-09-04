from django.urls import path
from . import views

app_name = "schedule"  # Пространство имён для URL

urlpatterns = [
    path("", views.schedule_dashboard_view, name="list"),

    # API эндпоинты для Alpine.js
    path("api/get-week/", views.get_week_schedule_api, name="api_get_week"),
    path("api/save/", views.save_lesson_api, name="api_save"),
    path("api/delete/<int:lesson_id>/", views.delete_lesson_api, name="api_delete"),
]
