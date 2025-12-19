from rest_framework.viewsets import ModelViewSet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from core.pagination import StandardResultsSetPagination
from .models import Station, VenteCarburant, Local, ContratLocation
from .serializers import (
    StationSerializer,
    VenteCarburantSerializer,
    LocalSerializer,
    ContratLocationSerializer,
)
from .permissions import IsStationActor, CanCreateStation
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

class TenantViewSetMixin:
    permission_classes = [IsStationActor]
    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.user.tenant,
            created_by=self.request.user
        )

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if not user.is_superuser:
            qs = qs.filter(tenant=user.tenant)
        return qs


class StationViewSet(TenantViewSetMixin, ModelViewSet):
    queryset = Station.objects.all()
    serializer_class = StationSerializer
    permission_classes = [CanCreateStation]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    search_fields = ["nom", "adresse"]
    ordering_fields = ["nom", "created_at"]
    filterset_fields = ["active"]

    def perform_create(self, serializer):
        serializer.save(tenant=self.request.user.tenant)


class VenteCarburantViewSet(TenantViewSetMixin, ModelViewSet):
    queryset = VenteCarburant.objects.all()
    serializer_class = VenteCarburantSerializer
    permission_classes = [IsStationActor]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["station", "produit"]
    search_fields = ["produit"]
    ordering_fields = ["date"]

    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):
        vente = self.get_object()
        if vente.status != FaitStatus.BROUILLON:
            return Response({"detail": "État invalide"}, status=400)

        vente.status = FaitStatus.SOUMIS
        vente.soumis_par = request.user
        vente.soumis_le = timezone.now()
        vente.save()

        return Response({"status": "soumis"})
    
    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        vente = self.get_object()

        # 🔐 Autorisation
        if request.user.role != "CHEF_STATION":
            return Response({"detail": "Non autorisé"}, status=403)

        # 🔁 État attendu
        if vente.status != FaitStatus.SOUMIS:
            return Response({"detail": "État invalide"}, status=400)

        # ✅ Validation métier
        vente.status = FaitStatus.VALIDE
        vente.valide_par = request.user
        vente.valide_le = timezone.now()
        vente.save()

        # 💰 Création FINANCES (idempotente)
        TransactionStation.objects.get_or_create(
            source_type="VenteCarburant",
            source_id=vente.id,
            defaults={
                "tenant": vente.tenant,
                "station": vente.station,
                "type": "RECETTE",
                "montant": vente.volume * vente.prix_unitaire,
                "date": vente.date,
            }
        )

        # 🔒 Verrouillage final
        vente.status = FaitStatus.TRANSFERE
        vente.save(update_fields=["status"])

    def perform_create(self, serializer):
        user = self.request.user
        
        if user.role not in ("ChefStation", "Collecteur"):
            raise PermissionDenied("Rôle non autorisé pour créer une vente.")

        serializer.save(
            tenant=user.tenant,
            station=user.station,
            created_by=user
        )

        return Response({"status": "transféré"})
    
    def perform_update(self, serializer):
        instance = self.get_object()

        if instance.status != FaitStatus.BROUILLON:
            raise PermissionDenied("Cette vente ne peut plus être modifiée.")

        serializer.save()

    def destroy(self, request, *args, **kwargs):
        vente = self.get_object()

        if vente.status != FaitStatus.BROUILLON:
            raise PermissionDenied("Suppression interdite pour cette vente.")

        return super().destroy(request, *args, **kwargs)
    
    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):
        vente = self.get_object()

        if request.user.role != "ChefStation":
            return Response({"detail": "Non autorisé"}, status=403)

        if vente.status != FaitStatus.BROUILLON:
            return Response({"detail": "État invalide"}, status=400)

        vente.status = FaitStatus.SOUMIS
        vente.soumis_par = request.user
        vente.soumis_le = timezone.now()
        vente.save(update_fields=["status", "soumis_par", "soumis_le"])

        return Response({"status": "soumis"})





class LocalViewSet(TenantViewSetMixin, ModelViewSet):
    queryset = Local.objects.all()
    serializer_class = LocalSerializer
    permission_classes = [IsStationActor]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["station", "occupe"]
    search_fields = ["nom", "type_local"]


class ContratLocationViewSet(TenantViewSetMixin, ModelViewSet):
    queryset = ContratLocation.objects.all()
    serializer_class = ContratLocationSerializer
    permission_classes = [IsStationActor]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["actif"]
    search_fields = ["locataire"]
