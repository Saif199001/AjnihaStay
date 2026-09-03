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
