from django.db import migrations


TRIGGER_FUNCTION = "payments_financialledgerentry_append_only"
TRIGGER_NAME = "payments_financialledgerentry_append_only_trigger"
TABLE_NAME = "payments_financialledgerentry"


FORWARD_SQL = f"""
CREATE OR REPLACE FUNCTION {TRIGGER_FUNCTION}()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'Financial ledger entries are append-only; % is not permitted', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS {TRIGGER_NAME} ON {TABLE_NAME};
CREATE TRIGGER {TRIGGER_NAME}
BEFORE UPDATE OR DELETE ON {TABLE_NAME}
FOR EACH ROW
EXECUTE FUNCTION {TRIGGER_FUNCTION}();
"""

REVERSE_SQL = f"""
DROP TRIGGER IF EXISTS {TRIGGER_NAME} ON {TABLE_NAME};
DROP FUNCTION IF EXISTS {TRIGGER_FUNCTION}();
"""


def apply_append_only(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(FORWARD_SQL)


def reverse_append_only(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(REVERSE_SQL)


class Migration(migrations.Migration):
    dependencies = [("payments", "0018_financial_ledger_entry")]

    operations = [
        migrations.RunPython(apply_append_only, reverse_append_only),
    ]
