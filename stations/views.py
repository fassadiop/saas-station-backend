# saas-backend/stations/views.py

from decimal import Decimal
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
    IndexPompe,
    Station,
    VenteCarburant,
    Local,
    ContratLocation,
    RelaisEquipe,
    FaitStatus,
)
from .serializers import (
    IndexPompeReadSerializer,
    IndexPompeWriteSerializer,
    StationSerializer,
    VenteCarburantSerializer,
    LocalSerializer,
    ContratLocationSerializer,
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


class PompeViewSet(ModelViewSet):
    serializer_class = PompeSerializer
    permission_classes = [IsAdminTenantStationForPompe]

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


class RelaisIndexV2ViewSet(viewsets.ModelViewSet):
    """
    Gestion des relais d’index (V2).
    Source de vérité unique pour les index par pompe.
    """

    serializer_class = RelaisIndexV2Serializer
    permission_classes = [
        IsAuthenticated,
        IsStationAdminOrActor,
        CanCreateRelaisIndexV2,
    ]

    # ----------------------
    # QUERYSET SÉCURISÉ
    # ----------------------
    def get_queryset(self):
        user = self.request.user

        qs = (
            RelaisIndexV2.objects
            .select_related("station")
            .prefetch_related(
                "lignes",
                "lignes__index_pompe",
                "lignes__index_pompe__pompe",
            )
        )

        if not user.is_superuser:
            qs = qs.filter(station=user.station)

        return qs.order_by("-debut_relais")

    # ----------------------
    # CREATE (ATOMIC)
    # ----------------------
    def create(self, request, *args, **kwargs):
        if request.user.role not in (
            UserRole.POMPISTE,
            UserRole.SUPERVISEUR,
        ):
            raise_business_error(
                code=ErrorCode.PERMISSION_DENIED,
                message="Vous n’êtes pas autorisé à créer un relais d’index",
                hint="Seuls les pompi stes et superviseurs peuvent effectuer cette action",
            )

        return super().create(request, *args, **kwargs)

    # ----------------------
    # SOUMISSION
    # ----------------------
    @action(detail=True, methods=["post"])
    def soumettre(self, request, pk=None):
        relais = self.get_object()

        if request.user.role not in (
            UserRole.POMPISTE,
            UserRole.SUPERVISEUR,
        ):
            raise_business_error(
                code=ErrorCode.PERMISSION_DENIED,
                message="Vous n’êtes pas autorisé à soumettre ce relais",
            )

        if relais.status != RelaisIndexV2.Status.BROUILLON:
            raise_business_error(
                code=ErrorCode.INVALID_STATE,
                field="status",
                message="Ce relais ne peut pas être soumis dans son état actuel",
                hint="Seuls les relais en brouillon peuvent être soumis",
            )

        relais.status = RelaisIndexV2.Status.SOUMIS
        relais.soumis_par = request.user
        relais.soumis_le = timezone.now()
        relais.save(update_fields=["status", "soumis_par", "soumis_le"])

        return Response(
            {
                "status": "SOUMIS",
                "message": "Relais soumis avec succès",
            },
            status=status.HTTP_200_OK,
        )

    # ----------------------
    # VALIDATION / TRANSFERT
    # ----------------------
    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):
        relais = self.get_object()

        if request.user.role != UserRole.SUPERVISEUR:
            raise_business_error(
                code=ErrorCode.PERMISSION_DENIED,
                message="Seul un superviseur peut valider un relais",
            )

        if relais.status != RelaisIndexV2.Status.SOUMIS:
            raise_business_error(
                code=ErrorCode.INVALID_STATE,
                field="status",
                message="Ce relais ne peut pas être validé",
                hint="Le relais doit être au statut SOUMIS",
            )

        # ======================
        # CONTRÔLE FINANCIER
        # ======================
        parametrage = ParametrageStation.objects.filter(
            tenant=relais.station.tenant
        ).first()

        if not parametrage:
            raise_business_error(
                code=ErrorCode.BUSINESS_RULE,
                message="Paramétrage financier introuvable pour la station",
                hint="Vérifiez le paramétrage de la station",
            )

        tolerance = parametrage.seuil_tolerance
        ecart = relais.ecart_encaissement or Decimal("0.00")

        if abs(ecart) > tolerance:
            raise_business_error(
                code=ErrorCode.BUSINESS_RULE,
                field="ecart_encaissement",
                message="Écart d’encaissement hors tolérance autorisée",
                hint=f"Tolérance max : {tolerance} | Écart constaté : {ecart}",
            )

        # ======================
        # TRANSFERT (ORDRE CRITIQUE)
        # ======================
        with transaction.atomic():

            appliquer_stock_relais_index_v2(
                relais=relais,
                user=request.user,
            )

            TransactionStation.objects.create(
                tenant=relais.station.tenant,
                station=relais.station,
                source_type="RELAIS_INDEX",
                source_id=relais.id,
                type="RECETTE",
                montant=relais.total_encaisse,
                date=relais.fin_relais,
                finance_status="TRANSFERE",
            )

            relais.status = RelaisIndexV2.Status.TRANSFERE
            relais.valide_par = request.user
            relais.valide_le = timezone.now()
            relais.save(update_fields=[
                "status",
                "valide_par",
                "valide_le",
                "stock_applique",
            ])

        return Response(
            {
                "status": "TRANSFERE",
                "message": "Relais validé et transféré avec succès",
            },
            status=status.HTTP_200_OK,
        )

    # ----------------------
    # DELETE (OPTIONNEL)
    # ----------------------
    @action(detail=True, methods=["delete"])
    def supprimer(self, request, pk=None):
        relais = self.get_object()

        STAFF_CAN_DELETE = ["SUPERVISEUR", "GERANT"]

        if request.user.role not in STAFF_CAN_DELETE:
            raise_business_error(
                code=ErrorCode.PERMISSION_DENIED,
                message="Vous n’êtes pas autorisé à supprimer ce relais",
            )

        if relais.status != RelaisIndexV2.Status.BROUILLON:
            raise_business_error(
                code=ErrorCode.INVALID_STATE,
                field="status",
                message="Seuls les relais en brouillon peuvent être supprimés",
            )

        if relais.finance_id:
            raise_business_error(
                code=ErrorCode.BUSINESS_RULE,
                message=(
                    "Impossible de supprimer un relais déjà lié "
                    "à une écriture financière"
                ),
            )

        relais.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)

    # ----------------------
    # ANNULER
    # ----------------------
    @action(detail=True, methods=["post"])
    def annuler(self, request, pk=None):
        relais = self.get_object()

        STAFF_CAN_ANNULER = ["SUPERVISEUR", "GERANT"]

        if request.user.role not in STAFF_CAN_ANNULER:
            raise_business_error(
                code=ErrorCode.PERMISSION_DENIED,
                message="Vous n’êtes pas autorisé à annuler ce relais",
            )

        if relais.status != RelaisIndexV2.Status.SOUMIS:
            raise_business_error(
                code=ErrorCode.INVALID_STATE,
                field="status",
                message="Seuls les relais soumis peuvent être annulés",
            )

        relais.status = RelaisIndexV2.Status.ANNULE
        relais.save(update_fields=["status"])

        return Response(
            {
                "status": "ANNULE",
                "message": "Relais annulé avec succès",
            },
            status=status.HTTP_200_OK,
        )

    # ----------------------
    # PREVIEW (INCHANGÉ)
    # ----------------------
    @action(detail=False, methods=["post"])
    def preview(self, request):
        """
        Calcul du montant total prévu (preview)
        sans création de relais en base.
        """

        lignes = request.data.get("lignes", [])

        if not isinstance(lignes, list) or not lignes:
            return Response({"montant_total_prevu": Decimal("0.00")})

        parametrage = ParametrageStation.objects.filter(
            tenant=request.user.station.tenant
        ).first()

        if not parametrage:
            return Response({"montant_total_prevu": Decimal("0.00")})

        total = Decimal("0.00")

        for ligne in lignes:
            index_debut = Decimal(str(ligne.get("index_debut", 0)))
            index_fin = Decimal(str(ligne.get("index_fin", 0)))

            if index_fin < index_debut:
                continue

            volume = index_fin - index_debut

            index_pompe = (
                IndexPompe.objects
                .select_related("pompe")
                .filter(
                    id=ligne.get("index_pompe"),
                    pompe__station=request.user.station,
                )
                .first()
            )

            if not index_pompe:
                continue

            carburant = index_pompe.carburant

            if carburant == "ESSENCE":
                total += volume * parametrage.prix_essence
            elif carburant == "GASOIL":
                total += volume * parametrage.prix_gasoil

        return Response({"montant_total_prevu": total})


