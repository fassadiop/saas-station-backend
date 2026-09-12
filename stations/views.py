# saas-backend/stations/views.py

from django.http import HttpResponse
from rest_framework.viewsets import ReadOnlyModelViewSet
from accounts.constants import UserRole
from django.db.models import (
    F,
    Case,
    OuterRef,
    Subquery,
    Sum,
    Count,
    Q,
    Value,
    DecimalField,
    ExpressionWrapper,
    When,
)

from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from weasyprint import HTML

from stations.services.cloture_relais import generer_cloture_relais
from .notifications.services import create_notification
from datetime import datetime
from calendar import monthrange
from decimal import Decimal

from django.db import models

from rest_framework import viewsets, status
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Sum, Q
from django.db import transaction
from django.utils import timezone
from django.utils.timezone import now
from django.utils.dateparse import parse_datetime
from django.db.models.functions import TruncDate
from django_filters.rest_framework import DjangoFilterBackend

from rest_framework.viewsets import ModelViewSet
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.filters import SearchFilter, OrderingFilter
from rest_framework.decorators import action, api_view
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
from stations.services.stock import get_capacite_totale_produit, get_seuil_critique_reel, get_stock_exploitable_produit

from .models import (
    CategorieDepense,
    ClientStation,
    Depense,
    DetteStation,
    IndexPompe,
    Notification,
    Pompe,
    RelaisEcart,
    RemboursementEcart,
    Station,
    RelaisEquipe,
    FaitStatus,
    EncaissementRelais,
    RelaisIndex,
    Ilot,
    ModePaiement,
    Versement,
    VersementDetail,
    RelaisEcart,
)

from stations.models_objectif import ObjectifStation
from .serializers import (
    CategorieDepenseSerializer,
    ClientStationSerializer,
    CuveSerializer,
    DepenseSerializer,
    DetteStationSerializer,
    IndexPompeReadSerializer,
    IndexPompeWriteSerializer,
    NotificationSerializer,
    ObjectifStationSerializer,
    PompeActiveSerializer,
    PompeSerializer,
    PrixCarburantSerializer,
    ProduitCarburantSerializer,
    RelaisEcartSerializer,
    RemboursementEcartSerializer,
    StationSerializer,
    RelaisEquipeSerializer,
    EncaissementRelaisListSerializer,
    IlotSerializer,
    RelaisIlot,
    RelaisIlotSerializer,
    ModePaiementSerializer,
    VersementSerializer,
    ReglementDetteSerializer,
)
from .permissions import CanAccessStations, IsStationAdminOrActor
from stations.services.reglement_dette_service import regler_dette
from stations.services.cloture_journaliere import (
    generer_cloture_journaliere
)


class ClotureJournaliereView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        station_id = request.query_params.get("station_id")

        date_debut = request.query_params.get("date_debut")
        date_fin = request.query_params.get("date_fin")

        if not station_id:
            return Response(
                {"detail": "station_id requis"},
                status=400
            )

        station = Station.objects.get(
            pk=station_id
        )

        if date_debut:
            date_debut = datetime.strptime(
                date_debut,
                "%Y-%m-%d"
            ).date()

        if date_fin:
            date_fin = datetime.strptime(
                date_fin,
                "%Y-%m-%d"
            ).date()

        data = generer_cloture_journaliere(
            station,
            date_debut,
            date_fin
        )

        return Response(data)

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


