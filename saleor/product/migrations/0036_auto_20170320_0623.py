# -*- coding: utf-8 -*-
# Generated by Django 1.10.6 on 2017-03-20 11:23
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0035_auto_20170320_0618'),
    ]

    operations = [
        migrations.RenameField(
            model_name='attributechoicevaluetranslation',
            old_name='display',
            new_name='name',
        ),
    ]
