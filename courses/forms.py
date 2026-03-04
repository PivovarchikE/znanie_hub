from django.forms import ModelForm, inlineformset_factory, Select, TextInput, Textarea, DateTimeInput, FileInput
from .models import Homework, HomeworkFile, SimulatorConfig, Section, Topic


class HomeworkForm(ModelForm):
    class Meta:
        model = Homework
        fields = ['subject', 'section', 'topic', 'hw_type', 'title', 'content', 'simulator_config', 'deadline']
        widgets = {
            'subject': Select(attrs={'class': 'form-select', 'id': 'id_subject'}),
            'section': Select(attrs={'class': 'form-select', 'id': 'id_section'}),
            'topic': Select(attrs={'class': 'form-select', 'id': 'id_topic'}),
            'hw_type': Select(attrs={'class': 'form-select', 'id': 'id_hw_type'}),
            'title': TextInput(attrs={'class': 'form-control', 'placeholder': 'Напр: Умножение на 5'}),
            'content': Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'simulator_config': Select(attrs={'class': 'form-select'}),
            'deadline': DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1. Если форма отправлена (POST)
        if args and args[0]:
            data = args[0]
            if 'subject' in data and data.get('subject'):
                self.fields['section'].queryset = Section.objects.filter(subject_id=data.get('subject'))
            if 'section' in data and data.get('section'):
                self.fields['topic'].queryset = Topic.objects.filter(section_id=data.get('section'))
            if 'topic' in data and data.get('topic'):
                self.fields['simulator_config'].queryset = SimulatorConfig.objects.filter(topic_id=data.get('topic'))

        # 2. Если мы открыли форму для редактирования существующей записи
        elif self.instance.pk:
            if self.instance.subject:
                self.fields['section'].queryset = Section.objects.filter(subject=self.instance.subject)
            if self.instance.section:
                self.fields['topic'].queryset = Topic.objects.filter(section=self.instance.section)
            if self.instance.topic:
                self.fields['simulator_config'].queryset = SimulatorConfig.objects.filter(topic=self.instance.topic)

        # 3. Если это просто чистая форма (GET)
        else:
            self.fields['section'].queryset = Section.objects.none()
            self.fields['topic'].queryset = Topic.objects.none()
            self.fields['simulator_config'].queryset = SimulatorConfig.objects.none()

HomeworkFileFormSet = inlineformset_factory(
    Homework,
    HomeworkFile,
    fields=('file',),
    extra=1,
    can_delete=True,
    widgets={'file': FileInput(attrs={'class': 'form-control'})}
)