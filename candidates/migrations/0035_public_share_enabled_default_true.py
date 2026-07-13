from django.db import migrations, models


def enable_public_share_for_existing(apps, schema_editor):
    """Flip every existing candidate to public so shared links work immediately."""
    Candidate = apps.get_model("candidates", "Candidate")
    Candidate.objects.update(public_share_enabled=True)


class Migration(migrations.Migration):

    dependencies = [
        ("candidates", "0034_candidate_public_share_enabled"),
    ]

    operations = [
        migrations.AlterField(
            model_name="candidate",
            name="public_share_enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.RunPython(
            enable_public_share_for_existing,
            migrations.RunPython.noop,
        ),
    ]
