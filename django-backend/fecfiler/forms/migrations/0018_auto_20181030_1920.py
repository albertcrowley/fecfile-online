# -*- coding: utf-8 -*-
# Generated by Django 1.11 on 2018-10-30 19:20
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('forms', '0017_auto_20181030_1847'),
    ]

    operations = [
        migrations.CreateModel(
            name='F99Attachment',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('bytes', models.TextField()),
                ('filename', models.CharField(max_length=255)),
                ('mimetype', models.CharField(max_length=50)),
            ],
        ),
        migrations.AlterField(
            model_name='committeeinfo',
            name='file',
            field=models.FileField(null=True, upload_to='forms.F99Attachment/bytes/filename/mimetype'),
        ),
    ]