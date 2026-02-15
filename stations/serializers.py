from rest_framework import serializers
from accounts.models import Utilisateur

from .constants import REGIONS_DEPARTEMENTS
from django.db import transaction
from django.core.exceptions import ValidationError
from django.db.models import Q
from decimal import Decimal
from rest_framework import serializers
from .models import (
    IndexPompe,
    JustificationDepotage,
    Pompe,
    Station,
    VenteCarburant,
    Local,
    ContratLocation,
    RelaisEquipe,
    FaitStatus,
)
from stations.models import ParametrageStation, RelaisEquipe, IndexPompe

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

class IndexPompeReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndexPompe
        fields = [
            "id",
            "pompe",
            "carburant",
            "face",
            "index_initial",
            "index_courant",
            "actif",
        ]
        read_only_fields = fields


class IndexPompeWriteSerializer(serializers.ModelSerializer):
    pompe_type = serializers.CharField(
        write_only=True,
        required=False
    )

    class Meta:
        model = IndexPompe
        fields = [
            "pompe",
            "pompe_type",
            "carburant",
            "face",
            "index_initial",
            "index_courant",
            "actif",
        ]

    def validate(self, data):
        pompe = data["pompe"]
        face = data.get("face", "A")

        # 🔒 RÈGLE MÉTIER CENTRALE
        if pompe.type_pompe == "MIXTE" and face != "A":
            raise serializers.ValidationError(
                "Les pompes mixtes ne peuvent avoir qu’une seule face (A)."
            )

        return data

    def update(self, instance, validated_data):
        validated_data.pop("pompe_type", None)
        validated_data.pop("face", None)
        return super().update(instance, validated_data)

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
            "type_pompe",
            "actif",
            "index_pompes",
        ]
        read_only_fields = ["id", "station", "index_pompes"]

    def create(self, validated_data):
        """
        Création d'une pompe + génération automatique
        des IndexPompe associés selon le type.
        """
        pompe = Pompe.objects.create(**validated_data)

        if pompe.type_pompe == "SIMPLE":
            IndexPompe.objects.create(
                pompe=pompe,
                carburant="ESSENCE",
                index_initial=0,
                index_courant=0,
            )

        elif pompe.type_pompe == "MIXTE":
            for carburant in ["ESSENCE", "GASOIL"]:
                IndexPompe.objects.create(
                    pompe=pompe,
                    carburant=carburant,
                    index_initial=0,
                    index_courant=0,
                )

        return pompe
    

