from rest_framework import serializers
from django.db import transaction
from django.db.models import Q, Sum
from django.core.exceptions import ValidationError as DjangoValidationError
from decimal import Decimal

from accounts.models import Utilisateur
from stations.models_objectif import ObjectifStation
from .constants import REGIONS_DEPARTEMENTS
from .models import (
    CategorieDepense,
    ClientStation,
    Depense,
    DetteStation,
    EncaissementRelais,
    ModePaiement,
    Notification,
    ReglementDette,
    RelaisEcart,
    RelaisIndex,
    RelaisIndexPhoto,
    RelaisJauge,
    RemboursementEcart,
    Station,
    Pompe,
    IndexPompe,
    RelaisEquipe,
    FaitStatus,
    Ilot,
    RelaisIlot,
    Versement,
    EncaissementRelais,
    VersementDetail,
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

    station_nom = serializers.CharField(
        source="station.nom",
        read_only=True
    )


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
            "station_nom", 
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
            "reference",
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
# ILOT
# ============================================================
class IlotSerializer(serializers.ModelSerializer):

    nb_pompes = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Ilot
        fields = [
            "id",
            "tenant",
            "station",
            "nom",
            "actif",
            "nb_pompes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "tenant",
            "station",
            "created_at",
            "updated_at"
        ]

    # ------------------------------------
    # Tenant automatique
    # ------------------------------------
    def create(self, validated_data):
        request = self.context["request"]
        validated_data["tenant"] = request.user.tenant
        return super().create(validated_data)

    # ------------------------------------
    # Validation cohérence tenant/station
    # ------------------------------------
    def validate(self, attrs):

        request = self.context["request"]

        station = attrs.get("station")

        # cas création → station du gérant
        if station is None and self.instance is None:
            station = request.user.station

        # cas update → station existante
        if station is None and self.instance:
            station = self.instance.station

        if station is None:
            raise serializers.ValidationError(
                "Station introuvable pour cet utilisateur."
            )

        if station.tenant_id != request.user.tenant_id:
            raise serializers.ValidationError(
                "La station n'appartient pas à votre tenant."
            )

        return attrs

    # ------------------------------------
    # Interdiction désactivation incohérente
    # ------------------------------------
    def perform_update(self, serializer):

        instance = self.get_object()
        validated_data = serializer.validated_data

        if instance.actif and validated_data.get("actif") is False:
            if instance.pompes.filter(actif=True).exists():
                raise DjangoValidationError(
                    "Impossible de désactiver un îlot contenant des pompes actives."
                )

        serializer.save()

    # ------------------------------------
    # Nombre de pompes
    # ------------------------------------
    def get_nb_pompes(self, obj):
        if hasattr(obj, "nb_pompes"):
            return obj.nb_pompes

        return obj.pompes.count()
    
class RelaisIndexSerializer(serializers.ModelSerializer):

    id = serializers.IntegerField()

    volume_vendu = serializers.ReadOnlyField()

    volume_reellement_vendu = serializers.ReadOnlyField()

    index_pompe = serializers.PrimaryKeyRelatedField(read_only=True)
    index_debut = serializers.ReadOnlyField()

    produit = serializers.CharField(
        source="index_pompe.produit.code",
        read_only=True
    )

    prix_produit = serializers.SerializerMethodField()

    class Meta:
        model = RelaisIndex
        fields = (
            "id",
            "index_pompe",
            "index_debut",
            "index_fin",
            "volume_vendu",
            "retour_en_cuve",
            "volume_reellement_vendu",
            "produit",
            "prix_produit",
        )

    def get_prix_produit(self, obj):

        relais = obj.relais_ilot.relais

        prix = (
            PrixCarburant.objects
            .filter(
                tenant=relais.tenant,
                station=relais.station,
                produit=obj.index_pompe.produit,
                actif=True
            )
            .values_list("prix_unitaire", flat=True)
            .first()
        )

        return prix or 0


class RelaisIndexPhotoSerializer(serializers.ModelSerializer):

    # ==========================================================
    # CAPTURE
    # ==========================================================

    capture_par_nom = serializers.SerializerMethodField()

    # ==========================================================
    # VALIDATION
    # ==========================================================

    validee_par_nom = serializers.SerializerMethodField()

    # ==========================================================
    # INFORMATIONS RELAIS / INDEX
    # ==========================================================

    relais_id = serializers.IntegerField(
        source="relais_index.relais_ilot.relais_id",
        read_only=True
    )

    index_pompe_id = serializers.IntegerField(
        source="relais_index.index_pompe_id",
        read_only=True
    )

    pompe_reference = serializers.CharField(
        source="relais_index.index_pompe.pompe.reference",
        read_only=True
    )

    produit_code = serializers.CharField(
        source="relais_index.index_pompe.produit.code",
        read_only=True
    )

    index_debut = serializers.DecimalField(
        source="relais_index.index_debut",
        max_digits=12,
        decimal_places=2,
        read_only=True
    )

    index_fin = serializers.DecimalField(
        source="relais_index.index_fin",
        max_digits=12,
        decimal_places=2,
        read_only=True
    )

    # ==========================================================
    # META
    # ==========================================================

    class Meta:
        model = RelaisIndexPhoto

        fields = (
            # Identité
            "id",

            # Relation métier
            "relais_index",
            "relais_id",
            "index_pompe_id",
            "pompe_reference",
            "produit_code",

            # Index
            "index_debut",
            "index_fin",

            # Photo
            "photo",

            # OCR
            "valeur_ocr",
            "confiance_ocr",

            # Capture
            "date_capture",
            "capture_par",
            "capture_par_nom",

            # Validation
            "valeur_validee",
            "validee_par",
            "validee_par_nom",
            "date_validation",
            "commentaire_validation",

            # Workflow
            "statut",
        )

        read_only_fields = (
            # Identité
            "id",

            # Relations calculées
            "relais_id",
            "index_pompe_id",
            "pompe_reference",
            "produit_code",

            # Index
            "index_debut",
            "index_fin",

            # OCR : écrit uniquement par l'action /ocr/
            "valeur_ocr",
            "confiance_ocr",

            # Capture : écrit automatiquement à la création
            "date_capture",
            "capture_par",
            "capture_par_nom",

            # Validation : écrit uniquement par /valider/
            "valeur_validee",
            "validee_par",
            "validee_par_nom",
            "date_validation",
            "commentaire_validation",

            # Statut : piloté par les actions métier
            "statut",
        )

    # ==========================================================
    # NOM DU CAPTUREUR
    # ==========================================================

    def get_capture_par_nom(self, obj):
        if not obj.capture_par:
            return ""

        nom = (
            f"{obj.capture_par.first_name} "
            f"{obj.capture_par.last_name}"
        ).strip()

        return nom or obj.capture_par.username

    # ==========================================================
    # NOM DU VALIDATEUR
    # ==========================================================

    def get_validee_par_nom(self, obj):
        if not obj.validee_par:
            return ""

        nom = (
            f"{obj.validee_par.first_name} "
            f"{obj.validee_par.last_name}"
        ).strip()

        return nom or obj.validee_par.username
    

class EncaissementRelaisSerializer(serializers.ModelSerializer):

    mode_id = serializers.IntegerField(
        source="mode_paiement_id",
    )

    mode = serializers.CharField(
        source="mode_paiement.nom",
        read_only=True
    )

    class Meta:
        model = EncaissementRelais
        fields = (
            "mode_id",
            "mode",
            "montant",
        )


class EncaissementRelaisListSerializer(serializers.ModelSerializer):

    mode = serializers.CharField(source="mode_paiement.nom", read_only=True)

    relais_id = serializers.IntegerField(
        source="relais_ilot.relais.id",
        read_only=True
    )

    ilot_nom = serializers.CharField(
        source="relais_ilot.ilot.nom",
        read_only=True
    )

    responsable = serializers.SerializerMethodField()

    date_relais = serializers.DateTimeField(
        source="relais_ilot.relais.fin_relais",
        read_only=True
    )

    class Meta:
        model = EncaissementRelais
        fields = (
            "id",
            "date",
            "relais_id",
            "ilot_nom",
            "mode",
            "montant",
            "responsable",
            "date_relais",
        )

    def get_responsable(self, obj):

        responsable = obj.relais_ilot.responsable

        nom = (
            f"{responsable.first_name} "
            f"{responsable.last_name}"
        ).strip()

        return nom or responsable.username
    

class RelaisIlotSerializer(serializers.ModelSerializer):

    ilot_nom = serializers.CharField(source="ilot.nom", read_only=True)
    responsable_nom = serializers.SerializerMethodField()

    indexes = RelaisIndexSerializer(many=True, required=False)

    encaissements = EncaissementRelaisSerializer(
        many=True,
        required=False
    )

    total_volume_vendu = serializers.ReadOnlyField()
    total_theorique = serializers.ReadOnlyField()
    total_encaisse = serializers.ReadOnlyField()

    class Meta:
        model = RelaisIlot
        fields = "__all__"
        read_only_fields = [
            "tenant",
            "created_by",
            "soumis_par",
            "valide_par",
            "created_at",
            "updated_at",
        ]

    def get_responsable_nom(self, obj):
        return f"{obj.responsable.first_name} {obj.responsable.last_name}"

    # ======================================================
    # VALIDATION GLOBALE
    # ======================================================
    def validate(self, attrs):

        user = self.context["request"].user

        relais = attrs.get("relais") or getattr(self.instance, "relais", None)
        ilot = attrs.get("ilot") or getattr(self.instance, "ilot", None)
        responsable = attrs.get("responsable") or getattr(self.instance, "responsable", None)

        if relais.tenant_id != user.tenant_id:
            raise serializers.ValidationError("Relais hors tenant.")

        if ilot.station_id != relais.station_id:
            raise serializers.ValidationError(
                "L'îlot doit appartenir à la station du relais."
            )

        if responsable.tenant_id != relais.tenant_id:
            raise serializers.ValidationError(
                "Responsable hors tenant."
            )

        if relais.status == "TRANSFERE":
            raise serializers.ValidationError(
                "Relais transféré : modification interdite."
            )

        # 🔒 éviter l'erreur unique_together
        if not self.instance:
            if RelaisIlot.objects.filter(
                relais=relais,
                ilot=ilot
            ).exists():
                raise serializers.ValidationError(
                    "Cet îlot est déjà utilisé dans ce relais."
                )

        return attrs

    # ======================================================
    # CREATE
    # ======================================================
    def create(self, validated_data):

        user = self.context["request"].user

        with transaction.atomic():

            relais_ilot = RelaisIlot.objects.create(
                tenant=user.tenant,
                created_by=user,
                **validated_data
            )

            # =============================
            # INDEX POMPES
            # =============================

            index_pompes = IndexPompe.objects.filter(
                pompe__ilot=relais_ilot.ilot,
                actif=True
            ).select_related("pompe", "produit")

            if not index_pompes.exists():
                raise serializers.ValidationError(
                    "Aucun index de pompe actif sur cet îlot."
                )

            instances = []

            for index_pompe in index_pompes:

                dernier_index = (
                    RelaisIndex.objects
                    .filter(
                        index_pompe=index_pompe,
                        index_fin__isnull=False
                    )
                    .order_by("-id")
                    .first()
                )

                index_debut = (
                    dernier_index.index_fin
                    if dernier_index
                    else index_pompe.index_courant
                )

                instance = RelaisIndex(
                    relais_ilot=relais_ilot,
                    index_pompe=index_pompe,
                    index_debut=index_debut
                )

                instance.full_clean()
                instances.append(instance)

            RelaisIndex.objects.bulk_create(instances)

            # =============================
            # ENCAISSEMENTS
            # =============================

            modes = ModePaiement.objects.filter(actif=True)

            encaissements = []

            for mode in modes:

                encaissements.append(
                    EncaissementRelais(
                        tenant=relais_ilot.tenant,
                        relais_ilot=relais_ilot,
                        mode_paiement=mode,
                        montant=0,
                        date=relais_ilot.relais.fin_relais,
                        created_by=user
                    )
                )

            EncaissementRelais.objects.bulk_create(encaissements)

        return relais_ilot

    # ======================================================
    # UPDATE (BROUILLON UNIQUEMENT)
    # ======================================================
    def update(self, instance, validated_data):

        indexes_data = validated_data.pop("indexes", [])
        encaissements_data = validated_data.pop("encaissements", [])

        with transaction.atomic():

            instance = super().update(instance, validated_data)

            # =============================
            # INDEXES
            # =============================

            indexes = {
                idx.id: idx
                for idx in instance.indexes.all()
            }

            to_update = []

            for data in indexes_data:

                idx_id = data.get("id")

                if idx_id is None:
                    raise serializers.ValidationError(
                        "ID index manquant."
                    )

                idx = indexes.get(idx_id)

                if not idx:
                    raise serializers.ValidationError(
                        "Index invalide."
                    )

                index_fin = data.get("index_fin")
                retour_en_cuve = data.get("retour_en_cuve")

                # =============================
                # VALIDATION INDEX FIN
                # =============================

                if (
                    index_fin is not None
                    and index_fin < idx.index_debut
                ):
                    raise serializers.ValidationError(
                        "Index fin inférieur à l'index début."
                    )

                # =============================
                # VALIDATION RETOUR EN CUVE
                # =============================

                if (
                    retour_en_cuve is not None
                    and retour_en_cuve < 0
                ):
                    raise serializers.ValidationError(
                        "Le retour en cuve ne peut pas être négatif."
                    )

                volume_distribue = (
                    index_fin - idx.index_debut
                    if index_fin is not None
                    else 0
                )

                if (
                    retour_en_cuve is not None
                    and retour_en_cuve > volume_distribue
                ):
                    raise serializers.ValidationError(
                        "Le retour en cuve ne peut pas être supérieur "
                        "au volume distribué."
                    )

                # =============================
                # AFFECTATION
                # =============================

                idx.index_fin = index_fin
                idx.retour_en_cuve = retour_en_cuve

                # =============================
                # PRIX + MONTANT THÉORIQUE
                # =============================

                if index_fin is not None:

                    prix = (
                        PrixCarburant.objects
                        .filter(
                            tenant=instance.tenant,
                            station=instance.relais.station,
                            produit=idx.index_pompe.produit,
                            actif=True
                        )
                        .values_list(
                            "prix_unitaire",
                            flat=True
                        )
                        .first()
                    )

                    idx.prix_unitaire = prix or 0

                    volume_reellement_vendu = (
                        volume_distribue
                        - (retour_en_cuve or 0)
                    )

                    idx.montant_theorique = (
                        volume_reellement_vendu
                        * idx.prix_unitaire
                    )

                else:

                    idx.prix_unitaire = None
                    idx.montant_theorique = None

                to_update.append(idx)

            if to_update:
                RelaisIndex.objects.bulk_update(
                    to_update,
                    [
                        "index_fin",
                        "retour_en_cuve",
                        "prix_unitaire",
                        "montant_theorique",
                    ]
                )

            # =============================
            # ENCAISSEMENTS
            # =============================

            instance.encaissements.exclude(
                mode_paiement_id__in=[
                    d["mode_paiement_id"] for d in encaissements_data
                ]
            ).delete()

            for data in encaissements_data:

                EncaissementRelais.objects.update_or_create(
                    tenant=instance.tenant,
                    relais_ilot=instance,
                    mode_paiement_id=data["mode_paiement_id"],
                    defaults={
                        "montant": data["montant"],
                        "date": instance.relais.date_relais,
                        "created_by": self.context["request"].user
                    }
                )

        return instance

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

    ilot_id = serializers.PrimaryKeyRelatedField(
        queryset=Ilot.objects.all(),
        source="ilot",
        write_only=True
    )

    index_pompes = IndexPompeReadSerializer(many=True, read_only=True)

    class Meta:
        model = Pompe
        fields = [
            "id",
            "station",
            "ilot",
            "station_id",
            "ilot_id",
            "reference",
            "actif",
            "index_pompes",
        ]

        read_only_fields = [
            "id",
            "station",
            "ilot",
            "index_pompes"
        ]

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

class RelaisIlotListSerializer(serializers.ModelSerializer):

    ilot_nom = serializers.CharField(source="ilot.nom", read_only=True)
    responsable_nom = serializers.SerializerMethodField()

    class Meta:
        model = RelaisIlot
        fields = [
            "id",
            "ilot",
            "ilot_nom",
            "responsable_nom",
            "total_encaisse",
        ]

    def get_responsable_nom(self, obj):
        return f"{obj.responsable.first_name} {obj.responsable.last_name}"

    def get_total_encaisse(self, obj):
        return (
            obj.encaissements.aggregate(total=Sum("montant"))["total"]
            or 0
        )


class RelaisEquipeSerializer(serializers.ModelSerializer):

    ilots = RelaisIlotListSerializer(many=True, read_only=True)

    total_volume_vendu = serializers.ReadOnlyField()
    total_theorique = serializers.ReadOnlyField()
    total_encaisse = serializers.ReadOnlyField()

    nombre_ventes_lubrifiants = serializers.SerializerMethodField()
    total_ventes_lubrifiants = serializers.SerializerMethodField()

    equipe_sortante = serializers.CharField(
        read_only=True
    )
    

    class Meta:
        model = RelaisEquipe
        fields = "__all__"
        read_only_fields = (
            "tenant",
            "station",
            "created_by",
            "status",
            "created_at",
            "stock_applique",
            "soumis_par",
            "soumis_le",
            "valide_par",
            "valide_le",
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

        # 🔒 Blocage si relais non transféré existe
        if not self.instance:

            open_relais = (
                RelaisEquipe.objects
                .filter(station=user.station)
                .exclude(status=FaitStatus.TRANSFERE)
            )

            if open_relais.exists():
                raise serializers.ValidationError(
                    "Le relais précédent doit être transféré avant d'en créer un nouveau."
                )

        return data

    # ==========================
    # CREATE
    # ==========================
    def create(self, validated_data):

        user = self.context["request"].user

        dernier_relais = (
            RelaisEquipe.objects
            .filter(
                station=user.station,
                status=FaitStatus.TRANSFERE
            )
            .order_by("-fin_relais")
            .first()
        )

        if dernier_relais:
            validated_data["equipe_sortante"] = (
                dernier_relais.equipe_entrante
            )

        return RelaisEquipe.objects.create(
            tenant=user.tenant,
            station=user.station,
            created_by=user,
            **validated_data
        )

    # ==========================
    # UPDATE
    # ==========================
    def update(self, instance, validated_data):

        if instance.status != FaitStatus.BROUILLON:
            raise serializers.ValidationError(
                "Modification impossible : relais non en brouillon."
            )

        return super().update(instance, validated_data)

    def get_nombre_ventes_lubrifiants(self, obj):
        from stations.models_lubrifiant.vente import VenteLubrifiant

        return VenteLubrifiant.objects.filter(
            tenant_id=obj.tenant_id,
            station_id=obj.station_id,
            relais_id=obj.id,
        ).count()


    def get_total_ventes_lubrifiants(self, obj):
        from stations.models_lubrifiant.vente import VenteLubrifiant

        total = VenteLubrifiant.objects.filter(
            tenant_id=obj.tenant_id,
            station_id=obj.station_id,
            relais_id=obj.id,
        ).aggregate(
            total=Sum("montant")
        )["total"]

        return total if total is not None else Decimal("0.00")
    

class RelaisEquipeListSerializer(serializers.ModelSerializer):

    total_volume_vendu = serializers.ReadOnlyField()
    total_encaisse = serializers.ReadOnlyField()

    encaissements = serializers.SerializerMethodField()

    class Meta:
        model = RelaisEquipe
        fields = (
            "id",
            "debut_relais",
            "fin_relais",
            "equipe_sortante",
            "equipe_entrante",
            "total_volume_vendu",
            "encaissements",
            "total_encaisse",
            "status",
            "created_at",
        )

    def get_encaissements(self, obj):

        qs = (
            EncaissementRelais.objects
            .filter(relais_ilot__relais=obj)
            .values("mode_paiement__code", "mode_paiement__nom")
            .annotate(total=Sum("montant"))
        )

        return [
            {
                "code": r["mode_paiement__code"],
                "nom": r["mode_paiement__nom"],
                "montant": float(r["total"] or 0),
            }
            for r in qs
        ]


class RelaisJaugeSerializer(serializers.ModelSerializer):

    produit_nom = serializers.CharField(
        source="produit.nom",
        read_only=True
    )

    produit_code = serializers.CharField(
        source="produit.code",
        read_only=True
    )

    class Meta:
        model = RelaisJauge

        fields = [
            "id",
            "relais",
            "produit",
            "produit_nom",
            "produit_code",
            "jauge_debut",
            "jauge_fin",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "produit_nom",
            "produit_code",
            "created_at",
            "updated_at",
        ]


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


class ObjectifStationSerializer(serializers.ModelSerializer):

    station_nom = serializers.CharField(
        source="station.nom",
        read_only=True
    )

    produit_code = serializers.CharField(
        source="produit.code",
        read_only=True
    )

    class Meta:
        model = ObjectifStation
        fields = [
            "id",
            "tenant",
            "station",
            "station_nom",
            "produit",
            "produit_code",
            "annee",
            "mois",
            "volume_cible",
            "ca_cible",
            "created_at",
        ]
        read_only_fields = ["tenant", "created_at"]

    def validate(self, data):
        tenant = self.context["request"].user.tenant

        exists = ObjectifStation.objects.filter(
            tenant=tenant,
            station=data["station"],
            produit=data["produit"],
            annee=data["annee"],
            mois=data["mois"],
        ).exists()

        if exists and self.instance is None:
            raise serializers.ValidationError(
                "Objectif déjà défini pour cette période."
            )

        return data
    

class ModePaiementSerializer(serializers.ModelSerializer):

    class Meta:
        model = ModePaiement
        fields = (
            "id",
            "nom",
            "code",
            "actif",
            "created_at",
        )
        read_only_fields = ("id", "created_at")


class VersementDetailSerializer(serializers.ModelSerializer):

    mode = serializers.CharField(
        source="mode_paiement.nom",
        read_only=True
    )

    mode_id = serializers.IntegerField(
        source="mode_paiement_id"
    )

    class Meta:
        model = VersementDetail
        fields = (
            "mode_id",
            "mode",
            "montant",
        )


class VersementSerializer(serializers.ModelSerializer):


    details = VersementDetailSerializer(many=True)

    # Informations contextuelles
    relais_id = serializers.IntegerField(
        source="relais_ilot.relais.id",
        read_only=True
    )

    ilot_nom = serializers.CharField(
        source="relais_ilot.ilot.nom",
        read_only=True
    )

    responsable = serializers.SerializerMethodField()

    # Calculs financiers
    encaissement_total = serializers.SerializerMethodField()
    ecart = serializers.SerializerMethodField()

    class Meta:
        model = Versement
        fields = (
            "id",
            "relais_ilot",
            "relais_id",
            "ilot_nom",
            "responsable",
            "montant_remis",
            "date_versement",
            "reference",
            "encaissement_total",
            "details",
            "ecart",
            "created_at",
        )

        read_only_fields = (
            "id",
            "relais_id",
            "ilot_nom",
            "responsable",
            "encaissement_total",
            "ecart",
            "created_at",
        )

    def get_responsable(self, obj):

        responsable = obj.relais_ilot.responsable

        nom = (
            f"{responsable.first_name} "
            f"{responsable.last_name}"
        ).strip()

        return nom or responsable.username

    # ======================================================
    # CALCUL TOTAL ENCAISSEMENTS
    # ======================================================

    def get_encaissement_total(self, obj):

        total = (
            EncaissementRelais.objects
            .filter(relais_ilot=obj.relais_ilot)
            .aggregate(total=Sum("montant"))
        )

        return total["total"] or 0

    # ======================================================
    # CALCUL ECART CAISSE
    # ======================================================

    def get_ecart(self, obj):

        total = (
            EncaissementRelais.objects
            .filter(relais_ilot=obj.relais_ilot)
            .aggregate(total=Sum("montant"))
        )["total"] or 0

        return obj.montant_remis - total
    
    def create(self, validated_data):

        details_data = validated_data.pop("details")

        with transaction.atomic():

            versement = Versement.objects.create(**validated_data)

            for d in details_data:
                VersementDetail.objects.create(
                    versement=versement,
                    mode_paiement_id=d["mode_paiement_id"],
                    montant=d["montant"]
                )

        return versement
    
class DepenseSerializer(serializers.ModelSerializer):

    categorie_nom = serializers.CharField(
        source="categorie.nom",
        read_only=True
    )

    class Meta:
        model = Depense
        fields = [
            "id",
            "date_depense",
            "categorie",
            "categorie_nom",
            "description",
            "montant",
            "statut",
            "relais",
        ]
        read_only_fields = [
            "tenant",
            "station",
            "relais",
            "created_by",
            "validated_by",
            "validated_at",
        ]

class CategorieDepenseSerializer(serializers.ModelSerializer):

    class Meta:
        model = CategorieDepense
        fields = [
            "id",
            "nom",
            "actif",
        ]

class ReglementDetteSerializer(serializers.ModelSerializer):

    montant = serializers.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    mode_paiement_nom = serializers.CharField(
        source="mode_paiement.nom",
        read_only=True
    )

    class Meta:
        model = ReglementDette
        fields = [
            "id",
            "montant",
            "mode_paiement_nom",
            "created_at"
        ]

class DetteStationSerializer(serializers.ModelSerializer):

    produit_nom = serializers.CharField(
        source="produit.nom",
        read_only=True
    )

    montant_restant = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True
    )

    client_nom = serializers.CharField(
        source="client.nom",
        read_only=True
    )

    station_nom = serializers.CharField(
        source="station.nom",
        read_only=True
    )

    relais = serializers.PrimaryKeyRelatedField(
        read_only=True
    )

    reglements = ReglementDetteSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = DetteStation
        fields = [
            "id",
            "station",
            "station_nom",
            "relais",
            "client",
            "client_nom",
            "produit",
            "produit_nom",
            "transaction",
            "volume",
            "prix_unitaire",
            "montant_initial",
            "montant_regle",
            "montant_restant",
            "reglements",
            "statut",
            "created_at"
        ]

        read_only_fields = [
            "station",
            "transaction",
            "prix_unitaire",
            "montant_initial",
            "montant_regle",
            "statut",
            "created_at"
        ]


class ClientStationSerializer(serializers.ModelSerializer):

    total_dette_active = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        read_only=True
    )

    station_nom = serializers.CharField(
        source="station_limitee.nom",
        read_only=True
    )

    credit_restant = serializers.SerializerMethodField()

    class Meta:
        model = ClientStation
        fields = [
            "id",
            "type_client",
            "nom",
            "cni",
            "telephone",
            "email",
            "adresse",
            "registre_commerce",
            "station_limitee",
            "station_nom",
            "plafond_credit",
            "credit_restant",
            "actif",
            "agree_par_admin",
            "total_dette_active",
            "created_at",
        ]

        read_only_fields = [
            "agree_par_admin",
            "created_at",
        ]

    def get_credit_restant(self, obj):
        return obj.credit_disponible

    def validate_cni(self, value):

        type_client = self.initial_data.get(
            "type_client"
        )

        # Une entreprise n'utilise pas le CNI
        if type_client == "ENTREPRISE":
            return value

        tenant = self.context["request"].user.tenant

        qs = ClientStation.objects.filter(
            tenant=tenant,
            cni=value
        )

        if self.instance:
            qs = qs.exclude(
                pk=self.instance.pk
            )

        if qs.exists():
            raise serializers.ValidationError(
                "Un client avec ce CNI existe déjà."
            )

        return value
    
    def validate(self, attrs):

        type_client = attrs.get(
            "type_client",
            getattr(self.instance, "type_client", None)
        )

        if (
            type_client == "PARTICULIER"
            and not attrs.get("cni")
        ):
            raise serializers.ValidationError({
                "cni": "Le numéro CNI est obligatoire."
            })

        if (
            type_client == "ENTREPRISE"
            and not attrs.get("registre_commerce")
        ):
            raise serializers.ValidationError({
                "registre_commerce":
                "Le registre de commerce est obligatoire."
            })

        return attrs
    

