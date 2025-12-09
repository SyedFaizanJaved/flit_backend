from django.apps import AppConfig


class StoriesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'stories'
    verbose_name = 'Stories'
    
    def ready(self):
        # Import signals here to avoid AppRegistryNotReady exception
        try:
            import stories.signals  # noqa
        except ImportError:
            pass
