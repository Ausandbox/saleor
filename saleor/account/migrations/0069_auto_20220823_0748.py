# Generated by Django 3.2.15 on 2022-08-23 07:48
from django.contrib.postgres.functions import RandomUUID
from django.db import migrations


def fill_missing_uuid_on_users(apps, _schema_editor):
    User = apps.get_model("account", "User")
    User.objects.update(uuid=RandomUUID())


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0068_user_uuid"),
    ]

    operations = [
        migrations.RunPython(
            fill_missing_uuid_on_users, reverse_code=migrations.RunPython.noop
        ),
    ]
