from rest_framework import serializers
from core.models import Tenant, User

class TenantMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ("id", "nom", "type_structure", "devise")
