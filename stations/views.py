# saas-backend/stations/views.py

from datetime import datetime
from calendar import monthrange
from decimal import Decimal

from django.db import models
from django.db.models import (
    Sum,
    Count,
    F,
    Q,
    DecimalField
)
from rest_framework import status
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Sum, Q
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import now
from django.db.models.functions import TruncDate
from django_filters.rest_framework import DjangoFilterBackend


from stations.models import RelaisIndex
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
from stations.models_objectif import ObjectifStation
from .serializers import (
    CuveSerializer,
    IndexPompeReadSerializer,
    IndexPompeWriteSerializer,
    ObjectifStationSerializer,
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
                        output_field=DecimalField(
                            max_digits=12,
                            decimal_places=2,
                        ),
                    ),
                    0,
                    output_field=DecimalField(
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
        ).prefetch_related("indexes")

        if not user.is_superuser:
            qs = qs.filter(
                tenant=user.tenant,
                station=user.station
            )

        # ✅ FILTRE STATUS
        status_param = self.request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param)

        return qs.order_by("-created_at")

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

        if not relais.indexes.exists():
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

    # ======================
    # STATS
    # ======================
    @action(detail=False, methods=["get"])
    def stats(self, request):
        user = request.user

        qs = RelaisEquipe.objects.all()

        if not user.is_superuser:
            qs = qs.filter(
                tenant=user.tenant,
                station=user.station
            )

        stats = qs.values("status").annotate(
            total=Count("id")
        )

        # Initialiser tous les statuts à 0
        result = {
            "BROUILLON": 0,
            "SOUMIS": 0,
            "VALIDE": 0,
            "TRANSFERE": 0,
        }

        for item in stats:
            result[item["status"]] = item["total"]

        return Response(result)
    
    # ======================
    # NEXT INDEXES
    # ======================
    @action(detail=False, methods=["get"], url_path="next-indexes")
    def next_indexes(self, request):

        user = request.user

        last_relais = (
            RelaisEquipe.objects
            .filter(
                station=user.station,
                status=FaitStatus.TRANSFERE
            )
            .prefetch_related("indexes")
            .order_by("-fin_relais")
            .first()
        )

        if not last_relais:
            return Response({
                "indexes": [],
                "equipe_sortante": None
            })

        return Response({
            "indexes": [
                {
                    "index_pompe": idx.index_pompe_id,
                    "dernier_index_fin": idx.index_fin,
                }
                for idx in last_relais.indexes.all()
            ],
            "equipe_sortante": last_relais.equipe_entrante
        })


class AdminTenantStationDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role != UserRole.ADMIN_TENANT_STATION:
            return Response({"detail": "Accès interdit"}, status=403)

        # ===============================
        # PARAMÈTRES MENSUELS (OBLIGATOIRES)
        # ===============================

        annee = request.query_params.get("annee")
        mois = request.query_params.get("mois")

        if not annee or not mois:
            return Response(
                {"detail": "annee et mois sont obligatoires"},
                status=400
            )

        annee = int(annee)
        mois = int(mois)

        last_day = monthrange(annee, mois)[1]
        start_date = datetime(annee, mois, 1)
        end_date = datetime(annee, mois, last_day)

        # ===============================
        # FILTRAGE STATIONS
        # ===============================

        station_id = request.query_params.get("station")

        stations_qs = Station.objects.filter(tenant=user.tenant)

        if station_id:
            stations_qs = stations_qs.filter(id=station_id)

        # ===============================
        # STATS STATIONS
        # ===============================

        total_stations = stations_qs.count()
        active_stations = stations_qs.filter(active=True).count()
        inactive_stations = total_stations - active_stations

        by_region = (
            stations_qs
            .values("region")
            .annotate(total=Count("id"))
            .order_by("region")
        )

        # ===============================
        # VOLUME RÉSEAU PAR PRODUIT
        # ===============================

        volume_par_produit_qs = (
            RelaisIndex.objects
            .filter(
                relais__tenant=user.tenant,
                relais__station__in=stations_qs,
                relais__status="TRANSFERE",
                relais__fin_relais__range=[start_date, end_date],
            )
            .values("index_pompe__produit__code")
            .annotate(
                volume=Coalesce(
                    Sum(F("index_fin") - F("index_debut")),
                    Decimal("0")
                )
            )
        )

        volume_par_produit = [
            {
                "produit": row["index_pompe__produit__code"],
                "volume": row["volume"]
            }
            for row in volume_par_produit_qs
        ]

        # ===============================
        # TRANSACTIONS RÉSEAU
        # ===============================

        transactions = TransactionStation.objects.filter(
            tenant=user.tenant,
            station__in=stations_qs,
            date__range=[start_date, end_date],
        )

        recettes = transactions.filter(type="RECETTE")

        totals = transactions.aggregate(
            total_recettes=Coalesce(
                Sum("montant", filter=models.Q(type="RECETTE")),
                Decimal("0")
            ),
            total_depenses=Coalesce(
                Sum("montant", filter=models.Q(type="DEPENSE")),
                Decimal("0")
            ),
            volume_total=Coalesce(
                Sum("volume", filter=models.Q(type="RECETTE")),
                Decimal("0")
            ),
        )

        # ===============================
        # OBJECTIFS (UNE SEULE REQUÊTE)
        # ===============================

        objectifs_qs = (
            ObjectifStation.objects
            .filter(
                tenant=user.tenant,
                annee=annee,
                mois=mois,
                station__in=stations_qs
            )
            .values(
                "station_id",
                "produit_id",
                "volume_cible",
                "ca_cible"
            )
        )

        # Indexation rapide
        objectifs_dict = {}
        volume_cible_par_station = {}
        ca_cible_par_station = {}

        for o in objectifs_qs:
            key = (o["station_id"], o["produit_id"])
            objectifs_dict[key] = o["volume_cible"]

            volume_cible_par_station.setdefault(o["station_id"], Decimal("0"))
            volume_cible_par_station[o["station_id"]] += o["volume_cible"]

            ca_cible_par_station.setdefault(o["station_id"], Decimal("0"))
            ca_cible_par_station[o["station_id"]] += o["ca_cible"]

        # ===============================
        # VOLUME RÉEL PAR STATION
        # ===============================

        volume_reel_qs = (
            RelaisIndex.objects
            .filter(
                relais__tenant=user.tenant,
                relais__station__in=stations_qs,
                relais__status="TRANSFERE",
                relais__fin_relais__range=[start_date, end_date],
            )
            .values("relais__station_id")
            .annotate(
                volume_reel=Coalesce(
                    Sum(F("index_fin") - F("index_debut")),
                    Decimal("0")
                )
            )
        )

        volume_reel_dict = {
            row["relais__station_id"]: row["volume_reel"]
            for row in volume_reel_qs
        }

        # ===============================
        # CA RÉEL PAR STATION
        # ===============================

        ca_reel_qs = (
            recettes
            .values("station_id")
            .annotate(
                ca_total_reel=Coalesce(
                    Sum("montant"),
                    Decimal("0")
                )
            )
        )

        ca_reel_dict = {
            row["station_id"]: row["ca_total_reel"]
            for row in ca_reel_qs
        }

        # ===============================
        # CALCUL PERFORMANCE STATION
        # ===============================

        stations_resume = []

        for station in stations_qs:
            sid = station.id

            volume_reel = volume_reel_dict.get(sid, Decimal("0"))
            volume_cible = volume_cible_par_station.get(sid, Decimal("0"))

            if volume_cible > 0:
                perf_volume = (volume_reel / volume_cible) * Decimal("100")
            else:
                perf_volume = Decimal("0")

            ca_reel = ca_reel_dict.get(sid, Decimal("0"))
            ca_cible = ca_cible_par_station.get(sid, Decimal("0"))

            if ca_cible > 0:
                perf_ca = (ca_reel / ca_cible) * Decimal("100")
            else:
                perf_ca = Decimal("0")

            weight_volume = Decimal("0.5")
            weight_ca = Decimal("0.5")

            score_global = (
                (perf_volume * weight_volume)
                + (perf_ca * weight_ca)
            )

            stations_resume.append({
                "station_id": sid,
                "station_nom": station.nom,
                "volume_total_reel": volume_reel,
                "volume_total_cible": volume_cible,
                "performance_volume_percent": round(perf_volume, 2),
                "ca_total_reel": ca_reel,
                "ca_total_cible": ca_cible,
                "performance_ca_percent": round(perf_ca, 2),
                "score_global": round(score_global, 2),
            })

        stations_resume_sorted = sorted(
            stations_resume,
            key=lambda x: x["score_global"],
            reverse=True
        )

        top_5 = stations_resume_sorted[:5]
        bottom_5 = stations_resume_sorted[-5:]

        stations_avec_transactions = recettes.values_list(
            "station_id", flat=True
        ).distinct()

        stations_sans_activite = stations_qs.exclude(
            id__in=stations_avec_transactions
        ).values("id", "nom")

        return Response({
            "totals": {
                "total": total_stations,
                "active": active_stations,
                "inactive": inactive_stations,
                "total_recettes": totals["total_recettes"],
                "total_depenses": totals["total_depenses"],
                "solde": totals["total_recettes"] - totals["total_depenses"],
                "volume_total": totals["volume_total"],
            },
            "volume_par_produit": volume_par_produit,
            "stations_resume": stations_resume,
            "top_5": top_5,
            "bottom_5": bottom_5,
            "stations_sans_activite": list(stations_sans_activite),
            "by_region": list(by_region),
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


class ObjectifStationViewSet(ModelViewSet):
    queryset = ObjectifStation.objects.all()
    serializer_class = ObjectifStationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        qs = ObjectifStation.objects.filter(
            tenant=user.tenant
        ).order_by("produit__code")

        station = self.request.query_params.get("station")
        annee = self.request.query_params.get("annee")
        mois = self.request.query_params.get("mois")

        print("ANNEE:", annee, type(annee))
        print("MOIS:", mois, type(mois))

        if station:
            qs = qs.filter(station_id=station)

        if annee:
            qs = qs.filter(annee=annee)

        if mois:
            qs = qs.filter(mois=mois)

        return qs

    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.user.tenant
        )