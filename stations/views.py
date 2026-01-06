# saas-backend/stations/views.py

from django.db.models import Count
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import now
from django.db.models import Sum
from django.db.models.functions import TruncDate
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError

from accounts.constants import UserRole
from accounts.models import Utilisateur

from core.pagination import StandardResultsSetPagination
from finances_station.models import TransactionStation

from .models import (
    Station,
    VenteCarburant,
    Local,
    ContratLocation,
    RelaisEquipe,
    FaitStatus,
)
from .serializers import (
    StationSerializer,
    VenteCarburantSerializer,
    LocalSerializer,
    ContratLocationSerializer,
    RelaisEquipeSerializer,
)
from .permissions import CanAccessStations

class StationViewSet(ModelViewSet):
    serializer_class = StationSerializer
    permission_classes = [IsAuthenticated, CanAccessStations]
    pagination_class = StandardResultsSetPagination

    filter_backends = [
        DjangoFilterBackend,
        SearchFilter,
        OrderingFilter,
    ]

    search_fields = ["nom", "adresse"]
    ordering_fields = ["nom", "created_at"]

    # ✅ AJOUT DES FILTRES MÉTIERS
    filterset_fields = [
        "active",
        "region",
        "departement",
    ]

    def get_queryset(self):
        user = self.request.user

        qs = Station.objects.all()

        # 🔒 SuperAdmin : toutes les stations
        if user.role == UserRole.SUPERADMIN:
            return qs

        # 🔒 AdminTenantStation : stations du tenant
        if user.role == UserRole.ADMIN_TENANT_STATION:
            return qs.filter(tenant=user.tenant)

        # 🔒 Personnel station : sa station uniquement
        if user.station_id:
            return qs.filter(id=user.station_id)

        return Station.objects.none()

    def perform_create(self, serializer):
        user = self.request.user

        if user.role != UserRole.ADMIN_TENANT_STATION:
            raise PermissionDenied(
                "Seul un AdminTenantStation peut créer une station."
            )

        gerant_data = serializer.validated_data.pop("gerant", None)
        if not gerant_data:
            raise ValidationError(
                {"gerant": "Un GERANT est obligatoire."}
            )

        with transaction.atomic():
            station = serializer.save(tenant=user.tenant)

            user.stations_administrees.add(station)

            Utilisateur.objects.create_user(
                username=gerant_data["username"],
                password=gerant_data["password"],
                email=gerant_data.get("email", ""),
                first_name=gerant_data.get("first_name", ""),
                last_name=gerant_data.get("last_name", ""),
                role=UserRole.GERANT,
                tenant=user.tenant,
                station=station,
                is_active=True,
            )

class TenantViewSetMixin:
    serializer_class = StationSerializer
    permission_classes = [IsAuthenticated, CanAccessStations]
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


class VenteCarburantViewSet(ModelViewSet):
    queryset = VenteCarburant.objects.all()
    serializer_class = VenteCarburantSerializer
    permission_classes = [IsAuthenticated, CanAccessStations]
    pagination_class = StandardResultsSetPagination

    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ["station", "produit"]
    ordering_fields = ["date"]

    def perform_create(self, serializer):
        user = self.request.user

        if user.role not in (
            UserRole.GERANT,
            UserRole.SUPERVISEUR,
            UserRole.POMPISTE,
        ):
            raise PermissionDenied("Rôle non autorisé.")

        serializer.save(
            tenant=user.tenant,
            station=user.station,
            created_by=user,
            date=timezone.now(),
        )
    
    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        vente = self.get_object()

        # 🔐 Autorisation
        if request.user.role != UserRole.SUPERVISEUR:
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
        
        if user.role not in (
            UserRole.GERANT,
            UserRole.SUPERVISEUR,
            UserRole.POMPISTE,
        ):
            raise PermissionDenied("Rôle non autorisé pour créer une vente.")
        
        if Station.use_relais:
            raise PermissionDenied(
                "Les ventes sont gérées via les relais d’équipe."
            )


        serializer.save(
            tenant=user.tenant,
            station=user.station,
            created_by=user,
            date=timezone.now()
        )
    
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

        if request.user.role not in (
            UserRole.POMPISTE,
            UserRole.SUPERVISEUR,
        ):
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
    permission_classes = [CanAccessStations]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["station", "occupe"]
    search_fields = ["nom", "type_local"]


