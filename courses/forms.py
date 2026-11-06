from django.core.exceptions import ValidationError
from django.forms import ModelForm, inlineformset_factory, Select, TextInput, Textarea, DateTimeInput, FileInput, JSONField, HiddenInput

from .generators import get_picker, sanitize_selection
from .models import Homework, HomeworkFile, SimulatorConfig, Section, Topic


class HomeworkFileForm(ModelForm):
    class Meta:
        model = HomeworkFile
        fields = ['file']
        widgets = {
            'file': FileInput(attrs={'class': 'form-control'})
        }

    def clean_file(self):
        file = self.cleaned_data.get('file')
        if file:
            # Ограничение 10 МБ (10 * 1024 * 1024 байт)
            if file.size > 10 * 1024 * 1024:
                raise ValidationError("Размер файла не должен превышать 10 МБ.")
        return file


class HomeworkForm(ModelForm):
    class Meta:
        model = Homework
        fields = ['subject', 'section', 'topic', 'hw_type', 'title', 'content', 'simulator_config', 'simulator_settings',  'deadline']
        widgets = {
            'subject': Select(attrs={'class': 'form-select', 'id': 'id_subject'}),
            'section': Select(attrs={'class': 'form-select', 'id': 'id_section'}),
            'topic': Select(attrs={'class': 'form-select', 'id': 'id_topic'}),
            'hw_type': Select(attrs={'class': 'form-select', 'id': 'id_hw_type'}),
            'title': TextInput(attrs={'class': 'form-control', 'placeholder': 'Напр: Контрольная работа по сложению'}),
            'content': Textarea(
                attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Дополнительные инструкции для ученика...'}),
            'simulator_config': Select(attrs={'class': 'form-select', 'id': 'id_simulator_config'}),
            'deadline': DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }

    simulator_settings = JSONField(required=False, widget=HiddenInput)

    def clean(self):
        cd = super().clean()
        hw_type = cd.get('hw_type')
        topic = cd.get('topic')

        if hw_type == 'simulator':
            if not topic:
                self.add_error('topic', 'Для тренажера выберите тему.')
            if not cd.get('simulator_config'):
                self.add_error('simulator_config', 'Выберите конфигурацию тренажера.')
        elif hw_type == 'interactive_theory':
            if not topic:
                self.add_error('topic', 'Для интерактивной теории выберите тему.')
            elif not (topic.text_content or '').strip():
                self.add_error('topic', 'У выбранной темы нет теории на сайте.')
            cd['simulator_config'] = None
        else:  # theory / practice
            cd['simulator_config'] = None

        # Настройки тренажера: только для simulator и только если у конфига есть выбор
        config = cd.get('simulator_config')
        if hw_type == 'simulator' and config and get_picker(config.params) and not config.params.get('locked'):
            try:
                cd['simulator_settings'] = sanitize_selection(config.params, cd.get('simulator_settings'))
            except ValueError as e:
                self.add_error(None, str(e))
        else:
            cd['simulator_settings'] = None
        return cd

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['section'].queryset = Section.objects.none()
        self.fields['topic'].queryset = Topic.objects.none()
        self.fields['simulator_config'].queryset = SimulatorConfig.objects.none()

        data = args[0] if args and args[0] else None
        instance = kwargs.get('instance')

        if data:
            self._set_dynamic_quarters(
                subject_id=data.get('subject'),
                section_id=data.get('section'),
                topic_id=data.get('topic')
            )
        elif instance and instance.pk:
            subject_id = instance.subject_id
            if not subject_id and instance.topic and instance.topic.section:
                subject_id = instance.topic.section.subject_id

            section_id = instance.section_id
            if not section_id and instance.topic:
                section_id = instance.topic.section_id

            self._set_dynamic_quarters(
                subject_id=subject_id,
                section_id=section_id,
                topic_id=instance.topic_id
            )

    def _set_dynamic_quarters(self, subject_id=None, section_id=None, topic_id=None):
        """Вспомогательный метод для фильтрации выпадающих списков с учетом подразделов"""
        if subject_id:
            self.fields['section'].queryset = Section.objects.filter(subject_id=subject_id)

        topic_qs = Topic.objects.none()

        # Рекурсивная функция для сбора ID раздела и всех его подразделов
        def get_all_subsections_ids(sec_id):
            if not sec_id:
                return []
            ids = [int(sec_id)]
            sub_ids = list(Section.objects.filter(parent_id=sec_id).values_list('id', flat=True))
            for sub_id in sub_ids:
                ids.extend(get_all_subsections_ids(sub_id))
            return ids

        if section_id:
            section_ids = get_all_subsections_ids(section_id)
            topic_qs = Topic.objects.filter(section_id__in=section_ids)

        if topic_id:
            try:
                t = Topic.objects.select_related('section').get(pk=topic_id)
                sub_ids = get_all_subsections_ids(t.section_id)
                topic_qs = topic_qs | Topic.objects.filter(section_id__in=sub_ids) | Topic.objects.filter(pk=topic_id)
            except Topic.DoesNotExist:
                pass

        self.fields['topic'].queryset = topic_qs.distinct()

        if topic_id:
            configs = SimulatorConfig.objects.filter(topic_id=topic_id)
            self.fields['simulator_config'].queryset = configs

HomeworkFileFormSet = inlineformset_factory(
    Homework,
    HomeworkFile,
    form=HomeworkFileForm,
    extra=1,
    max_num=10,
    validate_max=True,
    can_delete=True,
    widgets={'file': FileInput(attrs={'class': 'form-control'})}
)