class IlotViewSet(viewsets.ModelViewSet):

    serializer_class = IlotSerializer

    # --------------------------------------------
    # QUERYSET MULTI-TENANT STRICT
    # --------------------------------------------
    def get_queryset(self):
        user = self.request.user

        qs = (
            Ilot.objects
            .select_related("station", "tenant")
            .annotate(nb_pompes=Count("pompes"))
            .filter(tenant=user.tenant)
        )

        # Isolation par station si utilisateur lié à une station
        if not user.is_superuser and user.station:
            qs = qs.filter(station=user.station)

        # Filtres dynamiques (DataTable)
        station_id = (
            self.request.query_params.get("station_id")
            or self.request.query_params.get("station")
        )
        actif = self.request.query_params.get("actif")
        search = self.request.query_params.get("search")

        if station_id:
            qs = qs.filter(station_id=station_id)

        if actif is not None:
            qs = qs.filter(actif=actif.lower() == "true")

        if search:
            qs = qs.filter(
                Q(nom__icontains=search) |
                Q(station__nom__icontains=search)
            )

        return qs.order_by("nom")

    # --------------------------------------------
    # CREATE
    # --------------------------------------------
    def perform_create(self, serializer):
        user = self.request.user

        if not user.role in ["GERANT", "SUPERVISEUR"]:
            raise PermissionDenied("Permission insuffisante.")

        serializer.save(
            tenant=user.tenant,
            station=user.station
        )

    # --------------------------------------------
    # UPDATE
    # --------------------------------------------
    def perform_update(self, serializer):
        user = self.request.user

        if user.role not in ["GERANT", "SUPERVISEUR"]:
            raise PermissionDenied("Permission insuffisante.")

        serializer.save()

    # --------------------------------------------
    # DELETE INTERDIT (soft disable seulement)
    # --------------------------------------------
    def destroy(self, request, *args, **kwargs):
        return Response(
            {"detail": "Suppression interdite. Utilisez la désactivation."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )


class RelaisIlotViewSet(viewsets.ModelViewSet):

    serializer_class = RelaisIlotSerializer

    # ----------------------------------------
    # QUERYSET MULTI-TENANT
    # ----------------------------------------
    def get_queryset(self):
        user = self.request.user

        qs = (
            RelaisIlot.objects
            .select_related(
                "relais",
                "ilot",
                "responsable"
            )
            .prefetch_related(
                "indexes",
                "encaissements",
                "versements"
            )
            .filter(tenant=user.tenant)
        )

        if not user.is_superuser:
            qs = qs.filter(relais__station=user.station)

        return qs

    # ----------------------------------------
    # ACTION : SOUMETTRE
    # ----------------------------------------
    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):

        instance = self.get_object()

        try:
            instance.changer_statut(
                RelaisIlot.Statut.SOUMIS,
                request.user
            )
        except ValidationError as e:
            return Response(
                {"detail": str(e)},
                status=400
            )

        return Response({"statut": instance.statut})


    # ----------------------------------------
    # ACTION : VALIDER
    # ----------------------------------------
    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):

        instance = self.get_object()

        if request.user.role != UserRole.CHEF_STATION:
            raise PermissionDenied("Seul le chef station peut valider.")

        try:
            instance.changer_statut(
                RelaisIlot.Statut.VALIDE,
                request.user
            )
        except ValidationError as e:
            return Response(
                {"detail": str(e)},
                status=400
            )

        return Response({"statut": instance.statut})


    # ----------------------------------------
    # ACTION : REVENIR BROUILLON
    # ----------------------------------------
    @action(detail=True, methods=["post"])
    def revenir_brouillon(self, request, pk=None):

        instance = self.get_object()

        if instance.statut != RelaisIlot.Statut.VALIDE:
            return Response(
                {"detail": "Transition invalide."},
                status=400
            )

        if instance.relais.status == FaitStatus.TRANSFERE:
            return Response(
                {"detail": "Relais transféré."},
                status=400
            )

        instance.statut = RelaisIlot.Statut.BROUILLON
        instance.save()

        return Response({"statut": instance.statut})
    
    def update(self, request, *args, **kwargs):

        if "statut" in request.data:
            raise PermissionDenied(
                "Modification directe du statut interdite."
            )

        return super().update(request, *args, **kwargs)


    def partial_update(self, request, *args, **kwargs):

        if "statut" in request.data:
            raise PermissionDenied(
                "Modification directe du statut interdite."
            )

        return super().partial_update(request, *args, **kwargs)
    
    @action(detail=True, methods=["get"])
    def caisse(self, request, pk=None):

        relais_ilot = self.get_object()

        # Encaissements
        encaissements = (
            EncaissementRelais.objects
            .filter(relais_ilot=relais_ilot)
            .values("mode_paiement_id", "mode_paiement__nom")
            .annotate(total=Sum("montant"))
        )

        encaissement_map = {
            e["mode_paiement_id"]: e["total"]
            for e in encaissements
        }

        # Versements
        versements = (
            VersementDetail.objects
            .filter(versement__relais_ilot=relais_ilot)
            .values("mode_paiement_id")
            .annotate(total=Sum("montant"))
        )

        versement_map = {
            v["mode_paiement_id"]: v["total"]
            for v in versements
        }

        # Modes actifs
        modes = ModePaiement.objects.filter(
            tenant=request.user.tenant,
            actif=True
        )

        rows = []

        total_encaissement = 0
        total_versement = 0

        for mode in modes:

            enc = encaissement_map.get(mode.id, 0)
            ver = versement_map.get(mode.id, 0)

            rows.append({
                "mode_id": mode.id,
                "mode": mode.nom,
                "encaissement": enc,
                "versement": ver,
                "ecart": ver - enc
            })

            total_encaissement += enc
            total_versement += ver

        return Response({
            "relais_ilot": relais_ilot.id,
            "ilot": relais_ilot.ilot.nom,
            "responsable": relais_ilot.responsable.username,
            "modes": rows,
            "total_encaissement": total_encaissement,
            "total_versement": total_versement,
            "total_ecart": total_versement - total_encaissement
        })
    
    @action(detail=False, methods=["get"])
    def service(self, request):

        date_service = request.query_params.get("date")
        heure_service = request.query_params.get("heure")

        if not date_service or not heure_service:
            return Response(
                {"detail": "date et heure requis"},
                status=400
            )

        dt = parse_datetime(f"{date_service}T{heure_service}")

        relais = (
            RelaisEquipe.objects
            .filter(
                tenant=request.user.tenant,
                debut_relais__lte=dt,
                fin_relais__gte=dt
            )
            .first()
        )

        if not relais:
            return Response([])

        ilots = (
            RelaisIlot.objects
            .select_related("ilot", "responsable")
            .filter(relais=relais)
        )

        data = [
            {
                "id": r.id,
                "relais_id": relais.id,
                "ilot_nom": r.ilot.nom,
                "responsable": r.responsable.username
            }
            for r in ilots
        ]

        return Response(data)

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

    def perform_create(self, serializer):

        station = serializer.validated_data["station"]
        ilot = serializer.validated_data["ilot"]

        if ilot.station_id != station.id:
            raise ValidationError(
                "Cet îlot n'appartient pas à cette station"
            )

        serializer.save()
    

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

        base = RelaisEquipe.objects.all()

        qs = base.filter(tenant_id=user.tenant_id)

        if user.station_id:
            qs = qs.filter(station_id=user.station_id)

        return qs.order_by("-debut_relais")

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

        serializer.save(status=FaitStatus.BROUILLON)

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

            # ✅ NOTIFICATION
            create_notification(
                tenant_id=relais.tenant_id,
                station_id=relais.station_id,
                type="RELAIS_A_VALIDER",
                message=f"Relais #{relais.id} à valider",
                role_cible="SUPERVISEUR",
                lien=f"/dashboard/station/relais-index/{relais.id}"
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

        try:
            relais.changer_statut(
                nouveau_statut=relais.Statut.VALIDE,
                user=request.user
            )

            # ✅ NOTIFICATION
            create_notification(
                tenant_id=relais.tenant_id,
                station_id=relais.station_id,
                type="RELAIS_A_TRANSFERER",
                message=f"Relais #{relais.id} à transférer",
                role_cible="GERANT",
                lien=f"/dashboard/station/relais-index/{relais.id}"
            )

        except DjangoValidationError as e:
            raise ValidationError(e.messages)

        return Response({"status": "ok"})

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
            .prefetch_related("ilots__indexes")
            .order_by("-fin_relais")
            .first()
        )

        if not last_relais:
            return Response({
                "indexes": [],
                "equipe_sortante": None
            })

        indexes = []

        for ilot in last_relais.ilots.all():
            for idx in ilot.indexes.all():
                indexes.append({
                    "index_pompe": idx.index_pompe_id,
                    "dernier_index_fin": idx.index_fin,
                })

        return Response({
            "indexes": indexes,
            "equipe_sortante": last_relais.equipe_entrante
        })
    
    def update(self, request, *args, **kwargs):

        if "status" in request.data:
            raise PermissionDenied(
                "Modification directe du statut interdite."
            )

        return super().update(request, *args, **kwargs)


    def partial_update(self, request, *args, **kwargs):

        if "status" in request.data:
            raise PermissionDenied(
                "Modification directe du statut interdite."
            )

        return super().partial_update(request, *args, **kwargs)
    

    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        relais = self.get_object()

        if relais.status != relais.Statut.SOUMIS:
            raise ValidationError("Annulation impossible.")

        if request.user.role != "SUPERVISEUR":
            raise PermissionDenied()

        relais.status = relais.Statut.BROUILLON
        relais.save(bypass_validation=True)  # 🔥 clé

        return Response({"status": "brouillon"})


class AdminTenantStationDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if user.role != UserRole.ADMIN_TENANT_STATION:
            return Response({"detail": "Accès interdit"}, status=403)

        # ===============================
        # PARAMÈTRES MENSUELS (TZ SAFE)
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

        start_date = timezone.make_aware(
            datetime(annee, mois, 1)
        )

        if mois == 12:
            end_date = timezone.make_aware(
                datetime(annee + 1, 1, 1)
            )
        else:
            end_date = timezone.make_aware(
                datetime(annee, mois + 1, 1)
            )

        # ===============================
        # FILTRAGE STATIONS
        # ===============================

        station_id = request.query_params.get("station")

        stations_qs = Station.objects.filter(
            tenant=user.tenant
        )

        if station_id:
            stations_qs = stations_qs.filter(id=station_id)

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
        # VOLUME PAR PRODUIT (RELAIS)
        # ===============================

        volume_par_produit_qs = (
            RelaisIndex.objects.filter(
                relais_ilot__relais__station__tenant=user.tenant,
                relais_ilot__relais__station__in=stations_qs,
                relais_ilot__relais__status="TRANSFERE",
                relais_ilot__relais__stock_applique=True,
                relais_ilot__relais__fin_relais__gte=start_date,
                relais_ilot__relais__fin_relais__lt=end_date,
            )
            .values("index_pompe__produit__code")
            .annotate(
                volume=Coalesce(
                    Sum(
                        ExpressionWrapper(
                            Coalesce(F("index_fin"), Value(Decimal("0"))) -
                            Coalesce(F("index_debut"), Value(Decimal("0"))),
                            output_field=DecimalField()
                        )
                    ),
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
        # TRANSACTIONS (FINANCES)
        # ===============================

        transactions = TransactionStation.objects.filter(
            tenant=user.tenant,
            station__in=stations_qs,
            date__gte=start_date,
            date__lt=end_date,
        )

        recettes = transactions.filter(type="RECETTE")

        totals = transactions.aggregate(
            total_recettes=Coalesce(
                Sum("montant", filter=Q(type="RECETTE")),
                Decimal("0")
            ),
            total_depenses=Coalesce(
                Sum("montant", filter=Q(type="DEPENSE")),
                Decimal("0")
            ),
            volume_total=Coalesce(
                Sum("volume", filter=Q(type="RECETTE")),
                Decimal("0")
            ),
        )

        # ===============================
        # OBJECTIFS
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
                "volume_cible",
                "ca_cible"
            )
        )

        volume_cible_par_station = {}
        ca_cible_par_station = {}

        for o in objectifs_qs:
            sid = o["station_id"]

            volume_cible_par_station.setdefault(sid, Decimal("0"))
            volume_cible_par_station[sid] += o["volume_cible"]

            ca_cible_par_station.setdefault(sid, Decimal("0"))
            ca_cible_par_station[sid] += o["ca_cible"]

        # ===============================
        # SUBQUERY VOLUME RÉEL
        # ===============================

        volume_subquery = (
            RelaisIndex.objects
            .filter(
                relais_ilot__relais__station_id=OuterRef("id"),
                relais_ilot__relais__status="TRANSFERE",
                relais_ilot__relais__stock_applique=True,
                relais_ilot__relais__fin_relais__gte=start_date,
                relais_ilot__relais__fin_relais__lt=end_date,
            )
            .values("relais_ilot__relais__station_id")
            .annotate(
                total=Sum(
                    ExpressionWrapper(
                        Coalesce(F("index_fin"), Value(Decimal("0"))) -
                        Coalesce(F("index_debut"), Value(Decimal("0"))),
                        output_field=DecimalField()
                    )
                )
            )
            .values("total")[:1]
        )

        # ===============================
        # SUBQUERY CA RÉEL
        # ===============================

        ca_subquery = (
            TransactionStation.objects
            .filter(
                station_id=OuterRef("id"),
                tenant=user.tenant,
                type="RECETTE",
                date__gte=start_date,
                date__lt=end_date,
            )
            .values("station_id")
            .annotate(total=Sum("montant"))
            .values("total")[:1]
        )

        # ===============================
        # SUBQUERY OBJECTIFS
        # ===============================

        objectif_volume_subquery = (
            ObjectifStation.objects
            .filter(
                station_id=OuterRef("id"),
                tenant=user.tenant,
                annee=annee,
                mois=mois,
            )
            .values("station_id")
            .annotate(total=Sum("volume_cible"))
            .values("total")[:1]
        )

        objectif_ca_subquery = (
            ObjectifStation.objects
            .filter(
                station_id=OuterRef("id"),
                tenant=user.tenant,
                annee=annee,
                mois=mois,
            )
            .values("station_id")
            .annotate(total=Sum("ca_cible"))
            .values("total")[:1]
        )

        # ===============================
        # QUERY PRINCIPALE
        # ===============================

        stations_perf = (
            stations_qs
            .annotate(
                volume_reel=Coalesce(
                    Subquery(volume_subquery, output_field=DecimalField()),
                    Value(Decimal("0"))
                ),
                ca_reel=Coalesce(
                    Subquery(ca_subquery, output_field=DecimalField()),
                    Value(Decimal("0"))
                ),
                volume_cible=Coalesce(
                    Subquery(objectif_volume_subquery, output_field=DecimalField()),
                    Value(Decimal("0"))
                ),
                ca_cible=Coalesce(
                    Subquery(objectif_ca_subquery, output_field=DecimalField()),
                    Value(Decimal("0"))
                ),
            )
            .annotate(

                perf_volume=ExpressionWrapper(
                    Case(
                        When(volume_cible=0, then=Value(Decimal("0"))),
                        default=F("volume_reel") / F("volume_cible"),
                        output_field=DecimalField()
                    ),
                    output_field=DecimalField()
                ),
                perf_ca=ExpressionWrapper(
                    Case(
                        When(ca_cible=0, then=Value(Decimal("0"))),
                        default=F("ca_reel") / F("ca_cible"),
                        output_field=DecimalField()
                    ),
                    output_field=DecimalField()
                ),
            )
            .annotate(
                score_global=ExpressionWrapper(
                    (F("perf_volume") * Value(Decimal("0.5"))) +
                    (F("perf_ca") * Value(Decimal("0.5"))),
                    output_field=DecimalField()
                )
            )
            .values(
                "id",
                "nom",
                "volume_reel",
                "volume_cible",
                "ca_reel",
                "ca_cible",
                "perf_volume",
                "perf_ca",
                "score_global",
            )
            .order_by("-score_global")
        )

        stations_resume = [
            {
                "station_id": s["id"],
                "station_nom": s["nom"],
                "volume_total_reel": s["volume_reel"],
                "volume_total_cible": s["volume_cible"],
                "performance_volume_percent": round(s["perf_volume"], 2),
                "ca_total_reel": s["ca_reel"],
                "ca_total_cible": s["ca_cible"],
                "performance_ca_percent": round(s["perf_ca"], 2),
                "score_global": round(s["score_global"], 2),
            }
            for s in stations_perf
        ]

        stations_resume_sorted = sorted(
            stations_resume,
            key=lambda x: x["score_global"],
            reverse=True
        )

        return Response({
            "kpis": {
                "stations_total": total_stations,
                "stations_active": active_stations,
                "stations_inactive": inactive_stations,
                "ca_total": totals["total_recettes"],
                "depenses_total": totals["total_depenses"],
                "solde": totals["total_recettes"] - totals["total_depenses"],
            },

            "volumes": {
                "total": totals["volume_total"],
                "par_produit": volume_par_produit,
            },

            "performances": {
                "global": stations_resume_sorted,
                "top": stations_resume_sorted[:5],
                "bottom": stations_resume_sorted[-5:],
            },

            "distribution": {
                "par_region": list(by_region),
            }
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

            stock_global = get_stock_exploitable_produit(station, produit)
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


class ModePaiementViewSet(ModelViewSet):

    serializer_class = ModePaiementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        return ModePaiement.objects.filter(
            tenant=user.tenant
        )

    def perform_create(self, serializer):

        serializer.save(
            tenant=self.request.user.tenant
        )



class EncaissementRelaisViewSet(ReadOnlyModelViewSet):

    serializer_class = EncaissementRelaisListSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        qs = (
            EncaissementRelais.objects
            .select_related(
                "mode_paiement",
                "relais_ilot",
                "relais_ilot__ilot",
                "relais_ilot__relais",
                "relais_ilot__responsable",
            )
            .filter(tenant=user.tenant)
        )

        # restriction station pour acteurs
        if user.role != UserRole.ADMIN_TENANT_STATION:
            if user.station:
                qs = qs.filter(
                    relais_ilot__relais__station=user.station
                )

        station_id = self.request.query_params.get("station_id")

        if station_id:
            qs = qs.filter(
                relais_ilot__relais__station_id=station_id
            )

        # ==========================
        # FILTRES
        # ==========================

        relais = self.request.query_params.get("relais")
        ilot = self.request.query_params.get("ilot")
        mode = self.request.query_params.get("mode")
        responsable = self.request.query_params.get("responsable")

        if relais:
            qs = qs.filter(
                Q(relais_ilot__relais__equipe_sortante__icontains=relais) |
                Q(relais_ilot__relais__equipe_entrante__icontains=relais) |
                Q(relais_ilot__relais__id__icontains=relais)
            )

        if ilot:
            qs = qs.filter(
                relais_ilot__ilot__nom__icontains=ilot
            )

        if mode:
            qs = qs.filter(
                mode_paiement__nom__icontains=mode
            )

        if responsable:
            qs = qs.filter(
                relais_ilot__responsable__username__icontains=responsable
            )

        return qs.order_by("-date")


class VersementViewSet(ModelViewSet):

    serializer_class = VersementSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        qs = (
            Versement.objects
            .select_related(
                "relais_ilot",
                "relais_ilot__relais",
                "relais_ilot__ilot",
                "relais_ilot__responsable",
            )
            .filter(tenant=user.tenant)
        )

        if user.station:
            qs = qs.filter(
                relais_ilot__relais__station=user.station
            )

        # superviseur : voit tout
        if user.role in ["SUPERVISEUR", "GERANT"]:
            return qs.order_by("-date_versement")

        # responsable d'îlot : seulement ses versements
        qs = qs.filter(
            relais_ilot__responsable=user
        )
       

        return qs.order_by("-date_versement")

    # création
    # def perform_create(self, serializer):

    #     user = self.request.user
    #     relais_ilot = serializer.validated_data["relais_ilot"]

    #     # empêcher de créer un versement pour un autre îlot
    #     if user.role != "SUPERVISEUR":
    #         if relais_ilot.responsable != user:
    #             raise PermissionDenied(
    #                 "Vous ne pouvez saisir que votre versement."
    #             )

    #     serializer.save(
    #         tenant=user.tenant,
    #         created_by=user
    #     )

    # création
    def perform_create(self, serializer):

        user = self.request.user
        relais_ilot = serializer.validated_data["relais_ilot"]

        # ==================================================
        # 1. Vérifier le relais courant de la station
        # ==================================================

        relais_courant = (
            RelaisEquipe.objects
            .filter(
                tenant=user.tenant,
                station=user.station,
                status__in=[
                    RelaisEquipe.Statut.BROUILLON,
                    RelaisEquipe.Statut.SOUMIS,
                ],
            )
            .order_by("-debut_relais")
            .first()
        )

        if not relais_courant:
            raise ValidationError(
                "Impossible d'enregistrer le versement : "
                "aucun relais en cours de traitement pour cette station."
            )

        # ==================================================
        # 2. Vérifier que l'îlot appartient au relais courant
        # ==================================================

        if relais_ilot.relais_id != relais_courant.id:
            raise ValidationError(
                "Impossible d'enregistrer le versement : "
                "cet îlot n'appartient pas au relais courant."
            )

        # ==================================================
        # 3. Vérifier le responsable de l'îlot
        # ==================================================

        if user.role != "SUPERVISEUR":
            if relais_ilot.responsable != user:
                raise PermissionDenied(
                    "Vous ne pouvez saisir que votre versement."
                )

        # ==================================================
        # 4. Création
        # ==================================================

        serializer.save(
            tenant=user.tenant,
            created_by=user
        )

    # modification limitée
    def perform_update(self, serializer):

        user = self.request.user

        if user.role != "SUPERVISEUR":
            raise PermissionDenied(
                "Seul un superviseur peut modifier un versement."
            )

        serializer.save()


class DepenseViewSet(ModelViewSet):

    serializer_class = DepenseSerializer

    def get_queryset(self):

        user = self.request.user

        return Depense.objects.filter(
            tenant=self.request.user.tenant,
            station=user.station 
        ).select_related("categorie").order_by("-date_depense")

    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.user.tenant,
            station=self.request.user.station,
            created_by=self.request.user
        )

    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):

        depense = self.get_object()
        depense.valider(request.user)

        return Response({"status": "validée"})
    

class CategorieDepenseViewSet(ModelViewSet):

    serializer_class = CategorieDepenseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        return CategorieDepense.objects.filter(
            tenant=user.tenant,
            station=user.station
        )

    def perform_create(self, serializer):

        user = self.request.user

        serializer.save(
            tenant=user.tenant,
            station=user.station
        )


class DetteStationViewSet(viewsets.ModelViewSet):

    serializer_class = DetteStationSerializer

    def get_queryset(self):

        user = self.request.user

        qs = (
            DetteStation.objects
            .filter(
                tenant=user.tenant
            )
        )

        # Admin tenant → toutes les dettes
        if user.role != "ADMIN_TENANT_STATION":

            qs = qs.filter(
                station=user.station
            )

        return (
            qs
            .select_related(
                "client",
                "station",
                "produit"
            )
            .prefetch_related(
                "reglements__mode_paiement"
            )
        )

    def perform_create(self, serializer):

        user = self.request.user

        if user.role == "ADMIN_TENANT_STATION":
            raise PermissionDenied(
                "L'administrateur tenant ne peut pas créer de dettes."
            )

        relais = (
            RelaisEquipe.objects
            .filter(
                tenant=user.tenant,
                station=user.station,
                status__in=[
                    RelaisEquipe.Statut.BROUILLON,
                    RelaisEquipe.Statut.SOUMIS,
                ],
            )
            .order_by("-debut_relais")
            .first()
        )

        if not relais:
            raise ValidationError(
                "Impossible d'enregistrer une dette : "
                "aucun relais en cours de traitement pour cette station."
            )

        produit = serializer.validated_data["produit"]
        volume = serializer.validated_data["volume"]

        try:

            prix = PrixCarburant.objects.get(
                tenant=user.tenant,
                station=user.station,
                produit=produit,
                actif=True
            )

        except PrixCarburant.DoesNotExist:

            raise ValidationError(
                "Aucun prix actif défini pour ce produit."
            )

        prix_unitaire = prix.prix_unitaire

        montant = Decimal(volume) * Decimal(prix_unitaire)

        transaction = TransactionStation.objects.create(
            tenant=user.tenant,
            station=user.station,
            type="RECETTE",
            source_type="DETTE",
            source_id=0,  # temporaire
            montant=montant,
            volume=volume,
            date=timezone.now()
        )

        dette = serializer.save(
            tenant=user.tenant,
            station=user.station,
            relais=relais,
            transaction=transaction,
            produit=produit,
            prix_unitaire=prix_unitaire,
            montant_initial=montant,
            created_by=user
        )

        transaction.source_id = dette.id

        transaction.save(
            update_fields=["source_id"]
        )

    @action(detail=True, methods=["post"])
    def regler(self, request, pk=None):

        dette = self.get_object()

        serializer = ReglementDetteSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        reglement = regler_dette(
            dette=dette,
            montant=serializer.validated_data["montant"],
            mode_paiement=serializer.validated_data["mode_paiement"],
            user=request.user
        )

        return Response({
            "message": "Règlement enregistré",
            "montant": reglement.montant
        })

    @action(
        detail=False,
        methods=["get"],
        url_path="client/(?P<client_id>[^/.]+)"
    )
    def dettes_client(self, request, client_id=None):

        dettes = (
            self.get_queryset()
            .filter(client_id=client_id)
        )

        serializer = self.get_serializer(
            dettes,
            many=True
        )

        return Response(serializer.data)

    @action(
        detail=False,
        methods=["get"],
        url_path="dashboard"
    )
    def dashboard_dettes(self, request):

        user = request.user

        queryset = self.get_queryset()

        total_dette = queryset.aggregate(
            total=Coalesce(
                Sum(
                    F("montant_initial") - F("montant_regle"),
                    output_field=DecimalField()
                ),
                0
            )
        )["total"]

        nb_dettes = queryset.count()

        return Response({
            "total_dette": total_dette,
            "nombre_dettes": nb_dettes
        })
    

class ClientStationViewSet(viewsets.ModelViewSet):

    serializer_class = ClientStationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        if user.role == "ADMIN_TENANT_STATION":

            qs = (
                ClientStation.objects
                .filter(tenant=user.tenant)
                .order_by("nom")
            )

        else:

            qs = (
                ClientStation.objects
                .filter(tenant=user.tenant)
                .filter(
                    Q(station_limitee=user.station)
                    |
                    Q(station_limitee__isnull=True)
                )
                .order_by("nom")
            )

        search = (
            self.request.query_params
            .get("search", "")
            .strip()
        )

        if search:

            qs = qs.filter(
                Q(nom__icontains=search)
                |
                Q(telephone__icontains=search)
                |
                Q(cni__icontains=search)
                |
                Q(
                    registre_commerce__icontains=
                    search
                )
            )

        type_client = self.request.query_params.get(
            "type_client"
        )

        if type_client:
            qs = qs.filter(
                type_client=type_client
            )

        actif = self.request.query_params.get(
            "actif"
        )

        if actif in ["true", "false"]:

            qs = qs.filter(
                actif=(actif == "true")
            )

        agree = self.request.query_params.get(
            "agree"
        )

        if agree in ["true", "false"]:

            qs = qs.filter(
                agree_par_admin=
                (agree == "true")
            )

        return qs

    def perform_create(self, serializer):

        user = self.request.user

        if user.role != "ADMIN_TENANT_STATION":
            raise PermissionDenied(
                "Seul l'administrateur tenant peut créer un client."
            )

        serializer.save(
            tenant=user.tenant
        )

    def perform_update(self, serializer):

        user = self.request.user

        if user.role != "ADMIN_TENANT_STATION":
            raise PermissionDenied(
                "Seul l'administrateur tenant peut modifier un client."
            )

        serializer.save()

    @action(detail=True, methods=["post"])
    def approuver(self, request, pk=None):

        client = self.get_object()

        client.agree_par_admin = True
        client.save()

        return Response({
            "success": True
        })


    @action(detail=True, methods=["post"])
    def toggle_actif(self, request, pk=None):

        client = self.get_object()

        client.actif = not client.actif
        client.save()

        return Response({
            "success": True,
            "actif": client.actif
        })


@api_view(["GET"])
def list_notifications(request):
    user = request.user

    qs = Notification.objects.filter(
        station_id=user.station_id,
        role_cible=user.role,
        lu=False
    )

    return Response(NotificationSerializer(qs, many=True).data)


@api_view(["POST"])
def mark_as_read(request, pk):
    notif = Notification.objects.get(pk=pk)
    notif.lu = True
    notif.save()

    return Response({"ok": True})

class RelaisEcartViewSet(ReadOnlyModelViewSet):

    serializer_class = RelaisEcartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        qs = (
            RelaisEcart.objects
            .select_related(
                "relais",
                "relais_ilot",
                "relais_ilot__ilot",
                "responsable",
                "created_by",
            )
            .filter(
                tenant=user.tenant
            )
        )

        # --------------------------------------------------
        # Isolation station
        # --------------------------------------------------

        if (
            user.role != UserRole.ADMIN_TENANT_STATION
            and user.station
        ):
            qs = qs.filter(
                relais__station=user.station
            )

        # --------------------------------------------------
        # Filtres
        # --------------------------------------------------

        station_id = self.request.query_params.get("station")
        responsable_id = self.request.query_params.get("responsable")
        type_ecart = self.request.query_params.get("type")
        relais_id = self.request.query_params.get("relais")

        date_debut = self.request.query_params.get("date_debut")
        date_fin = self.request.query_params.get("date_fin")
        search = self.request.query_params.get("search")

        if station_id:
            qs = qs.filter(
                relais__station_id=station_id
            )

        responsable_id = self.request.query_params.get(
            "responsable"
        )

        print(
            "RESPONSABLE FILTRE =",
            responsable_id
        )

        if responsable_id:
            qs = qs.filter(
                responsable_id=responsable_id
            )

        print(
            "NB APRES FILTRE =",
            qs.count()
        )

        if type_ecart:
            qs = qs.filter(
                type_ecart=type_ecart
            )

        if relais_id:
            qs = qs.filter(
                relais_id=relais_id
            )

        if date_debut:
            qs = qs.filter(
                date_relais__gte=date_debut
            )

        if date_fin:
            qs = qs.filter(
                date_relais__lte=date_fin
            )

        if search:
            qs = qs.filter(
                Q(relais__id__icontains=search)
                | Q(relais_ilot__ilot__nom__icontains=search)
                | Q(responsable__first_name__icontains=search)
                | Q(responsable__last_name__icontains=search)
                | Q(type_ecart__icontains=search)
            )

        # --------------------------------------------------
        # Non soldés uniquement
        # --------------------------------------------------

        non_solde = self.request.query_params.get(
            "non_solde"
        )

        if non_solde == "true":

            qs = [
                ecart
                for ecart in qs
                if ecart.reste_a_rembourser > 0
            ]

        return qs
    
class RelaisEcartDashboardView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        qs = RelaisEcart.objects.filter(
            tenant=user.tenant
        )

        if (
            user.role != UserRole.ADMIN_TENANT_STATION
            and user.station
        ):
            qs = qs.filter(
                relais__station=user.station
            )

        total_manques = (
            qs.filter(
                type_ecart=RelaisEcart.TypeEcart.MANQUE
            )
            .aggregate(total=Sum("montant"))
            .get("total")
            or 0
        )

        total_excedents = (
            qs.filter(
                type_ecart=RelaisEcart.TypeEcart.EXCEDENT
            )
            .aggregate(total=Sum("montant"))
            .get("total")
            or 0
        )

        total_rembourse = sum(
            ecart.montant_rembourse
            for ecart in qs
            if ecart.type_ecart == RelaisEcart.TypeEcart.MANQUE
        )

        reste_a_recuperer = sum(
            ecart.reste_a_rembourser
            for ecart in qs
            if ecart.type_ecart == RelaisEcart.TypeEcart.MANQUE
        )

        return Response({
            "nombre_ecarts": qs.count(),
            "total_manques": total_manques,
            "total_excedents": total_excedents,
            "total_rembourse": total_rembourse,
            "reste_a_recuperer": reste_a_recuperer,
        })
    
class EcartSyntheseMensuelleView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        mois = request.query_params.get("mois")
        annee = request.query_params.get("annee")

        qs = RelaisEcart.objects.filter(
            tenant=user.tenant
        )

        if user.station:
            qs = qs.filter(
                relais__station=user.station
            )

        if mois:
            qs = qs.filter(
                date_relais__month=mois
            )

        if annee:
            qs = qs.filter(
                date_relais__year=annee
            )

        data = (
            qs.values(
                "responsable_id",
                "responsable__first_name",
                "responsable__last_name",
            )
            .annotate(
                nombre_ecarts=Count("id"),

                nombre_relais=Count(
                    "relais",
                    distinct=True
                ),

                total_manques=Coalesce(
                    Sum(
                        "montant",
                        filter=Q(
                            type_ecart=RelaisEcart.TypeEcart.MANQUE
                        )
                    ),
                    Value(0),
                    output_field=DecimalField()
                ),

                total_excedents=Coalesce(
                    Sum(
                        "montant",
                        filter=Q(
                            type_ecart=RelaisEcart.TypeEcart.EXCEDENT
                        )
                    ),
                    Value(0),
                    output_field=DecimalField()
                ),
            )
            .order_by(
                "-total_manques"
            )
        )

        resultats = []

        for item in data:

            responsable_id = item["responsable_id"]

            total_rembourse = (
                RemboursementEcart.objects.filter(
                    tenant=user.tenant,
                    responsable_id=responsable_id
                )
                .aggregate(
                    total=Coalesce(
                        Sum("montant"),
                        Value(0),
                        output_field=DecimalField()
                    )
                )["total"]
            )

            ecarts_responsable = (
                RelaisEcart.objects.filter(
                    tenant=user.tenant,
                    responsable_id=responsable_id,
                    type_ecart=RelaisEcart.TypeEcart.MANQUE
                )
            )

            reste = sum(
                ecart.reste_a_rembourser
                for ecart in ecarts_responsable
            )

            total_rembourse = sum(
                ecart.montant_rembourse
                for ecart in ecarts_responsable
            )

            if reste <= 0:
                continue

            resultats.append({
                "responsable_id": responsable_id,

                "responsable": (
                    f"{item['responsable__first_name']} "
                    f"{item['responsable__last_name']}"
                ).strip(),

                "nombre_relais": item["nombre_relais"],
                "nombre_ecarts": item["nombre_ecarts"],

                "total_manques": item["total_manques"],
                "total_excedents": item["total_excedents"],

                "solde": (
                    item["total_excedents"]
                    - item["total_manques"]
                ),

                "total_rembourse": total_rembourse,

                "reste_a_rembourser": reste,
            })

        return Response(resultats)
    
class RemboursementEcartViewSet(ModelViewSet):

    serializer_class = RemboursementEcartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):

        user = self.request.user

        queryset = (
            RemboursementEcart.objects
            .filter(
                tenant=user.tenant
            )
            .select_related(
                "ecart",
                "responsable",
                "created_by"
            )
            .order_by(
                "-date_remboursement",
                "-id"
            )
        )

        if hasattr(user, "station") and user.station:
            queryset = queryset.filter(
                ecart__relais__station=user.station
            )

        return queryset


