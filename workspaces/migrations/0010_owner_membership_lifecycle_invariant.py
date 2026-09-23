from django.db import migrations


TRIGGER_FUNCTION_SQL = r"""
CREATE OR REPLACE FUNCTION workspaces_assert_owner_membership(p_workspace_id bigint)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
    v_owner_id bigint;
    active_owner_count integer;
    matching_owner_count integer;
BEGIN
    SELECT owner_id INTO v_owner_id
    FROM workspaces_workspace
    WHERE id = p_workspace_id;

    IF NOT FOUND THEN
        RETURN;
    END IF;

    IF v_owner_id IS NULL THEN
        RAISE EXCEPTION 'Workspace % must have an owner', p_workspace_id
            USING ERRCODE = '23514';
    END IF;

    SELECT COUNT(*) INTO active_owner_count
    FROM workspaces_membership
    WHERE workspace_id = p_workspace_id
      AND role = 'owner'
      AND is_active = TRUE;

    SELECT COUNT(*) INTO matching_owner_count
    FROM workspaces_membership
    WHERE workspace_id = p_workspace_id
      AND user_id = v_owner_id
      AND role = 'owner'
      AND is_active = TRUE;

    IF active_owner_count <> 1 OR matching_owner_count <> 1 THEN
        RAISE EXCEPTION
            'Workspace % must have exactly one active owner membership matching Workspace.owner',
            p_workspace_id
            USING ERRCODE = '23514';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION workspaces_enforce_workspace_owner_membership()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    PERFORM workspaces_assert_owner_membership(NEW.id);
    RETURN NULL;
END;
$$;

CREATE OR REPLACE FUNCTION workspaces_enforce_membership_owner_membership()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        PERFORM workspaces_assert_owner_membership(OLD.workspace_id);
    ELSE
        PERFORM workspaces_assert_owner_membership(NEW.workspace_id);
    END IF;

    IF TG_OP = 'UPDATE'
       AND OLD.workspace_id IS DISTINCT FROM NEW.workspace_id THEN
        PERFORM workspaces_assert_owner_membership(OLD.workspace_id);
    END IF;

    RETURN NULL;
END;
$$;

DROP TRIGGER IF EXISTS workspaces_owner_membership_workspace_check ON workspaces_workspace;
DROP TRIGGER IF EXISTS workspaces_owner_membership_membership_check ON workspaces_membership;

-- Workspace creation is deliberately not validated here. Existing application
-- flows create Workspace and its initial Membership as two writes inside one
-- atomic service transaction. Validating the workspace INSERT itself would
-- reject the legitimate intermediate state before the membership exists.
-- The deferred membership trigger validates the completed aggregate after the
-- owner membership write, while owner changes are also validated at commit.
CREATE CONSTRAINT TRIGGER workspaces_owner_membership_workspace_check
AFTER UPDATE OF owner_id ON workspaces_workspace
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workspaces_enforce_workspace_owner_membership();

CREATE CONSTRAINT TRIGGER workspaces_owner_membership_membership_check
AFTER INSERT OR UPDATE OF workspace_id, user_id, role, is_active OR DELETE
ON workspaces_membership
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION workspaces_enforce_membership_owner_membership();

REVOKE ALL ON FUNCTION workspaces_assert_owner_membership(bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION workspaces_enforce_workspace_owner_membership() FROM PUBLIC;
REVOKE ALL ON FUNCTION workspaces_enforce_membership_owner_membership() FROM PUBLIC;
"""

TRIGGER_DROP_SQL = r"""
DROP TRIGGER IF EXISTS workspaces_owner_membership_membership_check ON workspaces_membership;
DROP TRIGGER IF EXISTS workspaces_owner_membership_workspace_check ON workspaces_workspace;
DROP FUNCTION IF EXISTS workspaces_enforce_membership_owner_membership();
DROP FUNCTION IF EXISTS workspaces_enforce_workspace_owner_membership();
DROP FUNCTION IF EXISTS workspaces_assert_owner_membership(bigint);
"""


class Migration(migrations.Migration):
    dependencies = [("workspaces", "0009_harden_owner_membership_trigger")]

    operations = [
        migrations.RunSQL(TRIGGER_FUNCTION_SQL, reverse_sql=TRIGGER_DROP_SQL),
    ]
