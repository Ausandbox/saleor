# -*- coding: utf-8 -*-
# Generated by Django 1.10.3 on 2016-11-30 12:26
from __future__ import unicode_literals

from django.db import migrations

from saleor.core.hstore import h_store_field


class Migration(migrations.Migration):

    dependencies = [("product", "0014_remove_productvariant_attributes")]

    operations = [
        migrations.AddField(
            model_name="productvariant",
            name="attributes",
            field=h_store_field(default="", verbose_name="attributes"),
        )
    ]
