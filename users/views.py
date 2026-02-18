from django.contrib import messages
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout, get_user_model
from django.core.paginator import Paginator
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.forms import inlineformset_factory

from courses import models
from users.forms import TeacherProfileForm, StudentProfileForm, UserRegistrationForm, PhoneFormSet, UserPhoneNumberForm, \
    BasePhoneFormSet
from users.models import StudentProfile, TeacherProfile, Role, UserPhoneNumber


def select_role(request):
    return render(request, 'registration/register_select_role.html')


def dynamic_register_view(request, role_slug):

    # Находим роль в базе данных по слагу из URL
    role = get_object_or_404(Role, slug=role_slug)

    # Определяем, какую форму профиля использовать
    # (маппинг 'слаг': 'класс_формы')
    form_map = {
        'teacher': TeacherProfileForm,
        'student': StudentProfileForm,
    }
    profile_form_class = form_map.get(role_slug)

    if not profile_form_class:
        raise Http404("Такой роли не существует")

    if request.method == 'POST':
        u_form = UserRegistrationForm(request.POST)
        p_form = profile_form_class(request.POST)

        phone_formset = PhoneFormSet(
            request.POST,
            form_kwargs={'role_slug': role_slug}
        )

        phone_formset.role_slug = role_slug

        if u_form.is_valid() and p_form.is_valid() and phone_formset.is_valid():
            # Сохраняем пользователя (User)
            # Используем commit=False, чтобы успеть захешировать пароль и назначить роль
            user = u_form.save(commit=False)

            # Берем "сырой" пароль из очищенных данных формы
            raw_password = u_form.cleaned_data.get('password')

            # Хешируем его
            user.set_password(raw_password)

            user.role = role
            user.save()

            # СРАЗУ сохраняем M2M для пользователя (например, предметы 'subjects')
            # так как объект user уже получил ID в базе
            u_form.save_m2m()

            # Сохраняем профиль (TeacherProfile или StudentProfile)
            profile = p_form.save(commit=False)
            profile.user = user  # Привязываем профиль к только что созданному юзеру
            profile.save()

            # Сохраняем M2M для профиля (например, 'school_classes' у учителя)
            p_form.save_m2m()

            # Сохраняем телефоны из Formset
            # Здесь тоже используем commit=False, чтобы вручную привязать каждый телефон к юзеру
            phones = phone_formset.save(commit=False)
            for phone in phones:
                phone.user = user
                # Если это учитель, сохраняем только тип "Личный", даже если во фронтенде что-то подменили
                if role.slug == 'teacher':
                    phone.relationship = UserPhoneNumber.RelationshipType.OWN
                phone.save()

            # Обработка удалений (если юзер нажал на кнопку удаления существующих)
            for obj in phone_formset.deleted_objects:
                obj.delete()

            # Если в формсете были удаления (can_delete=True), это их обработает
            phone_formset.save_m2m()

            messages.success(request, 'Вы успешно зарегистрировались! Войдите в систему.')

            return redirect('login')

    else:
        # GET
        u_form = UserRegistrationForm()
        p_form = profile_form_class()
        phone_formset = PhoneFormSet(queryset=UserPhoneNumber.objects.none())

    context = {
        'u_form': u_form,
        'p_form': p_form,
        'role': role,
        'role_display': role.name,
        'phone_formset': phone_formset,
    }
    return render(request, 'registration/register.html', context)



def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('index')
    else:
        form = AuthenticationForm()
    return render(request, 'registration/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('index')