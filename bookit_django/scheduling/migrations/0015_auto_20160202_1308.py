# -*- coding: utf-8 -*-
# Generated by Django 1.9b1 on 2016-02-02 18:08
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0014_event_maintenance'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='expired',
            field=models.BooleanField(default=False, verbose_name='Expired'),
        ),
        migrations.AlterField(
            model_name='event',
            name='status',
            field=models.CharField(choices=[('C', 'Canceled'), ('A', 'Active')], default='A', max_length=1),
        ),
    ]
