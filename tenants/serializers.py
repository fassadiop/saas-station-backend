from rest_framework import serializers
from tenants.models import Tenant


class TenantSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField()

    class Meta:
        model = Tenant
        fields = [
            "id",
            "nom",
            "type_structure",
            "date_creation",
            "devise",
            "actif",
            "created_by",
        ]

    def get_created_by(self, obj):
        if obj.created_by:
            return {
                "id": obj.created_by.id,
                "username": obj.created_by.username,
                "email": obj.created_by.email,
            }
        return None

    def create(self, validated_data):
        request = self.context["request"]

        return Tenant.objects.create(
            **validated_data,
            created_by=request.user,
        )