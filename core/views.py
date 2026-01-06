from rest_framework import viewsets, permissions, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.db import transaction
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from django.db.models import Sum, Q, Value

from accounts.permissions import CanManageUsers

from .permissions import (
    IsAdminTenantFinanceOnly,
    IsSameTenantOrSuper,
)

from .models import Tenant, Membre, Projet, Transaction, Cotisation, FileUpload
from .serializers import (
    TenantSerializer, MembreSerializer, ProjetSerializer, MeSerializer,
    TransactionSerializer, CotisationSerializer, FileUploadSerializer,
    UtilisateurSerializer, LoginSerializer, MyTokenObtainPairSerializer
)
from . import models

from rest_framework.filters import SearchFilter, OrderingFilter
from django.db.models.functions import TruncMonth, Concat, Coalesce
from core.pagination import StandardResultsSetPagination
from accounts.constants import UserRole

User = get_user_model()

class TenantViewSet(viewsets.ModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    permission_classes = []

    def get_permissions(self):
        return [permissions.IsAuthenticated()]

    def check_permissions(self, request):
        if not request.user or not request.user.is_authenticated:
            self.permission_denied(request, "Authentification requise")
        # IMPORTANT : ne rien appeler d’autre → DRF ne peut plus injecter ses permissions

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return Tenant.objects.all()

        if user.role in {
            UserRole.ADMIN_TENANT_FINANCE,
            UserRole.ADMIN_TENANT_STATION,
        }:
            return Tenant.objects.filter(id=user.tenant_id)

        return Tenant.objects.none()

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Seul le SuperAdmin peut créer un tenant.")
        serializer.save(created_by=self.request.user)


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


# -----------------------
# Membre ViewSet
# -----------------------
class MembreViewSet(viewsets.ModelViewSet):
    serializer_class = MembreSerializer
    permission_classes = [
        IsAuthenticated,
        IsAdminTenantFinanceOnly,
        IsSameTenantOrSuper,
    ]

    pagination_class = StandardResultsSetPagination
    filter_backends = [SearchFilter, OrderingFilter]

    search_fields = [
        "nom",
        "prenom",
        "telephone",
        "email",
    ]

    ordering_fields = ["id", "nom", "prenom", "created_at"]
    ordering = ["-id"]

    def get_queryset(self):
        user = self.request.user

        if getattr(user, "is_superuser", False):
            return Membre.objects.all()

        tenant = getattr(user, "tenant", None)
        if not tenant:
            return Membre.objects.none()

        return Membre.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        user = self.request.user
        if getattr(user, "is_superuser", False):
            serializer.save()
        else:
            serializer.save(tenant=user.tenant)


# -----------------------
# Projet ViewSet
# -----------------------
class ProjetViewSet(viewsets.ModelViewSet):
    serializer_class = ProjetSerializer
    permission_classes = [
        IsAuthenticated,
        IsSameTenantOrSuper,
        IsAdminTenantFinanceOnly,
    ]

    pagination_class = StandardResultsSetPagination
    filter_backends = [SearchFilter, OrderingFilter]

    # ⚠️ UNIQUEMENT des champs EXISTANTS
    search_fields = [
        "nom",
        "statut",
    ]

    ordering_fields = ["id", "nom", "budget"]
    ordering = ["-id"]

    def get_queryset(self):
        user = self.request.user

        if getattr(user, "is_superuser", False):
            return Projet.objects.all()

        tenant = getattr(user, "tenant", None)
        if not tenant:
            return Projet.objects.none()

        return Projet.objects.filter(tenant=tenant)

    def perform_create(self, serializer):
        user = self.request.user
        if getattr(user, "is_superuser", False):
            serializer.save()
        else:
            serializer.save(tenant=user.tenant)


# -----------------------
# Cotisation ViewSet
# -----------------------
class CotisationViewSet(viewsets.ModelViewSet):
    serializer_class = CotisationSerializer
    pagination_class = StandardResultsSetPagination

    permission_classes = [
        IsAuthenticated,
        IsSameTenantOrSuper,
        IsAdminTenantFinanceOnly,
    ]

    # 🔒 PAS DE SearchFilter
    filter_backends = [OrderingFilter]
    ordering_fields = ["date_paiement", "montant"]
    ordering = ["-date_paiement"]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            qs = Cotisation.objects.select_related("membre")
        else:
            tenant = getattr(user, "tenant", None)
            if not tenant:
                return Cotisation.objects.none()
            qs = Cotisation.objects.filter(
                tenant=tenant
            ).select_related("membre")

        # 🔍 Recherche maîtrisée (SAFE)
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(membre__nom_membre__icontains=search)
                | Q(periode__icontains=search)
                | Q(statut__icontains=search)
            )

        return qs
        

    @transaction.atomic
    def perform_create(self, serializer):
        user = self.request.user
        membre = serializer.validated_data.get("membre")

        if membre and not user.is_superuser:
            if membre.tenant != user.tenant:
                raise ValidationError(
                    "Le membre doit appartenir au même tenant."
                )

        serializer.save(
            tenant=user.tenant if not user.is_superuser else serializer.validated_data.get("tenant")
        )


