# -*- coding: utf-8 -*-
# Generated by Django 1.9b1 on 2016-02-22 22:33
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0020_auto_20160222_1145'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='critical',
            field=models.BooleanField(default=False, verbose_name='Critical'),
        ),
    ]