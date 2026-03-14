from django.forms import ModelForm, inlineformset_factory, Select, TextInput, Textarea, DateTimeInput, FileInput, \
    CheckboxInput
from .models import Homework, HomeworkFile, SimulatorConfig, Section, Topic


class HomeworkForm(ModelForm):
    class Meta:
        model = Homework
        fields = ['subject', 'section', 'topic', 'hw_type', 'title', 'content', 'simulator_config', 'deadline', 'include_site_theory']
        widgets = {
            'subject': Select(attrs={'class': 'form-select', 'id': 'id_subject'}),
            'section': Select(attrs={'class': 'form-select', 'id': 'id_section'}),
            'topic': Select(attrs={'class': 'form-select', 'id': 'id_topic'}),
            'hw_type': Select(attrs={'class': 'form-select', 'id': 'id_hw_type'}),
            'include_site_theory': CheckboxInput(attrs={'class': 'form-check-input'}),
            'title': TextInput(attrs={'class': 'form-control', 'placeholder': 'Напр: Контрольная работа по сложению'}),
            'content': Textarea(
                attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Дополнительные инструкции для ученика...'}),
            'simulator_config': Select(attrs={'class': 'form-select', 'id': 'id_simulator_config'}),
            'deadline': DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Начальные пустые наборы данных (QuerySets)
        self.fields['section'].queryset = Section.objects.none()
        self.fields['topic'].queryset = Topic.objects.none()
        self.fields['simulator_config'].queryset = SimulatorConfig.objects.none()

        # Логика динамического наполнения
        # Проверяем либо данные в POST (data), либо объект в БД (instance)
        data = args[0] if args and args[0] else None
        instance = kwargs.get('instance')

        if data:
            self._set_dynamic_quarters(
                subject_id=data.get('subject'),
                section_id=data.get('section'),
                topic_id=data.get('topic')
            )
        elif instance and instance.pk:
            self._set_dynamic_quarters(
                subject_id=instance.subject_id,
                section_id=instance.section_id,
                topic_id=instance.topic_id
            )

    def _set_dynamic_quarters(self, subject_id=None, section_id=None, topic_id=None):
        """Вспомогательный метод для фильтрации выпадающих списков"""
        if subject_id:
            self.fields['section'].queryset = Section.objects.filter(subject_id=subject_id)
        if section_id:
            self.fields['topic'].queryset = Topic.objects.filter(section_id=section_id)
        if topic_id:
            # Подтягиваем ВСЕ конфиги (и тренажеры, и самостоятельные) / добавить логику для самостоятельных
            configs = SimulatorConfig.objects.filter(topic_id=topic_id)
            self.fields['simulator_config'].queryset = configs

HomeworkFileFormSet = inlineformset_factory(
    Homework,
    HomeworkFile,
    fields=('file',),
    extra=1,
    can_delete=True,
    widgets={'file': FileInput(attrs={'class': 'form-control'})}
)
