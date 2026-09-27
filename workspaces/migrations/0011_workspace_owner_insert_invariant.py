from django.db import migrations


TRIGGER_SQL = r"""
DROP TRIGGER IF EXISTS workspaces_owner_membership_workspace_check ON workspaces_workspace;

CREATE CONSTRAINT TRIGGER workspaces_owner_membership_workspace_check
AFTER INSERT OR UPDATE OF owner_id ON workspaces_workspace
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workspaces_enforce_workspace_owner_membership();
"""


REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS workspaces_owner_membership_workspace_check ON workspaces_workspace;

CREATE CONSTRAINT TRIGGER workspaces_owner_membership_workspace_check
AFTER UPDATE OF owner_id ON workspaces_workspace
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workspaces_enforce_workspace_owner_membership();
"""


class Migration(migrations.Migration):
    dependencies = [("workspaces", "0010_owner_membership_lifecycle_invariant")]

    operations = [
        migrations.RunSQL(TRIGGER_SQL, reverse_sql=REVERSE_SQL),
    ]
