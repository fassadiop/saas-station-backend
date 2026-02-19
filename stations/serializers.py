from rest_framework import serializers
from django.db import transaction
from django.db.models import Q
from django.core.exceptions import ValidationError as DjangoValidationError

from accounts.models import Utilisateur
from .constants import REGIONS_DEPARTEMENTS
from .models import (
    Station,
    Pompe,
    IndexPompe,
    RelaisEquipe,
    RelaisProduit,
    FaitStatus,
)
from stations.models_depotage.cuve import Cuve, CuveStatus
from stations.models_produit import PrixCarburant, ProduitCarburant

# ============================================================
# GERANT – Serializer interne (création uniquement)
# ============================================================

class GerantCreateSerializer(serializers.Serializer):
    """
    Serializer interne pour la création du GERANT
    Utilisé uniquement lors de la création d'une station
    """
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    first_name = serializers.CharField(required=False, allow_blank=True)
    last_name = serializers.CharField(required=False, allow_blank=True)

    def validate_username(self, value):
        if Utilisateur.objects.filter(username=value).exists():
            raise serializers.ValidationError(
                "Ce nom d'utilisateur existe déjà."
            )
        return value


# ============================================================
# STATION
# ============================================================

class StationSerializer(serializers.ModelSerializer):
    """
    Création d'une station AVEC son GERANT obligatoire.
    La création effective du GERANT est gérée dans le ViewSet.
    """

    gerant = GerantCreateSerializer(write_only=True, required=True)

    class Meta:
        model = Station
        fields = "__all__"
        read_only_fields = ("tenant", "created_at")

    def validate(self, attrs):
        """
        Validation globale :
        - GERANT obligatoire à la création
        - Cohérence région / département
        """

        # 🔹 1. Validation GERANT (existant, conservé)
        if self.instance is None:
            if "gerant" not in attrs:
                raise serializers.ValidationError({
                    "gerant": "La création d’une station nécessite un GERANT."
                })

        # 🔹 2. Validation Région / Département
        region = attrs.get("region")
        departement = attrs.get("departement")

        if region:
            # Région inconnue
            if region not in REGIONS_DEPARTEMENTS:
                raise serializers.ValidationError({
                    "region": "Région invalide."
                })

            # Département présent mais incohérent
            if departement:
                allowed_departements = REGIONS_DEPARTEMENTS.get(region, [])
                if departement not in allowed_departements:
                    raise serializers.ValidationError({
                        "departement": (
                            f"Le département '{departement}' "
                            f"n'appartient pas à la région '{region}'."
                        )
                    })

        return attrs

# ============================================================
# CUVES
# ============================================================
class CuveSerializer(serializers.ModelSerializer):

    produit_code = serializers.CharField(
        source="produit.code",
        read_only=True
    )

    en_alerte = serializers.BooleanField(
        read_only=True
    )

    class Meta:
        model = Cuve
        fields = (
            "id",
            "tenant",
            "station",
            "reference",
            "produit",
            "produit_code",
            "capacite_max",
            "stock_actuel",
            "seuil_alerte",
            "statut",
            "en_alerte",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "tenant",
            "stock_actuel",
            "statut",
            "created_at",
            "updated_at",
        )

    # ==========================================================
    # VALIDATION GLOBALE
    # ==========================================================
    def validate(self, data):

        request = self.context["request"]
        user = request.user

        produit = data.get("produit")

        if not produit:
            raise serializers.ValidationError(
                {"produit": "Produit obligatoire."}
            )

        # 🔒 Produit doit appartenir au tenant
        if produit.tenant != user.tenant:
            raise serializers.ValidationError(
                {"produit": "Produit invalide pour ce tenant."}
            )
        
        station = data.get("station")

        if not station:
            raise serializers.ValidationError(
                {"station": "Station obligatoire."}
            )

        if station.tenant != user.tenant:
            raise serializers.ValidationError(
                {"station": "Station invalide pour ce tenant."}
            )

        # 🔒 Vérifier capacité cohérente
        capacite = data.get("capacite_max")
        if capacite is not None and capacite <= 0:
            raise serializers.ValidationError(
                {"capacite_max": "La capacité doit être > 0."}
            )

        return data

    # ==========================================================
    # CREATE
    # ==========================================================
    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        station = validated_data.get("station")

        if not station:
            raise serializers.ValidationError(
                {"station": "Station obligatoire."}
            )

        return Cuve.objects.create(
            tenant=user.tenant,
            statut=CuveStatus.STANDBY,
            stock_actuel=0,
            **validated_data
        )

    # ==========================================================
    # UPDATE
    # ==========================================================
    def update(self, instance, validated_data):

        # 🔒 Interdire modification directe du stock
        if "stock_actuel" in validated_data:
            raise serializers.ValidationError(
                {"stock_actuel": "Le stock est géré par les mouvements."}
            )

        # 🔒 Interdire modification directe du statut
        if "statut" in validated_data:
            raise serializers.ValidationError(
                {"statut": "Utilisez l’action changer_statut."}
            )

        return super().update(instance, validated_data)
    
    def validate_reference(self, value):
        if not value.strip():
            raise serializers.ValidationError(
                "La référence est obligatoire."
            )
        return value