class IndexPompeWithStartIndexView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        station = request.user.station

        # =====================================================
        # 1️⃣ ÉQUIPE SORTANTE (dernier relais index)
        # =====================================================
        last_relais = (
            RelaisIndexV2.objects
            .filter(station=station)
            .order_by("-fin_relais")
            .first()
        )

        equipe_sortante = (
            last_relais.equipe_entrante
            if last_relais
            else None
        )

        # =====================================================
        # 2️⃣ INDEX POMPES ACTIVES + INDEX_DEBUT CALCULÉ
        # =====================================================
        index_pompes = (
            IndexPompe.objects
            .filter(
                pompe__station=station,
                pompe__actif=True,
                actif=True,
            )
            .select_related("pompe")
        )

        lignes = []

        for index in index_pompes:
            last_ligne = (
                RelaisIndexLigneV2.objects
                .filter(index_pompe=index)
                .select_related("relais")
                .order_by("-relais__fin_relais")
                .first()
            )

            # 🔑 Règle métier :
            # - si relais précédent → index_fin
            # - sinon → index_courant (ou index_initial si tu préfères)
            index_debut = (
                last_ligne.index_fin
                if last_ligne
                else index.index_courant
            )

            lignes.append({
                "index_pompe_id": index.id,
                "pompe_reference": index.pompe.reference,
                "carburant": index.carburant,
                "face": index.face,
                "index_debut": index_debut,
                "index_courant": index.index_courant,
            })

        # =====================================================
        # 3️⃣ RÉPONSE UNIFIÉE
        # =====================================================
        return Response({
            "equipe_sortante": equipe_sortante,
            "lignes": lignes,
        })
    
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
            return Response({"detail": "Non autorisé"}, status=403)

        try:
            relais.changer_statut(RelaisStatus.SOUMIS, request.user)
        except ValidationError as e:
            return Response({"detail": str(e)}, status=400)

        return Response({"status": relais.status})

    # ======================
    # VALIDATION & FINANCES
    # ======================
    @action(detail=True, methods=["post"])
    def valider(self, request, pk=None):

        relais = self.get_object()

        if request.user.role != UserRole.SUPERVISEUR:
            return Response({"detail": "Non autorisé"}, status=403)

        try:
            relais.changer_statut(RelaisStatus.VALIDE, request.user)
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
            relais.changer_statut(RelaisStatus.TRANSFERE, request.user)
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

