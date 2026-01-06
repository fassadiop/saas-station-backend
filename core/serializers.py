# core/serializers.py
from rest_framework import serializers
from django.contrib.auth import authenticate, get_user_model

from accounts.models import Utilisateur
from stations.models import Station
from .models import Transaction, Membre, Projet, Cotisation, Tenant, FileUpload
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from accounts.constants import UserRole

from core.models import Tenant

User = get_user_model()

# -----------------------
# Me serializer
# -----------------------
class MeSerializer(serializers.ModelSerializer):
    """
    Serializer léger pour l'endpoint /auth/me/ (ou /api/v1/me/).
    Expose is_superuser/is_staff et les infos de base utilisées par le front.
    """
    class Meta:
        model = Utilisateur
        fields = (
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "is_superuser",
            "is_staff",
            "role", 
            "module",
            "tenant",
        )


# -----------------------
# Tenant serializer
# -----------------------
class TenantSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.id", read_only=True)

    class Meta:
        model = Tenant
        fields = ['id', 'nom', 'type_structure', 'date_creation', 'devise', 'actif', 'created_by']
        read_only_fields = ['id', 'date_creation', 'created_by']


class TenantMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tenant
        fields = ("id", "nom", "type_structure", "devise")


class UtilisateurSerializer(serializers.ModelSerializer):
    # 🔹 Tenant (lecture + écriture indirecte)
    tenant = TenantMiniSerializer(read_only=True)
    tenant_id = serializers.PrimaryKeyRelatedField(
        source="tenant",
        queryset=Tenant.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )

    # 🔹 Station (clé métier)
    station = serializers.PrimaryKeyRelatedField(
        queryset=Station.objects.all(),
        required=False,
        allow_null=True
    )

    # 🔹 Mot de passe
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True
    )

    class Meta:
        model = Utilisateur
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "role",
            "module",
            "tenant",
            "tenant_id",
            "station",
            "password",
            "is_active",
            "is_superuser",
            "is_staff",
        ]
        read_only_fields = ["id", "is_superuser", "is_staff"]

    # ------------------------------------------------------------------
    # VALIDATION MÉTIER PAR RÔLE (POINT CLÉ)
    # ------------------------------------------------------------------
    def validate(self, attrs):
        request = self.context.get("request")
        creator = getattr(request, "user", None)

        # Valeurs finales (création OU update)
        role = attrs.get("role") or getattr(self.instance, "role", None)
        tenant = attrs.get("tenant") or getattr(self.instance, "tenant", None)
        station = attrs.get("station") or getattr(self.instance, "station", None)

        # -------------------------------
        # SUPER ADMIN
        # -------------------------------
        if role == UserRole.SUPERADMIN:
            if not creator or not creator.is_superuser:
                raise serializers.ValidationError(
                    "Seul le SuperAdmin peut créer ou modifier un SuperAdmin."
                )
            attrs["tenant"] = None
            attrs["station"] = None

        # -------------------------------
        # ADMIN TENANT FINANCE
        # -------------------------------
        if role == UserRole.ADMIN_TENANT_FINANCE:
            if not creator or not creator.is_superuser:
                raise serializers.ValidationError(
                    "Seul le SuperAdmin peut créer un AdminTenantFinance."
                )
            if not tenant:
                raise serializers.ValidationError(
                    {"tenant": "Tenant obligatoire pour ce rôle."}
                )
            attrs["station"] = None

        # -------------------------------
        # ADMIN TENANT STATION
        # -------------------------------
        if role == UserRole.ADMIN_TENANT_STATION:
            if not creator or not creator.is_superuser:
                raise serializers.ValidationError(
                    "Seul le SuperAdmin peut créer un AdminTenantStation."
                )
            if not tenant:
                raise serializers.ValidationError(
                    {"tenant": "Tenant obligatoire pour ce rôle."}
                )
            attrs["station"] = None

        # ------------------------------------------------
        # UTILISATEURS STATION
        # ------------------------------------------------
        station_roles = (
            UserRole.GERANT,
            UserRole.SUPERVISEUR,
            UserRole.COLLECTEUR,
            UserRole.CAISSIER,
            UserRole.POMPISTE,
            UserRole.PERSONNEL_ENTRETIEN,
            UserRole.SECURITE,
        )

        if role in station_roles:
            if not tenant:
                raise serializers.ValidationError(
                    {"tenant": "Tenant obligatoire pour ce rôle."}
                )
            if not station:
                raise serializers.ValidationError(
                    {"station": "Station obligatoire pour ce rôle."}
                )

            # 🔐 Un AdminTenant crée uniquement dans son tenant
            if creator and creator.role == UserRole.ADMIN_TENANT_STATION:
                attrs["tenant"] = creator.tenant

        # ------------------------------------
        # RÔLES SANS STATION (FINANCE / LECTURE)
        # ------------------------------------
        finance_roles = ("Tresorier", "Lecteur")

        if role in finance_roles:
            attrs["station"] = None
            if creator and creator.role == UserRole.ADMIN_TENANT_FINANCE:
                attrs["tenant"] = creator.tenant

        return attrs

    # ------------------------------------------------------------------
    # CREATE
    # ------------------------------------------------------------------
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = Utilisateur(**validated_data)
        # 🔓 activation automatique (API interne)
        user.is_active = True
        if password:
            user.set_password(password)
        user.save()
        return user

    # ------------------------------------------------------------------
    # UPDATE
    # ------------------------------------------------------------------
    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        if password:
            instance.set_password(password)
        instance.save()
        return instance



