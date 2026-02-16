from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.forms.models import BaseInlineFormSet

from courses.models import Subject
from users.models import TeacherProfile, UserPhoneNumber, StudentProfile, SchoolClass

User = get_user_model()


class UserRegistrationForm(forms.ModelForm):

    username = forms.CharField(
        label='Имя пользователя',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': ''}))

    last_name = forms.CharField(
        label='Фамилия',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': ''})
    )

    first_name = forms.CharField(
        label='Имя',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': ''})
    )

    middle_name = forms.CharField(
        label='Отчество',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': ''})
    )

    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'ivanov@yandex.by'
        }),
        help_text="Мы отправим подтверждение на этот адрес."
    )

    password = forms.CharField(
        label="Пароль",
        widget=forms.PasswordInput(attrs={'class': 'form-control',
            'placeholder': ''})
    )

    password_confirm = forms.CharField(
        label="Подтвердите пароль",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': ''})
    )

    date_of_birth = forms.DateField(
        label='Дата рождения',
        widget=forms.DateInput(attrs={
            'class': 'form-control',
            'type': 'date',
            'placeholder': ''
        })
    )

    subjects = forms.ModelMultipleChoiceField(
        label='Выберите предметы',
        queryset=Subject.objects.all(),
        widget=forms.CheckboxSelectMultiple()
    )


    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")

        # Проверяем совпадение
        if password and password_confirm and password != password_confirm:
            # Выдаем ошибку для поля подтверждения
            self.add_error('password_confirm', "Пароли не совпадают")

        return cleaned_data

    # порядок отображения на фронте
    class Meta:
        model = User
        fields = [
            'username',
            'last_name',
            'first_name',
            'middle_name',
            'date_of_birth',
            'email',
            'password',
            'password_confirm',
            'subjects'
        ]


class TeacherProfileForm(forms.ModelForm):
    # Учитель: много предметов и много классов
    school_classes = forms.ModelMultipleChoiceField(
        label='Классы (преподавание)',
        queryset=SchoolClass.objects.all(),
        widget=forms.CheckboxSelectMultiple()
    )

    class Meta:
        model = TeacherProfile
        fields = ['school_classes']

class StudentProfileForm(forms.ModelForm):
    # Ученик: много предметов, но только ОДИН класс
    school_class = forms.ModelChoiceField(
        label='Ваш класс',
        queryset=SchoolClass.objects.all(),
        empty_label="Выберите класс",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = StudentProfile
        fields = ['school_class']


class UserPhoneNumberForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.role_slug = kwargs.pop('role_slug', None)
        super().__init__(*args, **kwargs)

        # Сообщения об ошибках на русском языке
        self.fields['number'].error_messages = {'required': 'Введите номер телефона'}
        self.fields['relationship'].error_messages = {'required': 'Укажите, чей это номер'}

        # ДЕЛАЕМ ПОЛЯ НЕОБЯЗАТЕЛЬНЫМИ (чтобы не вылетало "This field is required")
        self.fields['is_primary'].required = False
        self.fields['relationship'].required = False
        self.fields['is_primary'].required = False

    class Meta:
        model = UserPhoneNumber
        fields = ['number', 'relationship', 'owner_name', 'is_primary']
        labels = {
            'number': 'Номер телефона',
            'relationship': 'Чей номер',
            'owner_name': 'Имя владельца',
            'is_primary': 'Основной',
        }

    def clean(self):
        cleaned_data = super().clean()
        # Важно: используем .get(), так как если номер не введен,
        # поле 'relationship' может отсутствовать в cleaned_data
        relationship = cleaned_data.get("relationship")

        # ЕСЛИ ЭТО УЧИТЕЛЬ, ПРИНУДИТЕЛЬНО СТАВИМ "ЛИЧНЫЙ"
        if self.role_slug == 'teacher':
            relationship = UserPhoneNumber.RelationshipType.OWN
            cleaned_data['relationship'] = relationship

        # Проверка логики
        # Если видишь такое уведомление, значит всё пошло не так)
        if self.role_slug == 'teacher' and relationship != UserPhoneNumber.RelationshipType.OWN:
            self.add_error('relationship', "Учитель может указывать только личные номера.")

        return cleaned_data


class BasePhoneFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        role_slug = getattr(self, 'role_slug', None)
        has_primary = False
        filled_forms_count = 0

        for form in self.forms:
            # Пропускаем формы, помеченные на удаление
            if form.cleaned_data.get('DELETE'):
                continue

            # Проверяем, ввел ли пользователь хоть что-то в номер
            # Используем .get(), так как при ошибках валидации поля 'number' может не быть в cleaned_data
            number = form.cleaned_data.get('number')

            if number:
                filled_forms_count += 1
                rel = form.cleaned_data.get('relationship')
                primary = form.cleaned_data.get('is_primary')

                if primary:
                    has_primary = True

                # Проверка роли
                if role_slug == 'teacher' and rel != UserPhoneNumber.RelationshipType.OWN:
                    form.add_error('relationship', "Учитель может добавлять только личные номера.")

        # Если вообще нет заполненных номеров
        if filled_forms_count == 0:
            raise forms.ValidationError("Добавьте хотя бы один контактный номер телефона.")

        # Если номера есть, но никто не "основной"
        if filled_forms_count > 0 and not has_primary:
            # кидаем ошибку в ПЕРВУЮ форму, чтобы подсветить её
            self.forms[0].add_error('is_primary', "Выберите основной номер")
            # И дублируем общим текстом сверху
            raise forms.ValidationError("Один из номеров должен быть отмечен как основной.")


# # Создаем Formset: привязываем номера к пользователю
PhoneFormSet = inlineformset_factory(
    User,
    UserPhoneNumber,
    form=UserPhoneNumberForm,
    formset=BasePhoneFormSet,
    extra=1,            # по умолчанию отображается 1 запись
    min_num=0,
    max_num=5,
    validate_min=True,  # проверка при сохранении на наличие хотя бы 1 значения
    can_delete=True,
)

