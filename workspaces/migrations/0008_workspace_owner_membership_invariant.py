from django.db import migrations, models
from django.db.models import Q


def validate_owner_membership_invariant(apps, schema_editor):
    Workspace = apps.get_model("workspaces", "Workspace")
    Membership = apps.get_model("workspaces", "Membership")

    invalid = []
    for workspace in Workspace.objects.order_by("pk").iterator():
        owners = Membership.objects.filter(
            workspace_id=workspace.pk,
            user_id=workspace.owner_id,
            role="owner",
            is_active=True,
        ).count()
        active_owners = Membership.objects.filter(
            workspace_id=workspace.pk,
            role="owner",
            is_active=True,
        ).count()
        if owners != 1 or active_owners != 1:
            invalid.append(workspace.pk)

    if invalid:
        raise RuntimeError(
            "Cannot enforce workspace owner invariant; invalid workspace IDs: "
            + ", ".join(str(pk) for pk in invalid)
        )


TRIGGER_FUNCTION_SQL = r"""
CREATE OR REPLACE FUNCTION workspaces_enforce_owner_membership()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    workspace_id bigint;
    owner_id bigint;
    active_owner_count integer;
    matching_owner_count integer;
BEGIN
    IF TG_TABLE_NAME = 'workspaces_workspace' THEN
        workspace_id := COALESCE(NEW.id, OLD.id);
    ELSE
        workspace_id := COALESCE(NEW.workspace_id, OLD.workspace_id);
    END IF;

    SELECT owner_id
      INTO owner_id
      FROM workspaces_workspace
     WHERE id = workspace_id;

    IF owner_id IS NULL THEN
        RAISE EXCEPTION
            'Workspace % must have an owner',
            workspace_id
            USING ERRCODE = '23514';
    END IF;

    SELECT COUNT(*)
      INTO active_owner_count
      FROM workspaces_membership
     WHERE workspace_id = workspace_id
       AND role = 'owner'
       AND is_active = TRUE;

    SELECT COUNT(*)
      INTO matching_owner_count
      FROM workspaces_membership
     WHERE workspace_id = workspace_id
       AND user_id = owner_id
       AND role = 'owner'
       AND is_active = TRUE;

    IF active_owner_count <> 1 OR matching_owner_count <> 1 THEN
        RAISE EXCEPTION
            'Workspace % must have exactly one active owner membership matching Workspace.owner',
            workspace_id
            USING ERRCODE = '23514';
    END IF;

    IF TG_TABLE_NAME = 'workspaces_membership'
       AND TG_OP = 'UPDATE'
       AND OLD.workspace_id IS DISTINCT FROM NEW.workspace_id THEN
        SELECT owner_id
          INTO owner_id
          FROM workspaces_workspace
         WHERE id = OLD.workspace_id;

        SELECT COUNT(*)
          INTO active_owner_count
          FROM workspaces_membership
         WHERE workspace_id = OLD.workspace_id
           AND role = 'owner'
           AND is_active = TRUE;

        SELECT COUNT(*)
          INTO matching_owner_count
          FROM workspaces_membership
         WHERE workspace_id = OLD.workspace_id
           AND user_id = owner_id
           AND role = 'owner'
           AND is_active = TRUE;

        IF active_owner_count <> 1 OR matching_owner_count <> 1 THEN
            RAISE EXCEPTION
                'Workspace % must have exactly one active owner membership matching Workspace.owner',
                OLD.workspace_id
                USING ERRCODE = '23514';
        END IF;
    END IF;

    RETURN NULL;
END;
$$;
"""

TRIGGER_CREATE_SQL = r"""
CREATE CONSTRAINT TRIGGER workspaces_owner_membership_workspace_check
AFTER INSERT OR UPDATE OF owner ON workspaces_workspace
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION workspaces_enforce_owner_membership();

CREATE CONSTRAINT TRIGGER workspaces_owner_membership_membership_check
AFTER INSERT OR UPDATE OF workspace_id, user_id, role, is_active OR DELETE
ON workspaces_membership
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION workspaces_enforce_owner_membership();

REVOKE ALL ON FUNCTION workspaces_enforce_owner_membership() FROM PUBLIC;
"""

TRIGGER_DROP_SQL = r"""
DROP TRIGGER IF EXISTS workspaces_owner_membership_membership_check
ON workspaces_membership;
DROP TRIGGER IF EXISTS workspaces_owner_membership_workspace_check
ON workspaces_workspace;
DROP FUNCTION IF EXISTS workspaces_enforce_owner_membership();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0007_membership_viewer_role"),
    ]

    operations = [
        migrations.RunPython(
            validate_owner_membership_invariant,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="membership",
            constraint=models.UniqueConstraint(
                fields=["workspace"],
                condition=Q(role="owner", is_active=True),
                name="unique_active_workspace_owner",
            ),
        ),
        migrations.RunSQL(
            TRIGGER_FUNCTION_SQL + TRIGGER_CREATE_SQL,
            reverse_sql=TRIGGER_DROP_SQL,
        ),
    ]
