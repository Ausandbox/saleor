# Generated by Django 3.2.12 on 2022-05-23 11:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0152_auto_20220523_0815'),
    ]

    operations = [
        migrations.AlterField(
            model_name='productvariant',
            name='original_id',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='productvariant',
            name='original_sku',
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
    ]
