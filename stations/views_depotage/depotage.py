# saas-backend/stations/views_depotage/depotage.py

from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response

from stations.models_depotage import Depotage, Cuve, MouvementStock, depotage
from stations.serializers_depotage.depotage import DepotageSerializer
from finances_station.models import TransactionStation
from stations.constants import DepotageStatus
from stations.permissions import IsStationAdminOrActor
from accounts.constants import UserRole

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from stations.services.stock import appliquer_stock_depotage


class DepotageViewSet(viewsets.ModelViewSet):
    """
    API Dépotage carburant (station)

    - BROUILLON : création / modification
    - SOUMIS : en attente validation
    - CONFIRME : verrouillé
    """

    serializer_class = DepotageSerializer
    permission_classes = [IsStationAdminOrActor]

    def get_queryset(self):
        user = self.request.user
        qs = Depotage.objects.filter(station__tenant=user.tenant)

        if user.role == UserRole.ADMIN_TENANT_STATION:
            station_id = self.request.query_params.get("station_id")
            if station_id:
                qs = qs.filter(station_id=station_id)
            return qs

        return qs.filter(station=user.station)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
    
    @transaction.atomic
    def perform_update(self, serializer):
        depotage = serializer.save()

        if depotage.statut == "CONFIRME" and depotage.cuve:
            cuve = depotage.cuve
            cuve.stock_actuel += depotage.quantite_livree
            cuve.save(update_fields=["stock_actuel"])

    # =========================
    # TRANSITIONS DE STATUT
    # =========================

    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):
        depotage = self.get_object()

        if depotage.statut != DepotageStatus.BROUILLON:
            return Response(
                {"detail": "Seul un dépotage brouillon peut être soumis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        depotage.statut = DepotageStatus.SOUMIS
        depotage.save(update_fields=["statut"])

        return Response({"detail": "Dépotage soumis."})
    
    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        depotage = self.get_object()

        if depotage.statut != DepotageStatus.SOUMIS:
            raise ValidationError("Dépotage non soumis.")

        with transaction.atomic():
            try:
                Cuve.objects.select_for_update().get(
                    station=depotage.station,
                    produit=depotage.produit,
                    actif=True,
                )
            except Cuve.DoesNotExist:
                raise ValidationError(
                    "Aucune cuve active n’est configurée pour ce produit."
                )

            depotage.statut = DepotageStatus.CONFIRME
            depotage.validated_by = request.user
            depotage.save(update_fields=["statut", "validated_by", "updated_at"])

        return Response({"status": "confirme"})

        # ======================================================
        # 1️⃣ CONFIRMATION DÉPOTAGE
        # ======================================================
        depotage.statut = DepotageStatus.CONFIRME
        depotage.validated_by = request.user
        depotage.validated_at = timezone.now()
        depotage.save

        # ======================================================
        # 2️⃣ MISE À JOUR STOCK (CUVE)
        # ======================================================
        try:
            cuve = Cuve.objects.select_for_update().get(
                station=depotage.station,
                produit=depotage.produit,
            )
        except Cuve.DoesNotExist:
            raise ValidationError(
                "Aucune cuve n’est configurée pour ce produit sur cette station. "
                "Veuillez créer la cuve avant de confirmer le dépotage."
            )

        # Mouvement de stock (ENTRÉE)
        MouvementStock.objects.create(
            tenant=depotage.station.tenant,
            station=depotage.station,
            cuve=cuve,
            type_mouvement=MouvementStock.MOUVEMENT_ENTREE,
            quantite=depotage.quantite_livree,
            source_type="DEPOTAGE",
            source_id=depotage.id,
            date_mouvement=depotage.date_depotage,
        )

        # Mise à jour du stock courant
        cuve.stock_actuel += depotage.quantite_livree
        cuve.save(update_fields=["stock_actuel"])

        # ======================================================
        # 3️⃣ CALCUL ÉCART DE JAUGE (INFORMATIF)
        # ======================================================
        variation_jauge = (
            depotage.jauge_apres - depotage.jauge_avant
        )

        depotage.ecart_jauge = (
            variation_jauge - depotage.quantite_livree
        )
        depotage.save(update_fields=["ecart_jauge"])

        # ======================================================
        # 4️⃣ DÉPENSE FINANCIÈRE OFFICIELLE
        # ======================================================
        TransactionStation.objects.create(
            tenant=depotage.station.tenant,
            station=depotage.station,
            date=timezone.now(),  # pour les KPI jour/mois
            type="DEPENSE",
            montant=depotage.montant_total,
            source_type="DEPOTAGE",
            source_id=depotage.id,
            ffinance_status="CONFIRMEE",
            created_by=request.user,
        )

    @action(detail=True, methods=["post"])
    def transferer(self, request, pk=None):
        depotage = self.get_object()

        if depotage.statut != "CONFIRME":
            raise ValidationError("Dépotage non confirmé.")

        with transaction.atomic():
            # 1️⃣ Stock (service métier)
            cuve = appliquer_stock_depotage(
                depotage=depotage,
                user=request.user,
            )

            # 2️⃣ Dépense financière (ALIGNÉE AU MODÈLE RÉEL)
            TransactionStation.objects.create(
                tenant=depotage.station.tenant,
                station=depotage.station,
                date=timezone.now(),
                type="DEPENSE",
                montant=depotage.montant_total,
                source_type="DEPOTAGE",
                source_id=depotage.id,
                finance_status="CONFIRMEE",
            )

            # 3️⃣ Statut final
            depotage.statut = "TRANSFERE"
            depotage.save(update_fields=["statut"])

        return Response(
            {
                "status": "transfere",
                "cuve": cuve.id,
                "stock_actuel": str(cuve.stock_actuel),
            },
            status=status.HTTP_200_OK,
        )