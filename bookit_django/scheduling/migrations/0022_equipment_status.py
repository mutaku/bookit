# -*- coding: utf-8 -*-
# Generated by Django 1.9b1 on 2016-02-23 15:35
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0021_message_critical'),
    ]

    operations = [
        migrations.AddField(
            model_name='equipment',
            name='status',
            field=models.BooleanField(default=True, verbose_name='Running'),
        ),
    ]
