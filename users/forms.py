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
            'placeholder': ''}),
        required=False
    )

    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'ivanov@yandex.by'
        }),
        required=False,
        help_text="Мы отправим подтверждение на этот адрес."
    )

    # проверить на наличие password field, наследование от create form?

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
        }),
        required=False
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
        ]


class TeacherProfileForm(forms.ModelForm):
    # Учитель: много предметов и много классов
    school_classes = forms.ModelMultipleChoiceField(
        label='Классы (преподавание)',
        queryset=SchoolClass.objects.all(),
        widget=forms.CheckboxSelectMultiple()
    )
    subjects = forms.ModelMultipleChoiceField(
        label='Изучаемые предметы',
        queryset=Subject.objects.all(),
        widget=forms.CheckboxSelectMultiple()
    )

    class Meta:
        model = TeacherProfile
        fields = ['school_classes', 'subjects']

class StudentProfileForm(forms.ModelForm):
    # Ученик: много предметов, но только ОДИН класс
    school_class = forms.ModelChoiceField(
        label='Ваш класс',
        queryset=SchoolClass.objects.all(),
        empty_label="Выберите класс",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    subjects = forms.ModelMultipleChoiceField(
        label='Изучаемые предметы',
        queryset=Subject.objects.all(),
        widget=forms.CheckboxSelectMultiple(),
        error_messages = {
        'required': 'Пожалуйста, выберите хотя бы один предмет.'
    }
    )

    class Meta:
        model = StudentProfile
        fields = ['school_class', 'subjects']


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
        primary_count = 0
        filled_forms_count = 0

        for form in self.forms:
            if form.cleaned_data.get('DELETE'):
                continue

            number = form.cleaned_data.get('number')

            if number:
                filled_forms_count += 1
                rel = form.cleaned_data.get('relationship')
                primary = form.cleaned_data.get('is_primary')

                if primary:
                    primary_count += 1

                if role_slug == 'teacher' and rel != UserPhoneNumber.RelationshipType.OWN:
                    form.add_error('relationship', "Учитель может добавлять только личные номера.")

        if filled_forms_count == 0:
            raise forms.ValidationError("Добавьте хотя бы один контактный номер телефона.")

        if filled_forms_count > 0 and primary_count == 0:
            self.forms[0].add_error('is_primary', "Выберите основной номер")
            raise forms.ValidationError("Один из номеров должен быть отмечен как основной.")

        if primary_count > 1:
            raise forms.ValidationError("Только один номер может быть основным. Пожалуйста, снимите лишние галочки.")


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


# здесь не учтена смена пароля
class UserProfileEditForm(forms.ModelForm):
    username = forms.CharField(label='Имя пользователя', widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(label='Фамилия', widget=forms.TextInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(label='Имя', widget=forms.TextInput(attrs={'class': 'form-control'}))
    middle_name = forms.CharField(label='Отчество', widget=forms.TextInput(attrs={'class': 'form-control'}))
    date_of_birth = forms.DateField(
        label='Дата рождения',
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )

    class Meta:
        model = User
        fields = ['username', 'last_name', 'first_name', 'middle_name', 'date_of_birth']


class StudentEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email'] # Поля, которые можно менять
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }


class AvatarUpdateForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['avatar']
        widgets = {
            'avatar': forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
        }