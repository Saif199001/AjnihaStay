from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payments"

    def ready(self):
        import payments.billing_models  # noqa: F401
        import payments.signals  # noqa: F401