# ==========================================================
# PRODUIT CARBURANT
# ==========================================================
class ProduitCarburantSerializer(serializers.ModelSerializer):

    stock_global = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = ProduitCarburant
        fields = (
            "id",
            "nom",
            "code",
            "seuil_critique_percent",
            "stock_global",
            "actif",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def validate(self, data):
        request = self.context["request"]
        user = request.user

        code = data.get("code")

        if code:
            exists = ProduitCarburant.objects.filter(
                tenant=user.tenant,
                code__iexact=code
            )

            if self.instance:
                exists = exists.exclude(id=self.instance.id)

            if exists.exists():
                raise serializers.ValidationError(
                    {"code": "Un produit avec ce code existe déjà."}
                )

        seuil = data.get("seuil_critique_percent")
        if seuil is not None:
            if seuil <= 0 or seuil > 100:
                raise serializers.ValidationError(
                    {"seuil_critique_percent": "Doit être entre 1 et 100."}
                )

        return data

    def create(self, validated_data):
        request = self.context["request"]

        return ProduitCarburant.objects.create(
            tenant=request.user.tenant,
            **validated_data
        )


# ============================================================
# INEX POMPE
# ============================================================

class IndexPompeReadSerializer(serializers.ModelSerializer):

    produit_code = serializers.CharField(
        source="produit.code",
        read_only=True
    )

    class Meta:
        model = IndexPompe
        fields = [
            "id",
            "pompe",
            "produit",
            "produit_code",
            "face",
            "index_initial",
            "index_courant",
            "actif",
        ]


class IndexPompeWriteSerializer(serializers.ModelSerializer):

    class Meta:
        model = IndexPompe
        fields = [
            "pompe",
            "produit",
            "face",
            "index_initial",
            "index_courant",
            "actif",
        ]

    def validate(self, data):
        pompe = data["pompe"]
        produit = data["produit"]
        face = data.get("face", "A")

        # 🔒 1️⃣ Max 2 index par pompe
        if self.instance is None:  # création
            if IndexPompe.objects.filter(pompe=pompe).count() >= 2:
                raise serializers.ValidationError(
                    "Cette pompe a déjà deux index configurés."
                )

        # 🔒 2️⃣ Pas de doublon produit + face
        qs = IndexPompe.objects.filter(
            pompe=pompe,
            produit=produit,
            face=face
        )

        if self.instance:
            qs = qs.exclude(pk=self.instance.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "Un index existe déjà pour ce produit et cette face."
            )

        return data

# ============================================================
# POMPE
# ============================================================
class PompeSerializer(serializers.ModelSerializer):
    station_id = serializers.PrimaryKeyRelatedField(
        queryset=Station.objects.all(),
        source="station",
        write_only=True
    )

    index_pompes = IndexPompeReadSerializer(many=True, read_only=True)

    class Meta:
        model = Pompe
        fields = [
            "id",
            "station",
            "station_id",
            "reference",
            "actif",
            "index_pompes",
        ]
        read_only_fields = ["id", "station", "index_pompes"]

    def create(self, validated_data):
        return Pompe.objects.create(**validated_data)

# ============================================================
# POMPE ACTIVE
# ============================================================
class IndexPompeActiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndexPompe
        fields = [
            "id",
            "produit",
            "face",
            "index_courant",
        ]


class PompeActiveSerializer(serializers.ModelSerializer):
    index_pompes = IndexPompeActiveSerializer(many=True)

    class Meta:
        model = Pompe
        fields = [
            "id",
            "reference",
            "type_pompe",
            "index_pompes",
        ]

# ============================================================
# RELAIS D’ÉQUIPE
# ============================================================

class RelaisEquipeSerializer(serializers.ModelSerializer):
    volume_total_vendu = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    volumes_par_carburant = serializers.SerializerMethodField()

    total_theorique = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True
    )

    ecart_caisse = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True
    )

    class Meta:
        model = RelaisEquipe
        fields = "__all__"

    def get_volumes_par_carburant(self, obj):
        return obj.volumes_par_carburant
    
    class Meta:
        model = RelaisEquipe
        fields = [
            "id",
            "debut_relais",
            "fin_relais",
            "equipe_sortante",
            "equipe_entrante",
            "status",
            "created_at",
            "total_theorique",
            "ecart_caisse",

        ]
        read_only_fields = (
            "status",
            "created_at",
        )

    def validate(self, data):
        debut = data.get("debut_relais")
        fin = data.get("fin_relais")

        if debut and fin and fin <= debut:
            raise serializers.ValidationError(
                "La fin du relais doit être postérieure au début."
            )
        return data

    def create(self, validated_data):
        request = self.context["request"]
        user = request.user

        validated_data.update({
            "station": user.station,
            "tenant": user.tenant,
            "created_by": user,
            "status": "BROUILLON",
        })

        return RelaisEquipe.objects.create(**validated_data)

    
    
