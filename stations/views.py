# saas-backend/stations/views.py

from django.db.models import DecimalField as ModelDecimalField
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Sum, Q
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import now
from django.db.models.functions import TruncDate
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView

from accounts.constants import UserRole
from accounts.models import Utilisateur
from django.db.models.functions import Coalesce

from core.pagination import StandardResultsSetPagination
from dashboard.permissions import IsAdminTenantStation
from finances_station.models import TransactionStation
from stations.models_depotage.cuve import Cuve, CuveStatus
from stations.models_produit import PrixCarburant, ProduitCarburant
from stations.services.stock import get_capacite_totale_produit, get_seuil_critique_reel, get_stock_global_produit

from .models import (
    IndexPompe,
    Pompe,
    Station,
    RelaisEquipe,
    FaitStatus,
)
from .serializers import (
    CuveSerializer,
    IndexPompeReadSerializer,
    IndexPompeWriteSerializer,
    PompeActiveSerializer,
    PompeSerializer,
    PrixCarburantSerializer,
    ProduitCarburantSerializer,
    StationSerializer,
    RelaisEquipeSerializer,
)
from .permissions import CanAccessStations, IsStationAdminOrActor

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

        # 🔒 Seul AdminTenantStation peut créer une station
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

            # 1️⃣ Création station
            station = serializer.save(tenant=user.tenant)

            # 2️⃣ Vérifier qu'aucun GERANT actif n'existe déjà
            if Utilisateur.objects.filter(
                station=station,
                role=UserRole.GERANT,
                is_active=True
            ).exists():
                raise ValidationError(
                    {"gerant": "Un chef de station actif existe déjà."}
                )

            # 3️⃣ Création du GERANT
            gerant = Utilisateur.objects.create_user(
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

            # 4️⃣ Lier la station à l'AdminTenantStation
            user.stations_administrees.add(station)

        return station

# ============================================================
# CUVES
# ============================================================
class CuveViewSet(ModelViewSet):
    serializer_class = CuveSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        # 🔹 AdminTenantStation → toutes les stations administrées
        if user.role == UserRole.ADMIN_TENANT_STATION:
            return Cuve.objects.filter(
                tenant=user.tenant,
                station__in=user.stations_administrees.all()
            )

        # 🔹 GERANT / SUPERVISEUR → station unique
        if user.role in (
            UserRole.GERANT,
            UserRole.SUPERVISEUR,
        ):
            return Cuve.objects.filter(
                tenant=user.tenant,
                station=user.station
            )

        return Cuve.objects.none()

    def perform_create(self, serializer):
        user = self.request.user
        station = serializer.validated_data.get("station")

        if user.role != UserRole.ADMIN_TENANT_STATION:
            raise PermissionDenied("Accès réservé à l’AdminTenantStation.")

        if station.tenant_id != user.tenant_id:
            raise PermissionDenied("Station hors tenant.")

        if not user.stations_administrees.filter(id=station.id).exists():
            raise PermissionDenied("Station non autorisée.")

        serializer.save()

    def update(self, request, *args, **kwargs):
        if request.user.role != UserRole.ADMIN_TENANT_STATION:
            raise PermissionDenied("Modification réservée à l’AdminTenantStation.")
        return super().update(request, *args, **kwargs)


    def destroy(self, request, *args, **kwargs):
        if request.user.role != UserRole.ADMIN_TENANT_STATION:
            raise PermissionDenied("Suppression réservée à l’AdminTenantStation.")
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def changer_statut(self, request, pk=None):
        cuve = self.get_object()
        nouveau_statut = request.data.get("statut")

        if not nouveau_statut:
            return Response(
                {"detail": "Statut requis."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            cuve.changer_statut(nouveau_statut)
        except DjangoValidationError as e:
            return Response(
                {"detail": e.message},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"detail": "Statut mis à jour."}
        )
    
# ==========================================================
# PRODUIT CARBURANT
# ==========================================================
class ProduitCarburantViewSet(ModelViewSet):
    serializer_class = ProduitCarburantSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete"]

    def get_queryset(self):
        user = self.request.user

        return (
            ProduitCarburant.objects
            .filter(tenant=user.tenant)
            .annotate(
                stock_global=Coalesce(
                    Sum(
                        "cuves__stock_actuel",
                        filter=Q(
                            cuves__statut__in=[
                                CuveStatus.ACTIVE,
                                CuveStatus.STANDBY,
                            ]
                        ),
                        output_field=ModelDecimalField(
                            max_digits=12,
                            decimal_places=2,
                        ),
                    ),
                    0,
                    output_field=ModelDecimalField(
                        max_digits=12,
                        decimal_places=2,
                    ),
                )
            )
        )

    def perform_create(self, serializer):
        user = self.request.user

        if user.role != UserRole.ADMIN_TENANT_STATION:
            raise PermissionDenied(
                "Accès réservé à l’AdminTenantStation."
            )

        serializer.save()

    def perform_destroy(self, instance):
        if instance.cuve_set.exists():
            raise PermissionDenied(
                "Impossible de supprimer un produit utilisé par une cuve."
            )

        instance.delete()

    @action(detail=True, methods=["post"])
    def desactiver(self, request, pk=None):
        produit = self.get_object()

        try:
            produit.desactiver()
        except DjangoValidationError as e:
            return Response(
                {"detail": e.message},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"detail": "Produit désactivé."})


# ============================================================
# TENANTS
# ============================================================
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


class PompeViewSet(ModelViewSet):
    serializer_class = PompeSerializer
    permission_classes = [IsAdminTenantStation]

    def get_queryset(self):
        user = self.request.user
        station_id = self.request.query_params.get("station_id")

        qs = Pompe.objects.all()

        # 🔐 Sécurité multi-tenant
        qs = qs.filter(station__tenant=user.tenant)

        # 🎯 Filtre explicite station
        if station_id:
            qs = qs.filter(station_id=station_id)

        # 🔒 Visibilité selon rôle
        if user.role != UserRole.ADMIN_TENANT_STATION:
            qs = qs.filter(actif=True)

        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    

class PompeActiveListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        pompes = (
            Pompe.objects
            .filter(
                station=user.station,
                actif=True,
            )
            .prefetch_related("index_pompes")
            .order_by("reference")
        )

        serializer = PompeActiveSerializer(pompes, many=True)
        return Response(serializer.data)


  
class IndexPompeViewSet(ModelViewSet):
    """
    CRUD des index de pompe (paramétrage).
    """
    permission_classes = [
        IsAuthenticated,
        IsStationAdminOrActor,
    ]

    queryset = (
        IndexPompe.objects
        .select_related("pompe", "pompe__station")
    )

    def get_queryset(self):
        user = self.request.user

        qs = (
            IndexPompe.objects
            .select_related("pompe", "pompe__station")
        )

        # 🔒 ADMIN TENANT
        if user.role == UserRole.ADMIN_TENANT_STATION:
            qs = qs.filter(pompe__station__tenant=user.tenant)

            # 🎯 FILTRE OBLIGATOIRE PAR STATION
            station_id = self.request.query_params.get("station")
            if not station_id:
                return qs.none()

            return qs.filter(pompe__station_id=station_id)

        # 🔒 AUTRES RÔLES (station-bound)
        if user.station_id:
            return qs.filter(pompe__station=user.station)

        return qs.none()

    def get_serializer_class(self):
        if self.action in ["list", "retrieve"]:
            return IndexPompeReadSerializer
        return IndexPompeWriteSerializer

# class IndexPompeActifListView(ListAPIView):
#     permission_classes = [IsAuthenticated, IsStationAdminOrActor]

#     def get_queryset(self):
#         user = self.request.user

#         return (
#             IndexPompe.objects
#             .filter(
#                 pompe__station=user.station,
#                 actif=True
#             )
#             .select_related("pompe", "produit")
#         )

#     def list(self, request, *args, **kwargs):
#         queryset = self.get_queryset()

#         data = [
#             {
#                 "id": idx.id,
#                 "pompe_reference": idx.pompe.reference,
#                 "produit_id": idx.produit.id,
#                 "produit_code": idx.produit.code,
#                 "index_actuel": idx.index_courant,
#             }
#             for idx in queryset
#         ]

#         return Response(data)


class IndexPompeActifListView(ListAPIView):
    permission_classes = [IsAuthenticated, IsStationAdminOrActor]

    def get_queryset(self):
        user = self.request.user

        return (
            IndexPompe.objects
            .filter(
                pompe__station=user.station,
                actif=True
            )
            .select_related("pompe", "produit")
        )

    def list(self, request, *args, **kwargs):
        user = request.user
        queryset = self.get_queryset()

        # 🔥 Charger tous les prix actifs en une requête
        prix_map = {
            p.produit_id: p.prix_unitaire
            for p in PrixCarburant.objects.filter(
                tenant=user.tenant,
                station=user.station,
                actif=True
            )
        }

        data = []

        for idx in queryset:
            data.append({
                "id": idx.id,
                "pompe_reference": idx.pompe.reference,
                "produit_id": idx.produit.id,
                "produit_code": idx.produit.code,
                "index_actuel": idx.index_courant,
                "prix_unitaire": float(
                    prix_map.get(idx.produit.id, 0)
                ),
            })

        return Response(data)


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

    serializer_class = RelaisEquipeSerializer
    permission_classes = [IsAuthenticated, CanAccessStations]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        user = self.request.user

        qs = RelaisEquipe.objects.select_related(
            "station",
            "tenant"
        ).prefetch_related("produits")

        if user.is_superuser:
            return qs.order_by("-created_at")

        return qs.filter(
            tenant=user.tenant,
            station=user.station
        ).order_by("-created_at")

    # ======================
    # CREATE
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
    # UPDATE
    # ======================
    def perform_update(self, serializer):

        instance = self.get_object()

        if instance.status != FaitStatus.BROUILLON:
            raise PermissionDenied(
                "Ce relais ne peut plus être modifié."
            )

        serializer.save()

    # ======================
    # SOUMETTRE
    # ======================
    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):

        relais = self.get_object()

        if request.user.role not in (
            UserRole.POMPISTE,
            UserRole.SUPERVISEUR,
        ):
            return Response({"detail": "Non autorisé"}, status=403)

        try:
            relais.changer_statut(
                FaitStatus.SOUMIS,
                request.user
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=400)

        return Response({"status": relais.status})

    # ======================
    # VALIDER
    # ======================
    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):

        relais = self.get_object()

        if not self.produits.exists():
            raise ValidationError("Aucun produit dans le relais.")

        if request.user.role != UserRole.SUPERVISEUR:
            return Response({"detail": "Non autorisé"}, status=403)

        try:
            relais.changer_statut(
                FaitStatus.VALIDE,
                request.user
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=400)

        return Response({"status": relais.status})

    # ======================
    # TRANSFERER
    # ======================
    @action(detail=True, methods=["post"])
    def transferer(self, request, pk=None):

        relais = self.get_object()

        if request.user.role != UserRole.GERANT:
            return Response({"detail": "Non autorisé"}, status=403)

        try:
            relais.changer_statut(
                FaitStatus.TRANSFERE,
                request.user
            )
        except ValidationError as e:
            return Response({"detail": str(e)}, status=400)

        return Response({"status": relais.status})


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

class StockGlobalProduitAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        if not user.station:
            return Response(
                {"detail": "Utilisateur sans station"},
                status=403
            )

        station = user.station

        produits = station.tenant.produits_carburant.filter(actif=True)

        data = []

        for produit in produits:

            stock_global = get_stock_global_produit(station, produit)
            seuil = get_seuil_critique_reel(station, produit)
            capacite = get_capacite_totale_produit(station, produit)

            data.append({
                "produit": produit.code,
                "stock_global": float(stock_global),
                "capacite_totale": float(capacite),
                "seuil_critique": float(seuil),
                "critique": stock_global <= seuil,
                "pourcentage_remplissage":
                    float((stock_global / capacite) * 100)
                    if capacite > 0 else 0
            })

        return Response(data)

class PrixCarburantViewSet(ModelViewSet):

    serializer_class = PrixCarburantSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        qs = PrixCarburant.objects.select_related(
            "produit",
            "station"
        ).filter(
            tenant=user.tenant
        )

        station_id = self.request.query_params.get("station_id")
        actif = self.request.query_params.get("actif")

        if station_id:
            qs = qs.filter(station_id=station_id)

        if actif == "true":
            qs = qs.filter(actif=True)

        return qs.order_by("-date_debut")

    def perform_create(self, serializer):
        user = self.request.user

        if user.role != UserRole.ADMIN_TENANT_STATION:
            raise PermissionDenied("Non autorisé.")

        instance = serializer.save(
            tenant=user.tenant,
            created_by=user,
            date_debut=timezone.now(),
            actif=False
        )

        instance.activer()