# -----------------------
# Sync endpoint
# -----------------------
class SyncView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        user = request.user
        tenant = getattr(user, 'tenant', None)
        mappings = {"transactions": {}, "membres": {}, "cotisations": {}, "projets": {}}

        # Membres
        for item in request.data.get("membres", []):
            local_id = item.pop("local_id", None)
            if not getattr(user, 'is_superuser', False):
                item['tenant'] = tenant.id if tenant else None
            serializer = MembreSerializer(data=item, context={"request": request})
            serializer.is_valid(raise_exception=True)
            obj = serializer.save()
            mappings["membres"][local_id] = obj.id

        # Projets (optionnel si fourni)
        for item in request.data.get("projets", []):
            local_id = item.pop("local_id", None)
            if not getattr(user, 'is_superuser', False):
                item['tenant'] = tenant.id if tenant else None
            serializer = ProjetSerializer(data=item, context={"request": request})
            serializer.is_valid(raise_exception=True)
            obj = serializer.save()
            mappings["projets"][local_id] = obj.id

        # Transactions
        for item in request.data.get("transactions", []):
            local_id = item.pop("local_id", None)
            if not getattr(user, 'is_superuser', False):
                item['tenant'] = tenant.id if tenant else None
            proj_ref = item.get('projet')
            if isinstance(proj_ref, str) and proj_ref.startswith('local:'):
                local_proj_id = proj_ref.split(':', 1)[1]
                server_id = mappings.get('projets', {}).get(local_proj_id)
                if server_id:
                    item['projet'] = server_id
            serializer = TransactionSerializer(data=item, context={"request": request})
            serializer.is_valid(raise_exception=True)
            obj = serializer.save()
            mappings["transactions"][local_id] = obj.id

        # Cotisations
        for item in request.data.get("cotisations", []):
            local_id = item.pop("local_id", None)
            if not getattr(user, 'is_superuser', False):
                item['tenant'] = tenant.id if tenant else None
            mem_ref = item.get('membre')
            if isinstance(mem_ref, str) and mem_ref.startswith('local:'):
                local_mem_id = mem_ref.split(':', 1)[1]
                server_id = mappings.get('membres', {}).get(local_mem_id)
                if server_id:
                    item['membre'] = server_id
            serializer = CotisationSerializer(data=item, context={"request": request})
            serializer.is_valid(raise_exception=True)
            obj = serializer.save()
            mappings["cotisations"][local_id] = obj.id

        return Response({"mappings": mappings}, status=status.HTTP_201_CREATED)


# -----------------------
# FileUpload View
# -----------------------
class FileUploadView(viewsets.GenericViewSet):
    serializer_class = FileUploadSerializer
    permission_classes = [IsAuthenticated, IsSameTenantOrSuper]
    parser_classes = (MultiPartParser, FormParser)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        obj = serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


# -----------------------
# Me endpoint
# -----------------------
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UtilisateurSerializer(request.user, context={"request": request})
        return Response(serializer.data)


# -----------------------
# Login endpoint
# -----------------------
class LoginView(APIView):
    permission_classes = []
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        user_data = {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        }

        return Response({
            "access": access_token,
            "refresh": refresh_token,
            "user": user_data,
        }, status=status.HTTP_200_OK)


