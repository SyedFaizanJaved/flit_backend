from django.db import migrations, models


def mark_query_field_as_added(apps, schema_editor):
    """This is a no-op function since the column already exists"""
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('candidates', '0006_rename_query_candidate_search_query'),
    ]

    operations = [
        # This will add the field to Django's state without trying to create the column
        migrations.AddField(
            model_name='candidate',
            name='query',
            field=models.TextField(blank=True, null=True),
            preserve_default=False,
        ),
        # This will run our no-op function instead of trying to create the column
        migrations.RunPython(
            mark_query_field_as_added,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
