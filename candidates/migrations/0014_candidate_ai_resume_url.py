# Generated manually for ai_resume_url field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('candidates', '0013_alter_candidate_resume_data'),
    ]

    operations = [
        migrations.AddField(
            model_name='candidate',
            name='ai_resume_url',
            field=models.FileField(blank=True, null=True, upload_to='resumes/', verbose_name='AI Generated Resume'),
        ),
    ]
