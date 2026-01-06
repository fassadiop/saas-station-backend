from rest_framework import serializers
from .models import (
    JustificationDepotage,
    Station,
    VenteCarburant,
    Local,
    ContratLocation,
    RelaisEquipe,
    FaitStatus,
)
from accounts.models import Utilisateur

from .constants import REGIONS_DEPARTEMENTS
from rest_framework import serializers


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
# VENTES CARBURANT
# ============================================================

class VenteCarburantSerializer(serializers.ModelSerializer):
    class Meta:
        model = VenteCarburant
        fields = "__all__"
        read_only_fields = (
            "tenant",
            "created_by",
            "status",
            "soumis_par",
            "soumis_le",
            "valide_par",
            "valide_le",
        )

    def update(self, instance, validated_data):
        if instance.status != FaitStatus.BROUILLON:
            raise serializers.ValidationError(
                "Cette vente ne peut plus être modifiée."
            )
        return super().update(instance, validated_data)


# ============================================================
# LOCAUX
# ============================================================

class LocalSerializer(serializers.ModelSerializer):
    class Meta:
        model = Local
        fields = "__all__"
        read_only_fields = ("tenant",)


# ============================================================
# CONTRATS DE LOCATION
# ============================================================

class ContratLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContratLocation
        fields = "__all__"
        read_only_fields = ("tenant",)


# ============================================================
# RELAIS D’ÉQUIPE
# ============================================================

class RelaisEquipeSerializer(serializers.ModelSerializer):
    volume_essence_vendu = serializers.ReadOnlyField()
    volume_gasoil_vendu = serializers.ReadOnlyField()
    total_encaisse = serializers.ReadOnlyField()
    variation_cuve_essence = serializers.ReadOnlyField()
    variation_cuve_gasoil = serializers.ReadOnlyField()

    class Meta:
        model = RelaisEquipe
        fields = "__all__"
        read_only_fields = (
            "tenant",
            "station",
            "status",
            "created_by",
            "soumis_par",
            "valide_par",
            "created_at",
            "soumis_le",
            "valide_le",
        )
        extra_kwargs = {
            "equipe_sortante": {"required": False, "allow_null": True},
            "equipe_entrante": {"required": False, "allow_null": True},
            "index_essence_debut": {"required": False, "allow_null": True},
            "index_essence_fin": {"required": False, "allow_null": True},
            "index_gasoil_debut": {"required": False, "allow_null": True},
            "index_gasoil_fin": {"required": False, "allow_null": True},
        }

    def validate(self, data):
        debut = data.get("debut_relais")
        fin = data.get("fin_relais")

        if debut and fin and fin <= debut:
            raise serializers.ValidationError(
                "La fin du relais doit être postérieure au début."
            )

        return data

    def create(self, validated_data):
        user = self.context["request"].user

        validated_data["station"] = user.station
        validated_data["tenant"] = user.tenant
        validated_data["created_by"] = user
        validated_data["status"] = "BROUILLON"

        return super().create(validated_data)
    
    
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

class JustificationDepotageSerializer(serializers.ModelSerializer):
    class Meta:
        model = JustificationDepotage
        fields = "__all__"
        read_only_fields = ("justifie_par", "created_at")
