from django.apps import AppConfig


class AlertasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "alertas"
    verbose_name = "Alertas y Notificaciones"

    def ready(self):
        from .signals import conectar_senales
        conectar_senales()