# -----------------------
# Membre serializer
# -----------------------
class MembreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membre
        fields = ['id', 'tenant', 'nom_membre', 'contact', 'statut']
        read_only_fields = ['id', 'tenant']

    def create(self, validated_data):
        request = self.context.get('request')
        if request and not getattr(request.user, 'is_superuser', False):
            validated_data['tenant'] = request.user.tenant
        return super().create(validated_data)


# -----------------------
# Projet serializer
# -----------------------
class ProjetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Projet
        fields = ['id', 'tenant', 'nom', 'budget', 'statut']
        read_only_fields = ['id', 'tenant']

    def validate(self, data):
        request = self.context.get('request')
        user = request.user
        if not user.is_superuser:
            data['tenant'] = user.tenant
        return data

# -----------------------
# Transaction serializer
# -----------------------
class TransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transaction
        fields = [
            "id",
            "tenant",
            "projet",
            "type",
            "montant",
            "date",
            "mois",
            "categorie",
            "mode_paiement",
            "reference",
            "fichier_recu",
            "created_by",
        ]
        read_only_fields = ["id", "mois", "created_by", "tenant"]

    def create(self, validated_data):
        request = self.context.get("request")
        user = getattr(request, "user", None)
        validated_data["created_by"] = user
        validated_data["tenant"] = user.tenant  # sécurise : une transaction appartient AU TENANT du user connecté
        return super().create(validated_data)


class MembreMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membre
        fields = ["id", "nom_membre"]


# -----------------------
# Cotisation serializer
# -----------------------
class CotisationSerializer(serializers.ModelSerializer):
    membre_display = serializers.SerializerMethodField()

    class Meta:
        model = Cotisation
        fields = [
            "id",
            "membre",
            "membre_display",
            "montant",
            "date_paiement",
            "periode",
            "statut",
        ]

    def get_membre_display(self, obj):
        if obj.membre:
            return obj.membre.nom_membre
        return ""

    def validate(self, data):
        request = self.context.get('request')
        user = request.user

        if not user.is_superuser:
            data['tenant'] = user.tenant

        membre = data.get('membre')
        if membre and not user.is_superuser:
            if membre.tenant != user.tenant:
                raise serializers.ValidationError("Le membre doit appartenir au même tenant.")
        return data


# -----------------------
# FileUpload serializer
# -----------------------
class FileUploadSerializer(serializers.ModelSerializer):
    class Meta:
        model = FileUpload
        fields = ['id', 'tenant', 'transaction', 'uploaded_by', 'file', 'filename', 'content_type', 'size', 'created_at']
        read_only_fields = ['id', 'tenant', 'uploaded_by', 'filename', 'content_type', 'size', 'created_at']

    def create(self, validated_data):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and not getattr(user, 'is_superuser', False):
            tenant = getattr(user, 'tenant', None)
            if not tenant:
                raise serializers.ValidationError("Utilisateur non lié à un tenant.")
            validated_data['tenant'] = tenant
            validated_data['uploaded_by'] = user
        else:
            # pour superuser, si pas fourni on met uploaded_by à l'utilisateur courant (si présent)
            if user:
                validated_data.setdefault('uploaded_by', user)

        f = validated_data.get('file')
        if f:
            validated_data['content_type'] = getattr(f, 'content_type', '') or ''
            try:
                validated_data['size'] = f.size
            except Exception:
                validated_data.setdefault('size', None)
            validated_data['filename'] = getattr(f, 'name', '') or ''
        return super().create(validated_data)


# -----------------------
# LoginSerializer + Token custom
# -----------------------
class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get("email")
        password = data.get("password")

        # Essaie d’authentifier d'abord avec email comme username
        user = authenticate(username=email, password=password)
        if not user:
            try:
                user_obj = User.objects.get(email__iexact=email)
                user = authenticate(username=user_obj.get_username(), password=password)
            except User.DoesNotExist:
                user = None
        if not user:
            raise serializers.ValidationError("Identifiants invalides")
        if not user.is_active:
            raise serializers.ValidationError("Compte inactif")
        data["user"] = user
        return data


class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)

        token["email"] = user.email
        token["first_name"] = getattr(user, "first_name", "")
        token["last_name"] = getattr(user, "last_name", "")
        token["role"] = getattr(user, "role", "")

        # tenant_id doit toujours être STRING
        if getattr(user, "tenant", None):
            token["tenant_id"] = str(user.tenant.id)
        else:
            token["tenant_id"] = None

        return token

    def validate(self, attrs):
        data = super().validate(attrs)

        # renvoyer aussi le user dans la réponse
        data["user"] = {
            "id": self.user.id,
            "email": self.user.email,
            "username": self.user.username,
            "first_name": self.user.first_name or "",
            "last_name": self.user.last_name or "",
            "role": self.user.role,
            "tenant_id": str(self.user.tenant.id) if self.user.tenant else None,
        }

        return data
