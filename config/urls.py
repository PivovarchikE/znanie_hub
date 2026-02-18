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

    # registration
    path('select-role/', users_views.select_role, name='select_role'),
    # <slug:role_slug> — это "ловушка", которая поймает любое слово после /register/
    path('register/<slug:role_slug>/', users_views.dynamic_register_view, name='dynamic_register'),
    path('login/', users_views.login_view, name='login'),
    path('logout/', users_views.logout_view, name='logout'),
]
