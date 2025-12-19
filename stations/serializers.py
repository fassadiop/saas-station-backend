from rest_framework import serializers
from .models import FaitStatus, Station, VenteCarburant, Local, ContratLocation


class StationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Station
        fields = "__all__"
        read_only_fields = ("tenant", "created_at")


class VenteCarburantSerializer(serializers.ModelSerializer):
    class Meta:
        model = VenteCarburant
        fields = "__all__"
        read_only_fields = (
            "tenant",
            "created_by",
            "status",
            "soumis_par",
            "soumis_le",
            "valide_par",
            "valide_le",
        )

    def update(self, instance, validated_data):
        if instance.status != FaitStatus.BROUILLON:
            raise serializers.ValidationError(
                "Ce fait ne peut plus être modifié."
            )
        return super().update(instance, validated_data)



class LocalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Local
        fields = "__all__"
        read_only_fields = ("tenant",)


class ContratLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContratLocation
        fields = "__all__"
        read_only_fields = ("tenant",)
