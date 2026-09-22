# stations/views_lubrifiant_vente.py

from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from stations.models_lubrifiant import VenteLubrifiant
from stations.serializers_lubrifiant_vente import (
    VenteLubrifiantSerializer,
)
from stations.services.vente_lubrifiant import vendre_lubrifiant


class VenteLubrifiantViewSet(viewsets.ModelViewSet):
    """
    API de gestion des ventes de lubrifiants.

    La création d'une vente passe obligatoirement par
    le service métier vendre_lubrifiant().
    """

    serializer_class = VenteLubrifiantSerializer
    permission_classes = [IsAuthenticated]

    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, "tenant", None)

        if tenant is None:
            return VenteLubrifiant.objects.none()

        queryset = (
            VenteLubrifiant.objects
            .filter(tenant=tenant)
            .select_related(
                "station",
                "relais",
                "lubrifiant",
                "created_by",
            )
        )

        # ----------------------------------------------
        # Filtre station
        # ----------------------------------------------

        station_id = self.request.query_params.get(
            "station"
        )

        if station_id:
            queryset = queryset.filter(
                station_id=station_id
            )

        # ----------------------------------------------
        # Filtre relais
        # ----------------------------------------------

        relais_id = self.request.query_params.get(
            "relais"
        )

        if relais_id:
            queryset = queryset.filter(
                relais_id=relais_id
            )

        # ----------------------------------------------
        # Filtre lubrifiant
        # ----------------------------------------------

        lubrifiant_id = self.request.query_params.get(
            "lubrifiant"
        )

        if lubrifiant_id:
            queryset = queryset.filter(
                lubrifiant_id=lubrifiant_id
            )

        return queryset.order_by(
            "-date_vente",
            "-id",
        )

    def _can_manage_ventes(self):
        """
        Vérifie si l'utilisateur peut enregistrer une vente.
        """

        role = getattr(
            self.request.user,
            "role",
            None,
        )

        return role in [
            "ADMIN_TENANT_STATION",
            "GERANT",
            "SUPERVISEUR",
            "POMPISTE",
        ]

    def create(self, request, *args, **kwargs):

        if not self._can_manage_ventes():
            return Response(
                {
                    "detail": (
                        "Vous n'avez pas les droits "
                        "pour enregistrer une vente."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)

        tenant = request.user.tenant

        vente = vendre_lubrifiant(
            tenant=tenant,
            station=serializer.validated_data["station"],
            lubrifiant=serializer.validated_data[
                "lubrifiant"
            ],
            quantite=serializer.validated_data[
                "quantite"
            ],
            relais=serializer.validated_data.get(
                "relais"
            ),
            created_by=request.user,
            date_vente=serializer.validated_data.get(
                "date_vente"
            ),
        )

        output_serializer = self.get_serializer(
            vente
        )

        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED,
        )