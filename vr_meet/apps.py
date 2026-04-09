from django.apps import AppConfig


class VrMeetConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'vr_meet'

    def ready(self):
        import vr_meet.signals
