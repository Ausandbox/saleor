# Generated by Django 3.2.18 on 2023-05-15 11:45

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('order', '0164_auto_20230329_1200'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderline',
            name='price_override',
            field=models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True),
        ),
    ]
