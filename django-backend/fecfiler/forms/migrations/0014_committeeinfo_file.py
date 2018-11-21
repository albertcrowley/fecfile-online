# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2018-10-19 14:38
from __future__ import unicode_literals

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forms', '0013_committee_email_on_file'),
    ]

    operations = [
        migrations.AddField(
            model_name='committeeinfo',
            name='file',
            field=models.FileField(null=True, upload_to='f99/', validators=[django.core.validators.FileExtensionValidator(allowed_extensions=['pdf'])]),
        ),
    ]