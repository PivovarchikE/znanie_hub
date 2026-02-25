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
    BasePhoneFormSet, UserProfileEditForm
from users.models import StudentProfile, TeacherProfile, Role, UserPhoneNumber


def select_role(request):
    return render(request, 'registration/register_select_role.html')


# добавить транзакции для сохранения
# from.form
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

            # если регистрировал учитель, то привязываем его id к профилю студента
            if role_slug == 'student' and request.user.is_authenticated:
                if hasattr(request.user, 'role') and request.user.role.slug == 'teacher':
                    # Привязываем к полю teacher в StudentProfile профиль текущего юзера
                    profile.teacher = request.user.teacher_profile

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

            if request.user.is_authenticated and request.user.role.slug == 'teacher':
                messages.success(request,
                                 f'Ученик {user.get_full_name()} успешно зарегистрирован и добавлен в ваш список.')
                return redirect('teacher_dashboard')

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


@login_required
def profile_edit_view(request):
    user = request.user
    role_slug = user.role.slug

    form_map = {
        'teacher': (TeacherProfileForm, TeacherProfile),
        'student': (StudentProfileForm, StudentProfile),
    }

    profile_form_class, profile_model = form_map.get(role_slug)

    profile_instance = get_object_or_404(profile_model, user=user)

    if request.method == 'POST':
        u_form = UserProfileEditForm(request.POST, instance=user)
        p_form = profile_form_class(request.POST, instance=profile_instance)
        phone_formset = PhoneFormSet(
            request.POST,
            instance=user,
            form_kwargs={'role_slug': role_slug}
        )

        if u_form.is_valid() and p_form.is_valid() and phone_formset.is_valid():
            u_form.save()
            profile = p_form.save()

            if hasattr(p_form, 'save_m2m'):
                p_form.save_m2m()

            phone_formset.save()

            messages.success(request, 'Профиль успешно обновлен!')
            return redirect('profile_edit')
    else:

        u_form = UserProfileEditForm(instance=user)
        p_form = profile_form_class(instance=profile_instance)

        phone_formset = PhoneFormSet(instance=user, form_kwargs={'role_slug': role_slug})
        if user.phones.exists():
            phone_formset.extra = 0

    context = {
        'u_form': u_form,
        'p_form': p_form,
        'phone_formset': phone_formset,
        'role_display': user.role.name,
        'role_slug': role_slug,
    }
    return render(request, 'profile_edit.html', context)