# -----------------------
# Utilisateur ViewSet
# -----------------------
class UtilisateurViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UtilisateurSerializer
    permission_classes = [IsAuthenticated, CanManageUsers]
    pagination_class = StandardResultsSetPagination

    filter_backends = [filters.SearchFilter]
    search_fields = ["email", "first_name", "last_name", "username"]

    def get_queryset(self):
        user = self.request.user

        if user.is_superuser:
            return User.objects.filter(
                role__in=[
                    UserRole.ADMIN_TENANT_FINANCE,
                    UserRole.ADMIN_TENANT_STATION,
                ]
            ).select_related("tenant").order_by("-id")

        if user.role == UserRole.ADMIN_TENANT_FINANCE:
            return User.objects.filter(
                tenant=user.tenant,
                role__in=[
                    UserRole.TRESORIER,
                    UserRole.LECTEUR,
                ]
            ).select_related("tenant").order_by("-id")

        if user.role == UserRole.ADMIN_TENANT_STATION:
            return User.objects.filter(
                tenant=user.tenant,
                role__in=[
                    UserRole.GERANT,
                    UserRole.COLLECTEUR,
                ]
            ).select_related("tenant", "station").order_by("-id")

        return User.objects.none()

    def perform_create(self, serializer):
        creator = self.request.user
        role_to_create = serializer.validated_data.get("role")

        if creator.is_superuser:
            serializer.save()
            return

        if creator.role == UserRole.ADMIN_TENANT_FINANCE:
            if role_to_create not in {
                UserRole.TRESORIER,
                UserRole.COLLECTEUR,
            }:
                raise PermissionDenied(
                    "Un Admin Finance ne peut créer que des Trésoriers ou Lecteurs."
                )
            serializer.save(tenant=creator.tenant)
            return

        if creator.role == UserRole.ADMIN_TENANT_STATION:
            if role_to_create not in {
                UserRole.GERANT,
                UserRole.SUPERVISEUR,
                UserRole.POMPISTE,
                UserRole.CAISSIER,
                UserRole.PERSONNEL_ENTRETIEN,
                UserRole.SECURITE,
            }:
                raise PermissionDenied(
                    "Un Admin Station ne peut créer que des Gérants, Superviseur, Pompiste, etc."
                )
            serializer.save(tenant=creator.tenant)
            return

        raise PermissionDenied("Action non autorisée.")
    
    @action(detail=True, methods=["post"], url_path="toggle-active")
    def toggle_active(self, request, pk=None):
        target = self.get_object()
        actor = request.user

        if actor.is_superuser:
            pass

        elif (
            actor.role == UserRole.ADMIN_TENANT_FINANCE
            and target.role in {UserRole.TRESORIER, UserRole.COLLECTEUR}
        ):
            pass

        elif (
            actor.role == UserRole.ADMIN_TENANT_STATION
            and target.role in {UserRole.GERANT, UserRole.SUPERVISEUR, UserRole.POMPISTE, UserRole.CAISSIER, UserRole.PERSONNEL_ENTRETIEN, UserRole.SECURITE}
        ):
            pass

        else:
            raise PermissionDenied("Action interdite.")

        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])

        return Response(
            {"id": target.id, "is_active": target.is_active},
            status=status.HTTP_200_OK,
        )
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def me(request):
    serializer = MeSerializer(request.user)
    return Response(serializer.data)

class StaffViewSet(TenantViewSet, viewsets.ModelViewSet):
    """
    Personnel STATION uniquement
    """
    serializer_class = UtilisateurSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        user = self.request.user

        if not user.tenant or user.role != UserRole.ADMIN_TENANT_STATION:
            return User.objects.none()

        return User.objects.filter(
            tenant=user.tenant,
            role__in=[
                UserRole.GERANT,
                UserRole.SUPERVISEUR,
                UserRole.POMPISTE,
                UserRole.CAISSIER,
                UserRole.PERSONNEL_ENTRETIEN,
                UserRole.SECURITE,
            ]
        ).order_by("role", "username")

    def perform_create(self, serializer):
        creator = self.request.user
        role_to_create = serializer.validated_data.get("role")

        if creator.is_superuser:
            serializer.save()
            return

        if creator.role == UserRole.ADMIN_TENANT_FINANCE:
            if role_to_create not in {
                UserRole.TRESORIER,
                UserRole.COLLECTEUR,
            }:
                raise PermissionDenied(
                    "Un Admin Finance ne peut créer que des Trésoriers ou Lecteurs."
                )
            serializer.save(tenant=creator.tenant)
            return

        if creator.role == UserRole.ADMIN_TENANT_STATION:
            if role_to_create not in {
                UserRole.GERANT,
                UserRole.SUPERVISEUR,
                UserRole.POMPISTE,
                UserRole.CAISSIER,
                UserRole.PERSONNEL_ENTRETIEN,
                UserRole.SECURITE,
            }:
                raise PermissionDenied(
                    "Un Admin Station ne peut créer que des Gérants, Superviseur, Pompiste, etc."
                )
            serializer.save(tenant=creator.tenant)
            return

        raise PermissionDenied("Action non autorisée.")

    def partial_update(self, request, *args, **kwargs):
        """
        Autorise UNIQUEMENT l’activation / désactivation
        """
        instance = self.get_object()

        # 🔒 Sécurité métier
        if instance.tenant != request.user.tenant:
            return Response(status=status.HTTP_403_FORBIDDEN)

        is_active = request.data.get("is_active", None)
        if is_active is None:
            return Response(
                {"detail": "Champ is_active requis"},
                status=status.HTTP_400_BAD_REQUEST
            )

        instance.is_active = bool(is_active)
        instance.save(update_fields=["is_active"])

        return Response(self.get_serializer(instance).data)


