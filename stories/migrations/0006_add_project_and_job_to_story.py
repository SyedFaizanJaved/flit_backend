from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('stories', '0005_alter_story_user_type'),  # Use the latest migration
        ('projects', '0001_initial'),  # Make sure this is the first migration of projects app
        ('jobs', '0001_initial'),      # Make sure this is the first migration of jobs app
    ]

    operations = [
        migrations.AddField(
            model_name='story',
            name='project',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stories',
                to='projects.project'
            ),
        ),
        migrations.AddField(
            model_name='story',
            name='job',
            field=models.ForeignKey(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='stories',
                to='jobs.job'
            ),
        ),
    ]
