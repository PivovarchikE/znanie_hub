from django.db import migrations, models


def approve_existing_users(apps, schema_editor):
    """Все уже существующие пользователи считаются подтверждёнными."""
    User = apps.get_model('users', 'User')
    User._base_manager.update(is_validate=True)


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0015_alter_studentgroup_options_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="is_validate",
            field=models.BooleanField(
                default=False,
                help_text="Регистрация подтверждена администратором.",
                verbose_name="Подтверждён администратором",
            ),
        ),
        migrations.RunPython(approve_existing_users, migrations.RunPython.noop),
    ]
