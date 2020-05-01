# Generated by Django 2.0.3 on 2018-03-30 08:21

from django.db import migrations

from saleor.core.hstore import h_store_field


class Migration(migrations.Migration):

    dependencies = [("product", "0055_auto_20180321_0417")]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="attributes",
            field=h_store_field(blank=True, default={}),
        ),
        migrations.AlterField(
            model_name="productvariant",
            name="attributes",
            field=h_store_field(blank=True, default={}),
        ),
    ]
