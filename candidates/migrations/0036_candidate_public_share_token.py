import uuid

from django.db import migrations, models


def backfill_tokens(apps, schema_editor):
    Candidate = apps.get_model("candidates", "Candidate")
    for candidate in Candidate.objects.all().only("id").iterator():
        Candidate.objects.filter(pk=candidate.pk).update(public_share_token=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ("candidates", "0035_public_share_enabled_default_true"),
    ]

    operations = [
        # Add nullable + non-unique first so the one-off default doesn't collide
        # across existing rows, then give each row its own token, then enforce unique.
        migrations.AddField(
            model_name="candidate",
            name="public_share_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(backfill_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="candidate",
            name="public_share_token",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True),
        ),
    ]