class ReglementDetteSerializer(serializers.Serializer):

    montant = serializers.DecimalField(
        max_digits=14,
        decimal_places=2
    )

    mode_paiement = serializers.PrimaryKeyRelatedField(
        queryset=ModePaiement.objects.filter(actif=True)
    )


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"

class RelaisEcartSerializer(serializers.ModelSerializer):

    responsable_nom = serializers.SerializerMethodField()

    montant_rembourse = serializers.ReadOnlyField()
    reste_a_rembourser = serializers.ReadOnlyField()
    est_solde = serializers.ReadOnlyField()

    relais_id = serializers.IntegerField(
        source="relais.id",
        read_only=True
    )

    ilot_nom = serializers.CharField(
        source="relais_ilot.ilot.nom",
        read_only=True
    )

    created_by_nom = serializers.SerializerMethodField()

    class Meta:
        model = RelaisEcart
        fields = [
            "id",
            "date_relais",
            "relais_id",
            "ilot_nom",
            "responsable_nom",
            "type_ecart",
            "montant_theorique",
            "montant_encaisse",
            "montant",
            "montant_rembourse",
            "reste_a_rembourser",
            "est_solde",
            "created_by_nom",
            "created_at",
        ]

    def get_responsable_nom(self, obj):

        nom = (
            f"{obj.responsable.first_name} "
            f"{obj.responsable.last_name}"
        ).strip()

        return nom or obj.responsable.username
    
    def get_created_by_nom(self, obj):

        nom = (
            f"{obj.created_by.first_name} "
            f"{obj.created_by.last_name}"
        ).strip()

        return nom or obj.created_by.username
    
