# stations/views_baie.py

from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from stations.services.operation_baie import (
    enregistrer_operation_baie,
)

from stations.models_baie import (
    OperationBaie,
    PrestationBaie,
)

from stations.serializers_baie import (
    OperationBaieSerializer,
    PrestationBaieSerializer,
)

from stations.services.operation_baie import (
    enregistrer_operation_baie,
)


class OperationBaieViewSet(viewsets.ModelViewSet):
    """
    API de gestion des opérations de baie.

    Une opération de baie peut être :
        - autonome : sans relais ;
        - intégrée à un relais.

    La création passe obligatoirement par le service métier
    enregistrer_operation_baie().
    """

    serializer_class = OperationBaieSerializer
    permission_classes = [IsAuthenticated]

    http_method_names = [
        "get",
        "post",
        "head",
        "options",
    ]

    # ==================================================
    # QUERYSET
    # ==================================================

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, "tenant", None)

        if tenant is None:
            return OperationBaie.objects.none()

        queryset = (
            OperationBaie.objects
            .filter(tenant=tenant)
            .select_related(
                "station",
                "relais",
                "prestation",
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
        # Filtre prestation
        # ----------------------------------------------

        prestation_id = self.request.query_params.get(
            "prestation"
        )

        if prestation_id:
            queryset = queryset.filter(
                prestation_id=prestation_id
            )

        # ----------------------------------------------
        # Opérations autonomes
        # ----------------------------------------------

        autonome = self.request.query_params.get(
            "autonome"
        )

        if autonome == "true":
            queryset = queryset.filter(
                relais__isnull=True
            )

        elif autonome == "false":
            queryset = queryset.filter(
                relais__isnull=False
            )

        return queryset.order_by(
            "-id"
        )

    # ==================================================
    # PERMISSIONS MÉTIER
    # ==================================================

    def _can_manage_operations(self):
        """
        Vérifie si l'utilisateur peut enregistrer
        une opération de baie.
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

    # ==================================================
    # CRÉATION
    # ==================================================

    def create(self, request, *args, **kwargs):

        if not self._can_manage_operations():
            return Response(
                {
                    "detail": (
                        "Vous n'avez pas les droits "
                        "pour enregistrer une opération "
                        "de baie."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        tenant = request.user.tenant

        operation = enregistrer_operation_baie(
            tenant=tenant,
            station=serializer.validated_data[
                "station"
            ],
            prestation=serializer.validated_data[
                "prestation"
            ],
            quantite=serializer.validated_data[
                "quantite"
            ],
            relais=serializer.validated_data.get(
                "relais"
            ),
            created_by=request.user,
        )

        output_serializer = self.get_serializer(
            operation
        )

        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED,
        )


class PrestationBaieViewSet(viewsets.ModelViewSet):

    serializer_class = PrestationBaieSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        tenant = getattr(user, "tenant", None)

        if tenant is None:
            return PrestationBaie.objects.none()

        queryset = (
            PrestationBaie.objects
            .filter(tenant=tenant)
            .select_related("station")
        )

        station_id = self.request.query_params.get("station")

        if station_id:
            queryset = queryset.filter(
                station_id=station_id
            )

        actif = self.request.query_params.get("actif")

        if actif == "true":
            queryset = queryset.filter(actif=True)

        elif actif == "false":
            queryset = queryset.filter(actif=False)

        return queryset.order_by("station__nom", "code")

    def _can_manage_prestations(self):

        role = getattr(
            self.request.user,
            "role",
            None,
        )

        return role in [
            "ADMIN_TENANT_STATION",
            "GERANT",
            "SUPERVISEUR",
        ]

    def create(self, request, *args, **kwargs):

        if not self._can_manage_prestations():

            return Response(
                {
                    "detail": (
                        "Vous n'avez pas les droits "
                        "pour créer une prestation de baie."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = self.get_serializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        prestation = serializer.save(
            tenant=request.user.tenant
        )

        output_serializer = self.get_serializer(
            prestation
        )

        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):

        if not self._can_manage_prestations():

            return Response(
                {
                    "detail": (
                        "Vous n'avez pas les droits "
                        "pour modifier une prestation de baie."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().update(
            request,
            *args,
            **kwargs
        )

    def partial_update(
        self,
        request,
        *args,
        **kwargs
    ):

        if not self._can_manage_prestations():

            return Response(
                {
                    "detail": (
                        "Vous n'avez pas les droits "
                        "pour modifier une prestation de baie."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().partial_update(
            request,
            *args,
            **kwargs
        )

    def destroy(self, request, *args, **kwargs):

        if not self._can_manage_prestations():

            return Response(
                {
                    "detail": (
                        "Vous n'avez pas les droits "
                        "pour supprimer une prestation de baie."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        return super().destroy(
            request,
            *args,
            **kwargs
        )