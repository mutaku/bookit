# -*- coding: utf-8 -*-
# Generated by Django 1.9b1 on 2016-01-21 16:30
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0003_event_elapsed_hours'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='elapsed_hours',
            field=models.FloatField(blank=True, null=True, verbose_name='Elapsed time (h)'),
        ),
    ]