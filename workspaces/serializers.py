from rest_framework import serializers

from .models import Membership, Workspace


class WorkspaceSerializer(serializers.ModelSerializer):
    role = serializers.SerializerMethodField()

    class Meta:
        model = Workspace
        fields = ["id", "name", "slug", "is_active", "role", "created_at", "updated_at"]
        read_only_fields = fields

    def get_role(self, obj):
        membership = getattr(obj, "current_membership", None)
        return membership.role if membership else None


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
            Membership.ROLE_STAFF,
        ],
        default=Membership.ROLE_STAFF,
    )


class MembershipRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[
            Membership.ROLE_ADMIN,
            Membership.ROLE_MANAGER,
            Membership.ROLE_STAFF,
        ]
    )