class RelaisEquipeListSerializer(serializers.ModelSerializer):
    class Meta:
        model = RelaisEquipe
        fields = (
            "id",
            "debut_relais",
            "fin_relais",
            "equipe_sortante",
            "equipe_entrante",
            "total_encaisse",
            "volume_essence_vendu",
            "volume_gasoil_vendu",
            "status",
            "created_at",
        )


class RelaisProduitSerializer(serializers.ModelSerializer):

    volume_vendu = serializers.ReadOnlyField()

    class Meta:
        model = RelaisProduit
        fields = (
            "id",
            "produit",
            "index_debut",
            "index_fin",
            "volume_vendu",
        )



class RelaisEquipeSerializer(serializers.ModelSerializer):

    produits = RelaisProduitSerializer(many=True)

    total_volume_vendu = serializers.ReadOnlyField()
    total_encaisse = serializers.ReadOnlyField()

    class Meta:
        model = RelaisEquipe
        fields = "__all__"
        read_only_fields = (
            "tenant",
            "station",
            "status",
            "created_by",
            "created_at",
            "stock_applique",
        )

    # ==========================
    # VALIDATION MÉTIER
    # ==========================
    def validate(self, data):

        user = self.context["request"].user

        debut = data.get("debut_relais")
        fin = data.get("fin_relais")

        if debut and fin and fin <= debut:
            raise serializers.ValidationError(
                "La fin du relais doit être postérieure au début."
            )

        # 🔒 Anti chevauchement
        if debut and fin:

            conflit = RelaisEquipe.objects.filter(
                station=user.station
            ).filter(
                Q(debut_relais__lt=fin) &
                Q(fin_relais__gt=debut)
            )

            if self.instance:
                conflit = conflit.exclude(pk=self.instance.pk)

            if conflit.exists():
                raise serializers.ValidationError(
                    "Un relais existe déjà sur cette période."
                )

        # 🔒 Produits obligatoires
        produits = self.initial_data.get("produits", [])

        if not produits:
            raise serializers.ValidationError(
                "Un relais doit contenir au moins un produit."
            )

        produits_ids = [p.get("produit") for p in produits]
        if len(produits_ids) != len(set(produits_ids)):
            raise serializers.ValidationError(
                "Un produit ne peut apparaître qu'une seule fois."
            )

        return data

    # ==========================
    # CREATE ATOMIC
    # ==========================
    def create(self, validated_data):

        produits_data = validated_data.pop("produits")

        user = self.context["request"].user

        with transaction.atomic():

            relais = RelaisEquipe.objects.create(
                **validated_data,
                station=user.station,
                tenant=user.tenant,
                created_by=user,
                status=FaitStatus.BROUILLON,
            )

            instances = []

            for produit_data in produits_data:

                produit = produit_data["produit"]

                if produit.tenant_id != user.tenant_id:
                    raise serializers.ValidationError(
                        "Produit incompatible avec le tenant."
                    )

                instance = RelaisProduit(
                    relais=relais,
                    **produit_data
                )

                instance.full_clean()
                instances.append(instance)

            RelaisProduit.objects.bulk_create(instances)

        return relais

    # ==========================
    # UPDATE SÉCURISÉ
    # ==========================
    def update(self, instance, validated_data):

        if instance.stock_applique:
            raise serializers.ValidationError(
                "Impossible de modifier un relais dont le stock a été appliqué."
            )

        return super().update(instance, validated_data)
    

class RelaisEquipeListSerializer(serializers.ModelSerializer):

    total_volume_vendu = serializers.ReadOnlyField()
    total_encaisse = serializers.ReadOnlyField()

    class Meta:
        model = RelaisEquipe
        fields = (
            "id",
            "debut_relais",
            "fin_relais",
            "equipe_sortante",
            "equipe_entrante",
            "total_volume_vendu",
            "total_encaisse",
            "status",
            "created_at",
        )


class PrixCarburantSerializer(serializers.ModelSerializer):

    produit_code = serializers.CharField(
        source="produit.code",
        read_only=True
    )

    class Meta:
        model = PrixCarburant
        fields = [
            "id",
            "station",
            "produit",
            "produit_code",
            "prix_unitaire",
            "date_debut",
            "date_fin",
            "actif",
        ]
        read_only_fields = [
            "date_debut",
            "date_fin",
            "actif",
        ]