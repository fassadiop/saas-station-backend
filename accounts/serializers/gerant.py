from rest_framework import serializers
from django.contrib.auth.hashers import make_password

from accounts.models import Utilisateur
from accounts.constants import UserRole
from stations.models import Station


class GerantSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    station_id = serializers.PrimaryKeyRelatedField(
        queryset=Station.objects.all(),
        source="station",
        write_only=True
    )

    class Meta:
        model = Utilisateur
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "password",
            "station_id",
            "is_active",
        )
        read_only_fields = ("id",)

    def create(self, validated_data):
        request = self.context["request"]

        station = validated_data.pop("station")
        password = validated_data.pop("password")

        user = Utilisateur(
            **validated_data,
            role=UserRole.GERANT,
            tenant=request.user.tenant,
            station=station,
            module="station",
            is_active=True,
        )

        user.password = make_password(password)
        user.save()

        return user

    def validate(self, data):
        station = data.get("station")

        if Utilisateur.objects.filter(
            station=station,
            role=UserRole.GERANT,
            is_active=True
        ).exists():
            raise serializers.ValidationError(
                "Cette station a déjà un gérant actif."
            )

        return data
