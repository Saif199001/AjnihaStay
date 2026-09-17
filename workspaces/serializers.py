from rest_framework import serializers

from .models import Membership, Workspace


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ["id", "name", "slug", "is_active", "role", "created_at", "updated_at"]
        read_only_fields = ["id", "slug", "is_active", "role", "created_at", "updated_at"]

    def get_role(self, obj):
        membership = getattr(obj, "current_membership", None)
        return membership.role if membership else None


class WorkspaceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ["name"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Workspace name is required")
        return value


class WorkspaceTransferOwnershipSerializer(serializers.Serializer):
    target_user_id = serializers.IntegerField(min_value=1)


class MembershipSerializer(serializers.ModelSerializer):
    user_id = serializers.IntegerField(source="user.id", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "user_id", "email", "role", "is_active", "created_at", "updated_at"]
        read_only_fields = ["id", "user_id", "email", "is_active", "created_at", "updated_at"]


class MembershipCreateSerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(
        choices=[
            Membership.ROLE_ADMIN,
            Membership.ROLE_MANAGER,
            Membership.ROLE_VIEWER,
        ],
        default=Membership.ROLE_VIEWER,
    )


class MembershipRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[
            Membership.ROLE_ADMIN,
            Membership.ROLE_MANAGER,
            Membership.ROLE_VIEWER,
        ]
    )
