from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add `request_deleted_at` to ReferenceRequest so a candidate can remove
    a row from their Requests tab without destroying the reference-giver's
    submitted response. Existing rows correctly default to NULL (= not
    detached), so no data backfill is required.
    """

    dependencies = [
        ('candidates', '0031_alter_candidate_banner_seen'),
    ]

    operations = [
        migrations.AddField(
            model_name='referencerequest',
            name='request_deleted_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
    ]
