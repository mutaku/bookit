# -*- coding: utf-8 -*-
# Generated by Django 1.9b1 on 2016-01-28 17:11
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0008_auto_20160126_1343'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='equipment',
            options={'verbose_name_plural': 'equipment'},
        ),
        migrations.AddField(
            model_name='event',
            name='disassemble',
            field=models.BooleanField(default=True, verbose_name='Can disassemble'),
        ),
    ]
