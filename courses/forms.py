from django import forms
from .models import Homework, SimulatorConfig


class HomeworkForm(forms.ModelForm):
    class Meta:
        model = Homework
        fields = ['hw_type', 'title', 'content', 'simulator_config', 'deadline']
        widgets = {
            'hw_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_hw_type'}),
            'title': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Напр: Умножение на 5'}),
            'content': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'simulator_config': forms.Select(attrs={'class': 'form-select'}),
            'deadline': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
        }
