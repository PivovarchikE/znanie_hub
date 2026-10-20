import io
import os
from collections import defaultdict

from PIL import Image
from django.contrib import messages
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import Http404
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth import login, logout, get_user_model
from django.core.paginator import Paginator
from django.urls import reverse_lazy, reverse
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.forms import inlineformset_factory

from courses import models
from users.forms import TeacherProfileForm, StudentProfileForm, UserRegistrationForm, PhoneFormSet, UserPhoneNumberForm, \
    BasePhoneFormSet, UserProfileEditForm, AvatarUpdateForm, StudentGroupForm
from users.models import StudentProfile, TeacherProfile, Role, UserPhoneNumber, StudentGroup


# from.form
@require_http_methods(["GET", "POST"])
def dynamic_register_view(request, role_slug):
    # Чтобы обычный пользователь (не учитель) не мог регистрировать других
    if request.user.is_authenticated:
        if request.user.role.slug != 'teacher' or role_slug != 'student':
            return redirect('index')

    role = get_object_or_404(Role, slug=role_slug)
    form_map = {
        'teacher': TeacherProfileForm,
        'student': StudentProfileForm,
    }
    profile_form_class = form_map.get(role_slug)

    if not profile_form_class:
        raise Http404("Такой роли не существует")

    if request.method == 'POST':
        u_form = UserRegistrationForm(request.POST, slug=role_slug)
        p_form = profile_form_class(request.POST)
        phone_formset = PhoneFormSet(request.POST, form_kwargs={'role_slug': role_slug})

        if u_form.is_valid() and p_form.is_valid() and phone_formset.is_valid():
            try:
                with transaction.atomic():
                    # 1. Сохраняем User
                    user = u_form.save(commit=False)
                    user.set_password(u_form.cleaned_data.get('password'))
                    user.role = role
                    user.save()
                    u_form.save_m2m()

                    # 2. Сохраняем Profile
                    profile = p_form.save(commit=False)
                    profile.user = user
                    profile.save()
                    p_form.save_m2m()

                    # 3. ПРИВЯЗКА УЧИТЕЛЯ
                    if role_slug == 'student' and request.user.is_authenticated:
                        if hasattr(request.user, 'teacher_profile'):
                            # Используем .add(), так как teachers — это ManyToManyField
                            profile.teachers.add(request.user.teacher_profile)

                    # 4. Сохраняем телефоны
                    phones = phone_formset.save(commit=False)
                    for phone in phones:
                        phone.user = user
                        if role.slug == 'teacher':
                            phone.relationship = UserPhoneNumber.RelationshipType.OWN
                        phone.save()

                    phone_formset.save_m2m()
                    for obj in phone_formset.deleted_objects:
                        obj.delete()

                # Редиректы после успешной транзакции
                if request.user.is_authenticated and request.user.role.slug == 'teacher':
                    messages.success(request, f'Ученик {user.get_full_name()} успешно зарегистрирован и добавлен в ваш список.')
                    return redirect('teacher_dashboard')

                messages.success(request, 'Вы успешно зарегистрированы! Войдите в систему')
                return redirect('login')

            except Exception as e:
                messages.error(request, f'Ошибка при сохранении: {e}')

    else:
        # GET
        u_form = UserRegistrationForm(slug=role_slug)
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


@require_http_methods(['POST', 'GET'])
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


@login_required
@require_GET
def logout_view(request):
    logout(request)
    return redirect('index')


@login_required
@require_http_methods(['POST', 'GET'])
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
        u_form = UserProfileEditForm(request.POST, instance=user, slug=role_slug)
        p_form = profile_form_class(request.POST, instance=profile_instance)
        phone_formset = PhoneFormSet(
            request.POST,
            instance=user,
            form_kwargs={'role_slug': role_slug}
        )
        phone_formset.role_slug = role_slug

        if u_form.is_valid() and p_form.is_valid() and phone_formset.is_valid():
            u_form.save()
            profile = p_form.save()

            if hasattr(p_form, 'save_m2m'):
                p_form.save_m2m()

            phone_formset.save()

            messages.success(request, 'Профиль успешно обновлен!')
            return redirect('profile_edit')
    else:

        u_form = UserProfileEditForm(instance=request.user, slug=role_slug)
        p_form = profile_form_class(instance=profile_instance)

        phone_formset = PhoneFormSet(instance=user, form_kwargs={'role_slug': role_slug})
        if user.phones.exists():
            phone_formset.extra = 0

    context = {
        'form': u_form,
        'u_form': u_form,
        'p_form': p_form,
        'phone_formset': phone_formset,
        'role_display': user.role.name,
        'role_slug': role_slug,
        'student': profile_instance,
    }
    return render(request, 'profile_edit.html', context)


