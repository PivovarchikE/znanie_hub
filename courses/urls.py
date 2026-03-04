"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView

from courses import views as courses_views
from users import views as users_views

urlpatterns = [
     # profile and dashboards
    path('dashboard/', courses_views.teacher_dashboard_view, name='teacher_dashboard'),
    path('dashboard/student/', courses_views.student_dashboard_view, name='student_dashboard'),
    path('dashboard/student/<int:student_id>/', courses_views.student_detail_view, name='student_detail'),
    path('dashboard/student/<int:student_id>/add-homework/', courses_views.add_homework_view, name='add_homework'),
    path('homework/<int:hw_id>/view/', courses_views.homework_view_detail, name='homework_view_detail'),
    path('homework/<int:hw_id>/edit/', courses_views.edit_homework_view, name='edit_homework'),
    path('homework/<int:hw_id>/delete/', courses_views.delete_homework_view, name='delete_homework'),
    path('student/<int:student_id>/edit/', courses_views.edit_student_view, name='edit_student'),
    path('student/<int:student_id>/delete/', courses_views.delete_student_view, name='delete_student'),
    path('api/homework-results/<int:hw_id>/', courses_views.get_homework_results_api, name='homework_results_api'),

    # Пути для AJAX-запросов (динамическая подгрузка)
    path('ajax/get-sections/', courses_views.get_sections, name='ajax_get_sections'),
    path('ajax/get-topics/', courses_views.get_topics, name='ajax_get_topics'),
    path('ajax/get-configs/', courses_views.get_configs, name='ajax_get_configs'),

    # math
    path('math', courses_views.math_index, name='math_index'),
    # универсальная страница тренажеров и теории
    path('topic/<int:topic_id>/', courses_views.topic_detail, name='topic_detail'),
    # сохранение результатов
    path('save_training_result/', courses_views.save_training_result, name='save_training_result'),
]
