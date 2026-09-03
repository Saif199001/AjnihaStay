from django.db import connection

WORKSPACE_SETTING = "app.workspace_id"


def set_workspace_context(workspace_id):
    """Bind the current PostgreSQL transaction to one workspace."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT set_config(%s, %s, true)",
            [WORKSPACE_SETTING, str(workspace_id)],
        )


def clear_workspace_context():
    """Reset the workspace setting for defensive use outside an atomic request."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config(%s, '', true)", [WORKSPACE_SETTING])
