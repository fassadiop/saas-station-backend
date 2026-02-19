from rest_framework import serializers
from django.contrib.auth.hashers import make_password

from accounts.models import Utilisateur
from accounts.constants import UserRole
from tenants.models import Tenant


class AdminTenantStationCreateSerializer(serializers.ModelSerializer):
    tenant = serializers.SerializerMethodField(read_only=True)
    tenant_id = serializers.UUIDField(write_only=True)
    password = serializers.CharField(write_only=True)

    class Meta:
        model = Utilisateur
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "password",
            "tenant_id",
            "tenant",
            "is_active",
        )
        read_only_fields = ("id", "tenant", "is_active")

    def get_tenant(self, obj):
        if obj.tenant:
            return {
                "id": obj.tenant.id,
                "nom": obj.tenant.nom,
            }
        return None

    def create(self, validated_data):
        tenant_id = validated_data.pop("tenant_id")
        password = validated_data.pop("password")

        user = Utilisateur(
            **validated_data,
            role=UserRole.ADMIN_TENANT_STATION,
            tenant_id=tenant_id,
            station=None,
            is_active=True,
        )

        user.password = make_password(password)
        user.save()

        return user
