from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('candidates', '0004_candidate_resume_data'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                -- Ensure the column exists with the correct type
                IF NOT EXISTS (
                    SELECT 1 
                    FROM information_schema.columns 
                    WHERE table_name='candidates' AND column_name='resume_data'
                ) THEN
                    ALTER TABLE candidates ADD COLUMN resume_data jsonb;
                END IF;
                
                -- Make sure the column is nullable
                ALTER TABLE candidates ALTER COLUMN resume_data DROP NOT NULL;
                
                -- Add a comment for documentation
                COMMENT ON COLUMN candidates.resume_data IS 'Stores parsed CV/Resume data';
            END $$;
            """,
            reverse_sql="""
            -- No need to reverse this as it's just ensuring the column exists
            """
        ),
    ]
