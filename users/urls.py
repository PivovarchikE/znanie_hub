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
    # registration
    path('select-role/', TemplateView.as_view(template_name='registration/register_select_role.html'), name='select_role'),

    # <slug:role_slug> — это "ловушка", которая поймает любое слово после /register/
    path('register/<slug:role_slug>/', users_views.dynamic_register_view, name='dynamic_register'),
    path('login/', users_views.login_view, name='login'),
    path('logout/', users_views.logout_view, name='logout'),

    # profile and dashboards
    path('profile_edit/', users_views.profile_edit_view, name='profile_edit'),
    path('profile/avatar/', users_views.avatar_update_view, name='avatar_update'),
    path('profile/password/', users_views.UserPasswordChangeView.as_view(), name='password_change'),
]