class ContratLocationViewSet(TenantViewSetMixin, ModelViewSet):
    queryset = ContratLocation.objects.all()
    serializer_class = ContratLocationSerializer
    permission_classes = [CanAccessStations]
    pagination_class = StandardResultsSetPagination
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ["actif"]
    search_fields = ["locataire"]


class StationDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # 🔐 Sécurité absolue
        if not user.station:
            return Response(
                {"detail": "Utilisateur sans station"},
                status=403
            )

        station = user.station
        today = now().date()

        # =========================
        # BASE TRANSACTIONS STATION
        # =========================
        qs = TransactionStation.objects.filter(
            station=station
        )

        # =========================
        # KPI JOUR
        # =========================
        qs_jour = qs.filter(date=today)

        recettes_jour = (
            qs_jour.filter(type="RECETTE")
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        depenses_jour = (
            qs_jour.filter(type="DEPENSE")
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        # =========================
        # KPI MOIS
        # =========================
        qs_mois = qs.filter(
            date__year=today.year,
            date__month=today.month
        )

        recettes_mois = (
            qs_mois.filter(type="RECETTE")
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        depenses_mois = (
            qs_mois.filter(type="DEPENSE")
            .aggregate(total=Sum("montant"))["total"] or 0
        )

        # =========================
        # ÉVOLUTION TEMPORELLE
        # =========================
        evolution_qs = (
            qs_mois
            .annotate(jour=TruncDate("date"))
            .values("jour", "type")
            .annotate(total=Sum("montant"))
            .order_by("jour")
        )

        evolution_map = {}

        for item in evolution_qs:
            jour = item["jour"].isoformat()

            if jour not in evolution_map:
                evolution_map[jour] = {
                    "date": jour,
                    "recettes": 0,
                    "depenses": 0,
                }

            if item["type"] == "RECETTE":
                evolution_map[jour]["recettes"] = float(item["total"])
            elif item["type"] == "DEPENSE":
                evolution_map[jour]["depenses"] = float(item["total"])

        # =========================
        # RESPONSE STRICTEMENT ALIGNÉE FRONT
        # =========================
        return Response({
            "jour": {
                "recettes": float(recettes_jour),
                "depenses": float(depenses_jour),
                "solde": float(recettes_jour - depenses_jour),
            },
            "mois": {
                "recettes": float(recettes_mois),
                "depenses": float(depenses_mois),
                "solde": float(recettes_mois - depenses_mois),
            },
            "evolution": list(evolution_map.values()),
        })

class RelaisEquipeViewSet(ModelViewSet):
    queryset = RelaisEquipe.objects.all()
    serializer_class = RelaisEquipeSerializer
    permission_classes = [CanAccessStations]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return RelaisEquipe.objects.all()

        return RelaisEquipe.objects.filter(
            tenant=user.tenant,
            station=user.station
        )

    # ======================
    # CRÉATION RELAIS
    # ======================
    def perform_create(self, serializer):
        user = self.request.user

        if user.role not in (
            UserRole.POMPISTE,
            UserRole.SUPERVISEUR,
        ):
            raise PermissionDenied(
                "Rôle non autorisé pour créer un relais."
            )

        serializer.save(
            tenant=user.tenant,
            station=user.station,
            created_by=user,
            status=FaitStatus.BROUILLON
        )

    # ======================
    # MODIFICATION RELAIS
    # ======================
    def perform_update(self, serializer):
        instance = self.get_object()

        if instance.status != FaitStatus.BROUILLON:
            raise PermissionDenied(
                "Ce relais ne peut plus être modifié."
            )

        serializer.save()

    # ======================
    # SOUMISSION
    # ======================
    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):
        relais = self.get_object()

        if request.user.role not in (
            UserRole.POMPISTE,
            UserRole.SUPERVISEUR,
        ):
            return Response(
                {"detail": "Non autorisé"},
                status=403
            )

        if relais.status != FaitStatus.BROUILLON:
            return Response(
                {"detail": "État invalide"},
                status=400
            )

        relais.status = FaitStatus.SOUMIS
        relais.soumis_par = request.user
        relais.soumis_le = timezone.now()
        relais.save(
            update_fields=["status", "soumis_par", "soumis_le"]
        )

        return Response({"status": "soumis"})

    # ======================
    # VALIDATION & FINANCES
    # ======================
    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        relais = self.get_object()

        if request.user.role != UserRole.SUPERVISEUR:
            return Response(
                {"detail": "Non autorisé"},
                status=403
            )

        if relais.status != FaitStatus.SOUMIS:
            return Response(
                {"detail": "État invalide"},
                status=400
            )

        # 💰 Création transaction FINANCES
        TransactionStation.objects.get_or_create(
            source_type="RelaisEquipe",
            source_id=relais.id,
            defaults={
                "tenant": relais.tenant,
                "station": relais.station,
                "type": "RECETTE",
                "montant": relais.total_encaisse,
                "date": relais.fin_relais,
                "finance_status": "PROVISOIRE",
            }
        )

        relais.status = FaitStatus.TRANSFERE
        relais.valide_par = request.user
        relais.valide_le = timezone.now()
        relais.save(
            update_fields=[
                "status",
                "valide_par",
                "valide_le",
            ]
        )

        return Response({"status": "transféré"})

class AdminTenantStationDashboardAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # 🔒 Sécurité : uniquement AdminTenantStation
        if user.role != "ADMIN_TENANT_STATION":
            return Response(
                {"detail": "Accès non autorisé."},
                status=403
            )

        qs = Station.objects.filter(tenant=user.tenant)

        total_stations = qs.count()
        active_stations = qs.filter(active=True).count()
        inactive_stations = qs.filter(active=False).count()

        stations_by_region = (
            qs.values("region")
            .annotate(count=Count("id"))
            .order_by("region")
        )

        return Response({
            "totals": {
                "total": total_stations,
                "active": active_stations,
                "inactive": inactive_stations,
            },
            "by_region": list(stations_by_region),
        })
    
class AdminTenantStationDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role != UserRole.ADMIN_TENANT_STATION:
            return Response({"detail": "Accès interdit"}, status=403)

        start_date = request.query_params.get("startDate")
        end_date = request.query_params.get("endDate")
        station_id = request.query_params.get("station")

        stations_qs = Station.objects.filter(tenant=user.tenant)

        if station_id:
            stations_qs = stations_qs.filter(id=station_id)

        # 🔹 STATS STATIONS
        total_stations = stations_qs.count()
        active_stations = stations_qs.filter(active=True).count()
        inactive_stations = total_stations - active_stations

        # 🔹 TRANSACTIONS
        transactions = TransactionStation.objects.filter(
            station__in=stations_qs,
            date__range=[start_date, end_date],
        )

        total_recettes = transactions.filter(
            type="RECETTE"
        ).aggregate(total=Sum("montant"))["total"] or 0

        total_depenses = transactions.filter(
            type="DEPENSE"
        ).aggregate(total=Sum("montant"))["total"] or 0

        by_region = (
            stations_qs
            .values("region")
            .annotate(total=Count("id"))
            .order_by("region")
        )

        return Response({
            "totals": {
                "total": total_stations,
                "active": active_stations,
                "inactive": inactive_stations,
            },
            "by_region": list(by_region),
            "total_recettes": total_recettes,
            "total_depenses": total_depenses,
            "solde": total_recettes - total_depenses,
            "top_services": [],
        })

