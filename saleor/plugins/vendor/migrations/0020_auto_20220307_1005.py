# Generated by Django 3.2.10 on 2022-03-07 10:05

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("product", "0155_merge_20211208_1108"),
        ("vendor", "0019_auto_20220303_1352"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="vendor",
            name="variants",
        ),
        migrations.AddField(
            model_name="vendor",
            name="products",
            field=models.ManyToManyField(to="product.Product"),
        ),
    ]