class RemboursementEcartSerializer(serializers.ModelSerializer):

    responsable_nom = serializers.SerializerMethodField()
    reste_a_rembourser = serializers.SerializerMethodField()

    class Meta:
        model = RemboursementEcart

        fields = (
            "id",
            "ecart",
            "responsable",
            "responsable_nom",
            "montant",
            "date_remboursement",
            "commentaire",
            "reste_a_rembourser",
            "created_at",
        )

        read_only_fields = (
            "id",
            "responsable",
            "responsable_nom",
            "reste_a_rembourser",
            "created_at",
        )

    def get_responsable_nom(self, obj):

        nom = (
            f"{obj.responsable.first_name} "
            f"{obj.responsable.last_name}"
        ).strip()

        return nom or obj.responsable.username

    def get_reste_a_rembourser(self, obj):

        return obj.ecart.reste_a_rembourser

    def validate_ecart(self, value):

        if value.est_solde:
            raise serializers.ValidationError(
                "Cet écart est déjà totalement remboursé."
            )

        return value

    def create(self, validated_data):

        user = self.context["request"].user

        ecart = validated_data.pop("ecart")
        montant = validated_data.pop("montant")
        date_remboursement = validated_data.pop("date_remboursement")
        commentaire = validated_data.pop("commentaire", "")

        return RemboursementEcart.objects.create(
            tenant=user.tenant,
            ecart=ecart,
            responsable=ecart.responsable,
            montant=montant,
            date_remboursement=date_remboursement,
            commentaire=commentaire,
            created_by=user,
        )
    

class ClotureJournaliereSerializer(serializers.Serializer):
    resume = serializers.DictField()
    ilots = serializers.ListField()
    depenses = serializers.DictField()
    credits = serializers.DictField()
    ecarts = serializers.DictField()
    synthese = serializers.DictField()