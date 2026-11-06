import pytest
from courses.forms import HomeworkForm
from courses.models import SimulatorConfig


def _data(subject, section, topic, conf, settings):
    return {'subject': subject.id, 'section': section.id, 'topic': topic.id, 'hw_type': 'simulator',
            'title': 't', 'simulator_config': conf.id, 'simulator_settings': settings}


@pytest.mark.django_db
def test_form_sanitizes_settings(subject, section, topic):
    conf = SimulatorConfig.objects.create(topic=topic, label='Умн', params={'kind': 'multiplication_table'})
    form = HomeworkForm(data=_data(subject, section, topic, conf, '{"factor": "7", "x": 1}'))
    assert form.is_valid(), form.errors
    assert form.cleaned_data['simulator_settings'] == {'factor': '7'}


@pytest.mark.django_db
def test_form_rejects_bad_settings(subject, section, topic):
    conf = SimulatorConfig.objects.create(topic=topic, label='Умн', params={'kind': 'multiplication_division'})
    form = HomeworkForm(data=_data(subject, section, topic, conf, '{"operations": []}'))
    assert not form.is_valid()


@pytest.mark.django_db
def test_form_drops_settings_for_plain_config(subject, section, topic, simulator_config):
    form = HomeworkForm(data=_data(subject, section, topic, simulator_config, '{"factor": "7"}'))
    assert form.is_valid(), form.errors
    assert form.cleaned_data['simulator_settings'] is None


@pytest.mark.django_db
def test_form_persists_settings_on_instance(subject, section, topic):
    conf = SimulatorConfig.objects.create(topic=topic, label='Умн', params={'kind': 'multiplication_table'})
    form = HomeworkForm(data=_data(subject, section, topic, conf, '{"factor": "7"}'))
    assert form.is_valid(), form.errors
    assert form.instance.simulator_settings == {'factor': '7'}