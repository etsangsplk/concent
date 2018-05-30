# -*- coding: utf-8 -*-
# Generated by Django 1.11.9 on 2018-05-18 09:02
from __future__ import unicode_literals

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0017_update_subtask_with_null_report_computed_task'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subtask',
            name='report_computed_task',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subtasks_for_report_computed_task', to='core.StoredMessage'),
        ),
        migrations.AlterField(
            model_name='subtask',
            name='task_to_compute',
            field=models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='subtasks_for_task_to_compute', to='core.StoredMessage'),
        ),
    ]