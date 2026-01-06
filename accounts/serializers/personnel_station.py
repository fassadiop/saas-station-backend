# accounts/serializers/personnel_station.py
from rest_framework import serializers
from django.contrib.auth.hashers import make_password

from accounts.models import Utilisateur
from accounts.constants import UserRole, StationRoles


class PersonnelStationSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Utilisateur
        fields = (
            "id",
            "username",
            "first_name",
            "last_name",
            "email",
            "role",
            "is_active",
            "password",
        )
        read_only_fields = ("id",)

    def validate_role(self, value):
        if value not in StationRoles.ALLOWED:
            raise serializers.ValidationError(
                "Rôle non autorisé pour le personnel de station."
            )
        return value

    def validate(self, data):
        role = data.get("role")

        if role in StationRoles.ALLOWED:
            data["module"] = "station"

        return data

    def create(self, validated_data):
        request = self.context["request"]

        validated_data["tenant"] = request.user.tenant
        validated_data["station"] = request.user.station
        validated_data["module"] = "station"

        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError(
                {"password": "Mot de passe obligatoire."}
            )

        user = Utilisateur(**validated_data)
        user.password = make_password(password)
        user.save()

        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        if password:
            instance.password = make_password(password)

        instance.save()
        return instance