# ============================================================
# POMPE ACTIVE
# ============================================================
class IndexPompeActiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = IndexPompe
        fields = [
            "id",
            "carburant",
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
    variation_cuve = serializers.ReadOnlyField()

    class Meta:
        model = RelaisProduit
        fields = (
            "id",
            "produit",
            "index_debut",
            "index_fin",
            "jauge_debut",
            "jauge_fin",
            "encaisse_ticket",
            "volume_vendu",
            "variation_cuve",
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
        )

    def validate(self, data):

        user = self.context["request"].user

        debut = data.get("debut_relais")
        fin = data.get("fin_relais")

        if debut and fin and fin <= debut:
            raise serializers.ValidationError(
                "La fin du relais doit être postérieure au début."
            )

        # 🔒 Vérification chevauchement
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

        # 🔒 Vérifie produits
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

    def create(self, validated_data):

        produits_data = validated_data.pop("produits")

        user = self.context["request"].user

        with transaction.atomic():

            relais = RelaisEquipe.objects.create(
                **validated_data,
                station=user.station,
                tenant=user.tenant,
                created_by=user,
                status="BROUILLON",
            )

            produits_instances = []

            for produit_data in produits_data:

                produit = produit_data["produit"]

                # 🔒 Sécurité multi-tenant
                if produit.tenant_id != user.tenant_id:
                    raise serializers.ValidationError(
                        "Produit incompatible avec le tenant."
                    )

                instance = RelaisProduit(
                    relais=relais,
                    **produit_data
                )

                # 🔒 Validation modèle
                instance.full_clean()

                produits_instances.append(instance)

            RelaisProduit.objects.bulk_create(produits_instances)

            return relais
    
    def update(self, instance, validated_data):

        if instance.stock_applique:
            raise serializers.ValidationError(
                "Impossible de modifier un relais dont le stock a été appliqué."
            )

        return super().update(instance, validated_data)
    
    def delete(self, *args, **kwargs):

        if self.stock_applique:
            raise ValidationError(
                "Impossible de supprimer un relais dont le stock a été appliqué."
            )

        super().delete(*args, **kwargs)
    
    
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


class ParametrageStationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParametrageStation
        fields = [
            "prix_essence",
            "prix_gasoil",
            "seuil_tolerance",
        ]

    def validate(self, data):
        if data.get("prix_essence", 0) <= 0:
            raise serializers.ValidationError(
                "Le prix de l’essence doit être supérieur à 0."
            )
        if data.get("prix_gasoil", 0) <= 0:
            raise serializers.ValidationError(
                "Le prix du gasoil doit être supérieur à 0."
            )
        if data.get("seuil_tolerance", 0) < 0:
            raise serializers.ValidationError(
                "Le seuil de tolérance ne peut pas être négatif."
            )
        return data

class RelaisIndexLigneV2Serializer(serializers.ModelSerializer):
    class Meta:
        model = RelaisIndexLigneV2
        fields = [
            "index_pompe",
            "index_debut",
            "index_fin",
        ]

    def validate(self, data):
        if data["index_fin"] < data["index_debut"]:
            raise serializers.ValidationError(
                "Index fin inférieur à l’index début."
            )
        return data

    
class RelaisIndexLigneV2Serializer(serializers.ModelSerializer):
    carburant = serializers.CharField(
        source="index_pompe.carburant",
        read_only=True
    )
    pompe_reference = serializers.CharField(
        source="index_pompe.pompe.reference",
        read_only=True
    )

    class Meta:
        model = RelaisIndexLigneV2
        fields = [
            "id",
            "index_pompe",
            "pompe_reference",
            "carburant",
            "index_debut",
            "index_fin",
        ]

    def validate(self, data):
        if data["index_fin"] < data["index_debut"]:
            raise serializers.ValidationError(
                "Index fin inférieur à l’index de début."
            )
        return data


class RelaisIndexV2Serializer(serializers.ModelSerializer):
    equipe_sortante = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True
    )
    # ======================
    # LIGNES
    # ======================
    lignes = RelaisIndexLigneV2Serializer(
        many=True,
        write_only=True,
        required=False
    )

    lignes_detail = RelaisIndexLigneV2Serializer(
        source="lignes",
        many=True,
        read_only=True
    )

    # ======================
    # FINANCIER (CALCULÉ)
    # ======================
    total_encaisse = serializers.SerializerMethodField()
    montant_total_prevu = serializers.SerializerMethodField()
    ecart_encaissement = serializers.SerializerMethodField()
    volume_total_vendu = serializers.SerializerMethodField()
    volumes_par_carburant = serializers.SerializerMethodField()

    class Meta:
        model = RelaisIndexV2
        fields = [
            # identité
            "id",
            "station",

            # période
            "debut_relais",
            "fin_relais",

            # équipes
            "equipe_sortante",
            "equipe_entrante",

            # workflow
            "status",

            # encaissement
            "encaisse_liquide",
            "encaisse_carte",
            "encaisse_ticket",
            "total_encaisse",

            # index
            "lignes",          # écriture
            "lignes_detail",   # lecture

            # financier
            "total_encaisse",
            "montant_total_prevu",
            "ecart_encaissement",

            # volumes
            "volume_total_vendu",
            "volumes_par_carburant",

            # meta
            "created_at",
        ]

        read_only_fields = (
            "station",
            "status",
            "created_at",
            "total_encaisse",
        )

    # ======================
    # METHODS
    # ======================
    def validate(self, attrs):
        request = self.context["request"]
        user = request.user
        station = user.station

        if not station:
            raise serializers.ValidationError(
                "Utilisateur non rattaché à une station."
            )

        # 🔒 RÈGLE CRITIQUE : un seul relais BROUILLON à la fois
        relais_brouillon_existe = RelaisIndexV2.objects.filter(
            station=station,
            status=RelaisIndexV2.Status.BROUILLON
        ).exists()

        if relais_brouillon_existe:
            raise serializers.ValidationError({
                "detail": (
                    "Un relais non soumis existe déjà pour cette station. "
                    "Veuillez le soumettre ou l’annuler avant d’en créer un nouveau."
                )
            })

        # 🔍 Dernier relais VALIDÉ (pas brouillon)
        dernier_relais = (
            RelaisIndexV2.objects
            .filter(station=station)
            .exclude(status=RelaisIndexV2.Status.BROUILLON)
            .order_by("-fin_relais")
            .first()
        )

        # ==========================
        # ÉQUIPE SORTANTE
        # ==========================
        if dernier_relais is None:
            # 👉 PREMIER RELAIS
            attrs["equipe_sortante"] = "PREMIER_RELAIS"
        else:
            # 👉 RELAIS SUIVANT
            attrs["equipe_sortante"] = dernier_relais.equipe_entrante

        # ==========================
        # ÉQUIPE ENTRANTE
        # ==========================
        if not attrs.get("equipe_entrante"):
            raise serializers.ValidationError({
                "equipe_entrante": "L’équipe entrante est obligatoire."
            })
        
        # ==========================
        # CONTRÔLE DES LIGNES (UNICITÉ INDEX)
        # ==========================
        lignes = attrs.get("lignes", [])

        index_ids = []
        for ligne in lignes:
            index_pompe = ligne.get("index_pompe")
            if index_pompe:
                index_ids.append(index_pompe.id)

        if len(index_ids) != len(set(index_ids)):
            raise serializers.ValidationError({
                "lignes": (
                    "Un même index de pompe ne peut pas être utilisé "
                    "plus d’une fois dans un relais."
                )
            })

        return attrs

    def create(self, validated_data):
        lignes_data = validated_data.pop("lignes", [])

        request = self.context["request"]
        user = request.user

        with transaction.atomic():
            relais = RelaisIndexV2.objects.create(
                station=user.station,
                created_by=user,
                **validated_data
            )

            for ligne in lignes_data:
                RelaisIndexLigneV2.objects.create(
                    relais=relais,
                    **ligne
                )

        # ============================
        # 2️⃣ CALCUL DU TOTAL PRÉVU
        # ============================

        parametrage = ParametrageStation.objects.filter(
            tenant=user.station.tenant
        ).first()

        if not parametrage:
            raise serializers.ValidationError(
                "Paramétrage station manquant."
            )

        montant_total_prevu = Decimal("0.00")

        for ligne in lignes_data:
            index_debut = Decimal(str(ligne["index_debut"]))
            index_fin = Decimal(str(ligne["index_fin"]))

            if index_fin < index_debut:
                raise serializers.ValidationError(
                    "Index fin inférieur à l’index début."
                )

            volume = index_fin - index_debut

            index_pompe = ligne["index_pompe"]  # ✅ déjà une instance

            if index_pompe.pompe.station != user.station:
                raise serializers.ValidationError(
                    "Index pompe non autorisé pour cette station."
                )

            if index_pompe.carburant == "ESSENCE":
                montant_total_prevu += volume * parametrage.prix_essence

            elif index_pompe.carburant == "GASOIL":
                montant_total_prevu += volume * parametrage.prix_gasoil

        # ============================
        # 3️⃣ CALCUL ÉCART & TOLÉRANCE
        # ============================

        total_encaisse = (
            relais.encaisse_liquide
            + relais.encaisse_carte
            + relais.encaisse_ticket
        )

        ecart = total_encaisse - montant_total_prevu

        tolerance = (
            parametrage.seuil_tolerance
            if parametrage.seuil_tolerance is not None
            else Decimal("0.00")
        )

        if abs(ecart) > tolerance:
            raise serializers.ValidationError({
                "ecart_encaissement": (
                    f"Écart hors tolérance ({ecart} FCFA). "
                    f"Tolérance autorisée : ±{tolerance} FCFA."
                )
            })

        return relais

    def get_total_encaisse(self, obj):
        return obj.total_encaisse

    def get_montant_total_prevu(self, obj):
        return obj.montant_total_prevu

    def get_ecart_encaissement(self, obj):
        return obj.ecart_encaissement

    def get_volume_total_vendu(self, obj):
        return obj.volume_total_vendu

    def get_volumes_par_carburant(self, obj):
        return obj.volumes_par_carburant