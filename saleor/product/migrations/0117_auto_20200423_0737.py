# Generated by Django 3.0.5 on 2020-04-23 12:37

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0116_auto_20200225_0237"),
    ]

    operations = [
        migrations.AlterField(
            model_name="producttranslation",
            name="name",
            field=models.CharField(max_length=250),
        ),
    ]