@action(detail=True, methods=["post"], url_path="toggle-active")
def toggle_active(self, request, pk=None):
    target = self.get_object()
    actor = request.user

    if actor.is_superuser:
        pass

    elif (
        actor.role == UserRole.ADMIN_TENANT_FINANCE
        and target.role in {UserRole.TRESORIER, UserRole.COLLECTEUR}
    ):
        pass

    elif (
        actor.role == UserRole.ADMIN_TENANT_STATION
        and target.role in {UserRole.GERANT, UserRole.SUPERVISEUR, UserRole.POMPISTE, UserRole.CAISSIER, UserRole.PERSONNEL_ENTRETIEN, UserRole.SECURITE}
    ):
        pass

    else:
        raise PermissionDenied("Action interdite.")

    target.is_active = not target.is_active
    target.save(update_fields=["is_active"])

    return Response(
        {"id": target.id, "is_active": target.is_active},
        status=status.HTTP_200_OK,
    )

class StaffViewSet(TenantViewSet, viewsets.ModelViewSet):
    """
    Personnel station uniquement :
    - Gérant
    - Collecteur
    """
    serializer_class = UtilisateurSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "patch"]

    def get_queryset(self):
        user = self.request.user

        if not user.tenant or user.role != UserRole.ADMIN_TENANT_STATION:
            return User.objects.none()

        return User.objects.filter(
            tenant=user.tenant,
            role__in=[
                UserRole.GERANT,
                UserRole.SUPERVISEUR,
                UserRole.POMPISTE,
                UserRole.CAISSIER,
                UserRole.PERSONNEL_ENTRETIEN,
                UserRole.SECURITE
            ]
        ).order_by("role", "username")


class TransactionViewSet(viewsets.ModelViewSet):
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination
    filter_backends = [SearchFilter, OrderingFilter]

    search_fields = [
        "reference",
        "categorie",
        "type",
        "projet__nom",
    ]

    ordering_fields = ["date", "montant"]
    ordering = ["-date"]

    def get_queryset(self):
        user = self.request.user
        tenant = getattr(user, "tenant", None)

        if tenant is None:
            return Transaction.objects.none()

        return Transaction.objects.filter(tenant=tenant)

    # /transactions/solde/
    @action(detail=False, methods=["get"])
    def solde(self, request):
        qs = self.get_queryset()

        recettes = (
            qs.filter(type="Recette")
            .aggregate(total=Sum("montant"))["total"]
            or 0
        )

        depenses = (
            qs.filter(type="Depense")
            .aggregate(total=Sum("montant"))["total"]
            or 0
        )

        return Response({"solde": recettes - depenses})

    # /transactions/stats/recettes-depenses/
    @action(detail=False, methods=["get"], url_path="stats/recettes-depenses")
    def stats_recettes_depenses(self, request):
        qs = self.get_queryset().annotate(
            mois_calcule=TruncMonth("date")
        )

        data = (
            qs.values("mois_calcule")
            .annotate(
                recettes=Sum("montant", filter=Q(type="Recette")),
                depenses=Sum("montant", filter=Q(type="Depense")),
            )
            .order_by("mois_calcule")
        )

        return Response([
            {
                "mois": d["mois_calcule"],
                "recettes": float(d["recettes"] or 0),
                "depenses": float(d["depenses"] or 0),
            }
            for d in data
        ])
