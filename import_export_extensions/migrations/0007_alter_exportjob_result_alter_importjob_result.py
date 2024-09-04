# Generated by Django 4.2.7 on 2024-05-16 09:21

from django.db import migrations

import import_export.results
import picklefield.fields


class Migration(migrations.Migration):
    dependencies = [
        ("import_export_extensions", "0006_importjob_input_errors_file"),
    ]

    operations = [
        migrations.AlterField(
            model_name="exportjob",
            name="result",
            field=picklefield.fields.PickledObjectField(
                default=import_export.results.Result,
                editable=False,
                help_text="Internal job result object that contain info about job statistics. Pickled Python object",
                verbose_name="Job result",
            ),
        ),
        migrations.AlterField(
            model_name="importjob",
            name="result",
            field=picklefield.fields.PickledObjectField(
                default=import_export.results.Result,
                editable=False,
                help_text="Internal job result object that contain info about job statistics. Pickled Python object",
                verbose_name="Job result",
            ),
        ),
    ]
