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
from django.urls import path

from courses import views as courses_views
from users import views as users_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path('', courses_views.index, name='index'),
    path('thanks/', courses_views.thanks, name='thanks'),

    # registration
    path('select-role/', users_views.select_role, name='select_role'),
    # <slug:role_slug> — это "ловушка", которая поймает любое слово после /register/
    path('register/<slug:role_slug>/', users_views.dynamic_register_view, name='dynamic_register'),
    path('login/', users_views.login_view, name='login'),
    path('logout/', users_views.logout_view, name='logout'),
    # profile and dashboards
    path('profile_edit/', users_views.profile_edit_view, name='profile_edit'),
    path('dashboard/', courses_views.teacher_dashboard_view, name='teacher_dashboard'),
    path('dashboard/student/<int:student_id>/', courses_views.student_detail_view, name='student_detail'),
    path('dashboard/student/<int:student_id>/add-homework/', courses_views.add_homework_view, name='add_homework'),

    # math
    path('math', courses_views.math_index, name='math_index'),
    # универсальная страница тренажеров и теории
    path('topic/<int:topic_id>/', courses_views.topic_detail, name='topic_detail'),
    # сохранение результатов
    path('save_training_result/', courses_views.save_training_result, name='save_training_result'),
]
