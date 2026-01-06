# accounts/views/personnel_station.py
from rest_framework import viewsets, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from accounts.models import Utilisateur
from .permissions import IsGerantOrAdminTenantStation
from accounts.serializers.personnel_station import PersonnelStationSerializer

from accounts.constants import StationRoles, UserRole
from accounts.permissions import (
    CanCreateStationPersonnel,
    IsGerantOrAdminTenantStation,
)


class PersonnelStationViewSet(viewsets.ModelViewSet):
    serializer_class = PersonnelStationSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch"]

    def get_queryset(self):
        user = self.request.user

        return Utilisateur.objects.filter(
            tenant=user.tenant,
            station=user.station,
            module="station",
            role__in=StationRoles.ALLOWED,
        ).order_by("last_name", "first_name")

    def get_permissions(self):
        if self.action == "create":
            return [IsAuthenticated(), CanCreateStationPersonnel()]

        if self.action in ["partial_update", "update"]:
            return [IsAuthenticated(), IsGerantOrAdminTenantStation()]

        return [IsAuthenticated()]

    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Suppression interdite. Utilisez la désactivation."},
            status=status.HTTP_403_FORBIDDEN,
        )

    def perform_create(self, serializer):
        creator = self.request.user

        # 🔒 Sécurité absolue : seul un utilisateur AVEC station peut créer du staff
        if creator.role == UserRole.GERANT and not creator.station:
            raise ValidationError(
                "Le gérant doit être rattaché à une station."
            )

        if not creator.station:
            raise ValidationError(
                "Impossible de créer du personnel sans station associée."
            )

        role = serializer.validated_data.get("role")

        # 🔒 Un seul Chef de station actif
        if role == UserRole.GERANT:
            if Utilisateur.objects.filter(
                station=creator.station,
                role=UserRole.GERANT,
                is_active=True
            ).exists():
                raise ValidationError({
                    "role": (
                        "Un chef de station actif existe déjà. "
                        "Veuillez le désactiver avant d’en créer un autre."
                    )
                })

        # 🔒 Un seul Chef de piste actif
        if role == UserRole.SUPERVISEUR:
            if Utilisateur.objects.filter(
                station=creator.station,
                role=UserRole.SUPERVISEUR,
                is_active=True
            ).exists():
                raise ValidationError({
                    "role": (
                        "Un chef de piste actif existe déjà. "
                        "Veuillez le désactiver avant d’en créer un autre."
                    )
                })

        # ✅ CRÉATION GARANTIE AVEC STATION
        serializer.save(
            tenant=creator.tenant,
            station=creator.station if creator.role == UserRole.GERANT else None,
            is_active=True,
        )

    def perform_update(self, serializer):
        instance = self.get_object()
        role = instance.role
        station = instance.station
        is_active = serializer.validated_data.get("is_active", instance.is_active)

        # 🔁 Réactivation Chef de station
        if role == "Chef de station" and is_active:
            exists = Utilisateur.objects.filter(
                station=station,
                role="Chef de station",
                is_active=True
            ).exclude(id=instance.id).exists()

            if exists:
                raise ValidationError({
                    "is_active": (
                        "Un autre chef de station est déjà actif pour cette station."
                    )
                })

        # 🔁 Réactivation Chef de piste
        if role == "Chef de piste" and is_active:
            exists = Utilisateur.objects.filter(
                station=station,
                role="Chef de piste",
                is_active=True
            ).exclude(id=instance.id).exists()

            if exists:
                raise ValidationError({
                    "is_active": (
                        "Un autre chef de piste est déjà actif pour cette station."
                    )
                })

        serializer.save()