class ClotureRelaisView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, relais_id):

        user = request.user

        queryset = RelaisEquipe.objects.all()

        # SUPERADMIN
        if user.role == UserRole.SUPERADMIN:
            pass

        # Admin tenant station
        elif user.role == UserRole.ADMIN_TENANT_STATION:
            queryset = queryset.filter(
                tenant=user.tenant
            )

        # Gérant / Superviseur / Pompiste / Caissier
        else:
            queryset = queryset.filter(
                tenant=user.tenant,
                station=user.station
            )

        relais = get_object_or_404(
            queryset,
            pk=relais_id
        )

        return Response(
            generer_cloture_relais(relais)
        )
    
class ClotureRelaisListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        queryset = RelaisEquipe.objects.filter(
            status=RelaisEquipe.Statut.TRANSFERE
        )

        if user.role == UserRole.SUPERADMIN:
            pass

        elif user.role == UserRole.ADMIN_TENANT_STATION:
            queryset = queryset.filter(
                tenant=user.tenant
            )

        else:
            queryset = queryset.filter(
                tenant=user.tenant,
                station=user.station
            )

        data = []

        for relais in queryset.order_by("-fin_relais"):

            data.append({
                "id": relais.id,
                "station": relais.station.nom,
                "debut_relais": relais.debut_relais,
                "fin_relais": relais.fin_relais,
                "equipe_sortante": relais.equipe_sortante,
                "equipe_entrante": relais.equipe_entrante,
                "statut": relais.status,
                "encaissements": float(
                    relais.total_encaisse
                ),
            })

        return Response(data)


class ClotureRelaisPdfView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, relais_id):

        relais = get_object_or_404(
            RelaisEquipe,
            pk=relais_id,
            station=request.user.station
        )

        data = generer_cloture_relais(relais)

        html = render_to_string(
            "pdf/cloture_relais.html",
            {
                "data": data,
            }
        )

        pdf = HTML(
            string=html,
            base_url=request.build_absolute_uri("/")
        ).write_pdf()

        response = HttpResponse(
            pdf,
            content_type="application/pdf"
        )

        response[
            "Content-Disposition"
        ] = (
            f'attachment; '
            f'filename="cloture-relais-{relais.id}.pdf"'
        )

        return response