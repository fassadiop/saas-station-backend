# saas-backend/stations/views_depotage/depotage.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError

from django.db import transaction
from django.utils import timezone

from dashboard.permissions import IsAdminTenantStation
from stations.models_depotage import Depotage, Cuve, MouvementStock
from stations.serializers_depotage.depotage import DepotageSerializer
from stations.constants import DepotageStatus
from stations.permissions import IsGerantOrSuperviseur, IsStationAdminOrActor

from finances_station.models import TransactionStation
from accounts.constants import UserRole


class DepotageViewSet(viewsets.ModelViewSet):
    """
    API Dépotage carburant (station)

    Workflow :
    BROUILLON → SOUMIS → CONFIRME → TRANSFERE
    """

    serializer_class = DepotageSerializer
    permission_classes = [IsGerantOrSuperviseur]

    # ==========================================================
    # QUERYSET
    # ==========================================================

    def get_queryset(self):
        user = self.request.user

        qs = Depotage.objects.select_related(
            "station",
            "cuve",
            "tenant",
        ).filter(tenant=user.tenant)

        if user.role == UserRole.ADMIN_TENANT_STATION:
            station_id = self.request.query_params.get("station_id")
            if station_id:
                qs = qs.filter(station_id=station_id)
            return qs

        return qs.filter(station=user.station)

    # ==========================================================
    # CREATE
    # ==========================================================
    def get_permissions(self):

        # 🔹 Lecture → gérant & superviseur
        if self.action in ["list", "retrieve"]:
            return [IsGerantOrSuperviseur()]

        # 🔹 Création → gérant & superviseur
        if self.action == "create":
            return [IsGerantOrSuperviseur()]

        # 🔹 Transitions métier
        if self.action in ["soumettre", "confirmer", "transferer"]:
            return [IsGerantOrSuperviseur()]

        # 🔹 Sécurité par défaut
        return [IsAdminTenantStation()]

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            tenant=self.request.user.tenant,
            station=self.request.user.station,
        )

    # ==========================================================
    # TRANSITIONS
    # ==========================================================

    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):
        depotage = self.get_object()

        if depotage.statut != DepotageStatus.BROUILLON:
            raise ValidationError(
                "Seul un dépotage brouillon peut être soumis."
            )

        depotage.statut = DepotageStatus.SOUMIS
        depotage.save(update_fields=["statut", "updated_at"])

        return Response({"status": "soumis"})

    # ----------------------------------------------------------

    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        depotage = self.get_object()

        if depotage.statut != DepotageStatus.SOUMIS:
            raise ValidationError("Dépotage non soumis.")

        depotage.statut = DepotageStatus.CONFIRME
        depotage.validated_by = request.user
        depotage.validated_at = timezone.now()
        depotage.save(
            update_fields=[
                "statut",
                "validated_by",
                "validated_by",
                "updated_at",
            ]
        )

        return Response({"status": "confirme"})

    # ----------------------------------------------------------

    @action(detail=True, methods=["post"])
    def transferer(self, request, pk=None):
        depotage = self.get_object()

        if depotage.statut != DepotageStatus.CONFIRME:
            raise ValidationError("Dépotage non confirmé.")

        if depotage.stock_applique:
            raise ValidationError("Stock déjà appliqué.")

        if not depotage.cuve:
            raise ValidationError(
                "Aucune cuve associée à ce dépotage."
            )

        with transaction.atomic():

            # 🔐 Lock cuve (anti double écriture concurrente)
            cuve = Cuve.objects.select_for_update().get(
                pk=depotage.cuve.pk,
                tenant=request.user.tenant,
            )

            # ======================================================
            # 1️⃣ MOUVEMENT STOCK (ENTRÉE)
            # ======================================================
            MouvementStock.objects.create(
                tenant=cuve.station.tenant,
                station=cuve.station,
                cuve=cuve,
                type_mouvement=MouvementStock.MOUVEMENT_ENTREE,
                quantite=depotage.quantite_acceptee,
                source_type="DEPOTAGE",
                source_id=depotage.id,
                date_mouvement=timezone.now(),
            )

            # ======================================================
            # 2️⃣ MAJ STOCK CUVE
            # ======================================================
            cuve.stock_actuel += depotage.quantite_acceptee
            cuve.save(update_fields=["stock_actuel"])

            # ======================================================
            # 3️⃣ DÉPENSE FINANCIÈRE
            # ======================================================
            TransactionStation.objects.create(
                tenant=cuve.station.tenant,
                station=cuve.station,
                date=timezone.now(),
                type="DEPENSE",
                montant=depotage.montant_total,
                source_type="DEPOTAGE",
                source_id=depotage.id,
                finance_status="CONFIRMEE",
            )

            # ======================================================
            # 4️⃣ FINALISATION
            # ======================================================
            depotage.stock_applique = True
            depotage.statut = DepotageStatus.TRANSFERE
            depotage.save(
                update_fields=["stock_applique", "statut", "updated_at"]
            )

        return Response(
            {
                "status": "transfere",
                "cuve": cuve.id,
                "stock_actuel": str(cuve.stock_actuel),
            },
            status=status.HTTP_200_OK,
        )