@login_required
@require_http_methods(['POST', 'GET'])
def avatar_update_view(request):
    user = request.user

    if request.method == 'POST':
        # ЛОГИКА УДАЛЕНИЯ АВАТАРА
        if 'delete_avatar' in request.POST:
            if user.avatar:
                old_path = user.avatar.path
                if os.path.isfile(old_path):
                    os.remove(old_path)  # Удаляем только файл
                user.avatar = None  # Стираем путь в базе
                user.save()
                messages.success(request, 'Аватар удален')
            return redirect('avatar_update')

        # ЛОГИКА ОБНОВЛЕНИЯ И ОБРЕЗКИ
        form = AvatarUpdateForm(request.POST, request.FILES, instance=user)
        if form.is_valid():
            x = request.POST.get('x')
            y = request.POST.get('y')
            w = request.POST.get('width')
            h = request.POST.get('height')

            if x and y and w and h and 'avatar' in request.FILES:
                img = Image.open(request.FILES['avatar'])

                # Обрезка
                cropped_img = img.crop((
                    float(x), float(y),
                    float(x) + float(w), float(y) + float(h)
                ))

                # Ресайз и сжатие
                cropped_img = cropped_img.resize((400, 400), Image.LANCZOS)

                buffer = io.BytesIO()
                if cropped_img.mode in ("RGBA", "P"):
                    cropped_img = cropped_img.convert("RGB")
                cropped_img.save(buffer, format='JPEG', quality=85, optimize=True)

                # УДАЛЯЕМ СТАРЫЙ АВАТАР ПЕРЕД СОХРАНЕНИЕМ НОВОГО
                if user.avatar:
                    old_path = user.avatar.path
                    if os.path.isfile(old_path):
                        os.remove(old_path)

                filename = f"avatar_user_{user.id}.jpg"
                user.avatar.save(filename, ContentFile(buffer.getvalue()), save=False)

            user.save()
            messages.success(request, 'Аватар успешно обновлен!')
            return redirect('avatar_update')

    else:
        form = AvatarUpdateForm(instance=user)

    return render(request, 'avatar_update.html', {'form': form})


class UserPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password_change.html'
    success_url = reverse_lazy('password_change')

    def form_valid(self, form):
        messages.success(self.request, 'Пароль успешно изменен!')
        return super().form_valid(form)


@login_required
def group_create_view(request):
    """Создание новой группы учеников"""
    teacher_profile = getattr(request.user, 'teacher_profile', None)
    if not teacher_profile:
        messages.error(request, "Доступ разрешен только преподавателям.")
        return redirect('teacher_dashboard')

    if request.method == 'POST':
        form = StudentGroupForm(request.POST, teacher_profile=teacher_profile)
        if form.is_valid():
            group = form.save(commit=False)
            group.teacher = teacher_profile
            group.is_active = True  # <--- Автоматически делаем группу активной
            group.save()
            form.save_m2m()
            messages.success(request, f'Группа "{group.name}" успешно создана!')
            return redirect('group_detail', pk=group.pk)
    else:
        form = StudentGroupForm(teacher_profile=teacher_profile)

    return render(request, 'group_form.html', {
        'form': form,
        'title': 'Создание группы'
    })


@login_required
def group_edit_view(request, pk):
    """Редактирование существующей группы"""
    teacher_profile = getattr(request.user, 'teacher_profile', None)
    group = get_object_or_404(StudentGroup, pk=pk, teacher=teacher_profile)

    if request.method == 'POST':
        form = StudentGroupForm(request.POST, instance=group, teacher_profile=teacher_profile)
        if form.is_valid():
            form.save()
            messages.success(request, f'Группа "{group.name}" обновлена.')
            return redirect('group_detail', pk=group.pk)
    else:
        form = StudentGroupForm(instance=group, teacher_profile=teacher_profile)

    return render(request, 'group_form.html', {
        'form': form,
        'group': group,
        'title': f'Редактирование: {group.name}'
    })


@login_required
def group_detail_view(request, pk):
    teacher_profile = getattr(request.user, 'teacher_profile', None)
    if not teacher_profile:
        raise PermissionDenied("Доступ разрешен только преподавателям.")

    group = get_object_or_404(
        StudentGroup.objects.prefetch_related('students__user', 'students__school_class'),
        pk=pk,
        teacher=teacher_profile
    )

    grouped_homeworks = get_grouped_homeworks_for_group(group)

    # Проверяем, откуда пришел пользователь
    from_param = request.GET.get('from')
    if from_param == 'schedule':
        back_url = reverse('schedule:list')
        back_label = 'Назад к расписанию'
    else:
        back_url = f"{reverse('teacher_dashboard')}#groups"  # или URL списка групп
        back_label = 'Назад к списку групп'

    context = {
        'group': group,
        'grouped_homeworks': grouped_homeworks,
        'back_url': back_url,
        'back_label': back_label,
    }

    return render(request, 'group_detail.html', context)


@login_required
def complete_group_view(request, pk):
    """Перевод группы в статус 'Обучение завершено'"""
    teacher_profile = getattr(request.user, 'teacher_profile', None)
    if not teacher_profile:
        return redirect('home')

    group = get_object_or_404(StudentGroup, pk=pk, teacher=teacher_profile)

    if request.method == 'POST':
        group.status = 'completed'
        group.save()
        messages.success(request, f'Группа "{group.name}" переведена в статус "Обучение завершено".')

    return redirect(f"{request.META.get('HTTP_REFERER', '/')}#groups")


def get_grouped_homeworks_for_group(group):
    """
    Получает все домашние задания группы и группирует их по единым выданным таскам.
    """
    homeworks = (
        models.Homework.objects
        .filter(group=group)
        .select_related('subject', 'student__user')
        .order_by('-created_at')
    )

    grouped_homeworks = defaultdict(list)

    for hw in homeworks:
        group_key = (
            hw.title,
            hw.subject.name if hw.subject else '—',
            hw.hw_type,
            hw.get_hw_type_display(),
            hw.deadline,
        )
        grouped_homeworks[group_key].append(hw)

    return dict(grouped_homeworks)
