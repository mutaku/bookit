# -*- coding: utf-8 -*-
# Generated by Django 1.9b1 on 2016-02-16 15:18
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('scheduling', '0016_auto_20160216_1011'),
    ]

    operations = [
        migrations.RenameField(
            model_name='equipment',
            old_name='components',
            new_name='component',
        ),
    ]