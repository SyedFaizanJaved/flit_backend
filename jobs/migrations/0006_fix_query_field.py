from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('jobs', '0005_rename_query_to_search_query'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DO $$
            BEGIN
                -- Check if the column 'query' exists and 'search_query' doesn't exist
                IF EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='jobs_job' AND column_name='query')
                AND NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='jobs_job' AND column_name='search_query') THEN
                    -- Rename the column
                    ALTER TABLE jobs_job RENAME COLUMN query TO search_query;
                END IF;
            END $$;
            """,
            reverse_sql="""
            DO $$
            BEGIN
                -- Check if the column 'search_query' exists and 'query' doesn't exist
                IF EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='jobs_job' AND column_name='search_query')
                AND NOT EXISTS (SELECT 1 FROM information_schema.columns 
                              WHERE table_name='jobs_job' AND column_name='query') THEN
                    -- Rename the column back
                    ALTER TABLE jobs_job RENAME COLUMN search_query TO query;
                END IF;
            END $$;
            """
        ),
    ]
