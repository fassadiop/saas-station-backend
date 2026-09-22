# stations/serializers_baie.py

from decimal import Decimal

from rest_framework import serializers

from stations.models import Station, RelaisEquipe
from stations.models_baie import OperationBaie, PrestationBaie


class OperationBaieSerializer(serializers.ModelSerializer):
    """
    Serializer des opérations de baie.

    Le prix unitaire et le montant sont calculés
    par le service métier à partir du prix de la
    prestation sélectionnée.

    Ils sont donc en lecture seule côté API.
    """

    # ==================================================
    # INFORMATIONS PRESTATION
    # ==================================================

    prestation_code = serializers.CharField(
        source="prestation.code",
        read_only=True,
    )

    prestation_designation = serializers.CharField(
        source="prestation.designation",
        read_only=True,
    )

    unite = serializers.CharField(
        source="prestation.unite",
        read_only=True,
    )

    # ==================================================
    # INFORMATIONS STATION
    # ==================================================

    station_nom = serializers.CharField(
        source="station.nom",
        read_only=True,
    )

    # ==================================================
    # INFORMATIONS RELAIS
    # ==================================================

    relais_id = serializers.IntegerField(
        source="relais.id",
        read_only=True,
    )

    # ==================================================
    # META
    # ==================================================

    class Meta:
        model = OperationBaie

        fields = [
            "id",

            "tenant",

            "station",
            "station_nom",

            "relais",
            "relais_id",

            "prestation",
            "prestation_code",
            "prestation_designation",
            "unite",

            "quantite",
            "prix_unitaire",
            "montant",

            "created_by",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "tenant",

            "station_nom",

            "relais_id",

            "prestation_code",
            "prestation_designation",
            "unite",

            "prix_unitaire",
            "montant",

            "created_by",
            "created_at",
            "updated_at",
        ]

    # ==================================================
    # INITIALISATION DES QUERYSETS
    # ==================================================

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")

        if request is None:
            return

        tenant = getattr(
            request.user,
            "tenant",
            None,
        )

        if tenant is None:
            return

        # ----------------------------------------------
        # Stations du tenant courant uniquement
        # ----------------------------------------------

        self.fields["station"].queryset = (
            Station.objects
            .filter(
                tenant=tenant,
                active=True,
            )
            .order_by("nom")
        )

        # ----------------------------------------------
        # Prestations du tenant courant
        #
        # Le filtrage par station sera renforcé
        # dans validate().
        # ----------------------------------------------

        self.fields["prestation"].queryset = (
            PrestationBaie.objects
            .filter(
                tenant=tenant,
                actif=True,
            )
            .order_by("code")
        )

        # ----------------------------------------------
        # Relais du tenant courant
        # ----------------------------------------------

        self.fields["relais"].queryset = (
            RelaisEquipe.objects
            .filter(
                tenant=tenant,
            )
            .order_by("-id")
        )

    # ==================================================
    # VALIDATION QUANTITÉ
    # ==================================================

    def validate_quantite(self, value):

        if value <= Decimal("0"):
            raise serializers.ValidationError(
                "La quantité doit être supérieure à zéro."
            )

        return value

    # ==================================================
    # VALIDATION GLOBALE
    # ==================================================

    def validate(self, attrs):

        request = self.context.get("request")

        if request is None:
            return attrs

        tenant = getattr(
            request.user,
            "tenant",
            None,
        )

        if tenant is None:
            raise serializers.ValidationError(
                "Aucun tenant n'est associé à cet utilisateur."
            )

        station = attrs["station"]
        prestation = attrs["prestation"]
        relais = attrs.get("relais")

        # ----------------------------------------------
        # TENANT / STATION
        # ----------------------------------------------

        if station.tenant_id != tenant.id:
            raise serializers.ValidationError(
                {
                    "station": (
                        "Cette station n'appartient pas "
                        "au tenant courant."
                    )
                }
            )

        if not station.active:
            raise serializers.ValidationError(
                {
                    "station": (
                        "Cette station est désactivée."
                    )
                }
            )

        # ----------------------------------------------
        # TENANT / PRESTATION
        # ----------------------------------------------

        if prestation.tenant_id != tenant.id:
            raise serializers.ValidationError(
                {
                    "prestation": (
                        "Cette prestation n'appartient pas "
                        "au tenant courant."
                    )
                }
            )

        # ----------------------------------------------
        # STATION / PRESTATION
        # ----------------------------------------------

        if prestation.station_id != station.id:
            raise serializers.ValidationError(
                {
                    "prestation": (
                        "Cette prestation n'appartient pas "
                        "à cette station."
                    )
                }
            )

        if not prestation.actif:
            raise serializers.ValidationError(
                {
                    "prestation": (
                        "Cette prestation est désactivée."
                    )
                }
            )

        # ----------------------------------------------
        # RELAIS FACULTATIF
        # ----------------------------------------------

        if relais is not None:

            if relais.tenant_id != tenant.id:
                raise serializers.ValidationError(
                    {
                        "relais": (
                            "Ce relais n'appartient pas "
                            "au tenant courant."
                        )
                    }
                )

            if relais.station_id != station.id:
                raise serializers.ValidationError(
                    {
                        "relais": (
                            "Ce relais n'appartient pas "
                            "à cette station."
                        )
                    }
                )

            if relais.status != relais.Statut.BROUILLON:
                raise serializers.ValidationError(
                    {
                        "relais": (
                            "Une opération de baie ne peut "
                            "être ajoutée qu'à un relais "
                            "à l'état BROUILLON."
                        )
                    }
                )

        return attrs


from decimal import Decimal

from rest_framework import serializers

from stations.models import Station
from stations.models_baie import PrestationBaie


class PrestationBaieSerializer(serializers.ModelSerializer):

    station_nom = serializers.CharField(
        source="station.nom",
        read_only=True,
    )

    class Meta:
        model = PrestationBaie

        fields = [
            "id",
            "tenant",
            "station",
            "station_nom",
            "code",
            "designation",
            "unite",
            "prix_unitaire",
            "actif",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "tenant",
            "station_nom",
            "created_at",
            "updated_at",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        request = self.context.get("request")

        if request is None:
            return

        tenant = getattr(request.user, "tenant", None)

        if tenant is None:
            return

        self.fields["station"].queryset = (
            Station.objects
            .filter(
                tenant=tenant,
                active=True,
            )
            .order_by("nom")
        )

    def validate_code(self, value):
        value = value.strip().upper()

        if not value:
            raise serializers.ValidationError(
                "Le code est obligatoire."
            )

        return value

    def validate_designation(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "La désignation est obligatoire."
            )

        return value

    def validate_unite(self, value):
        value = value.strip().upper()

        if not value:
            raise serializers.ValidationError(
                "L'unité est obligatoire."
            )

        return value

    def validate_prix_unitaire(self, value):
        if value < Decimal("0"):
            raise serializers.ValidationError(
                "Le prix unitaire ne peut pas être négatif."
            )

        return value

    def validate(self, attrs):

        request = self.context.get("request")

        if request is None:
            return attrs

        tenant = getattr(request.user, "tenant", None)

        if tenant is None:
            raise serializers.ValidationError(
                "Aucun tenant n'est associé à cet utilisateur."
            )

        station = attrs.get("station")

        # En création, la station est obligatoire.
        if self.instance is None and station is None:
            raise serializers.ValidationError({
                "station": "La station est obligatoire."
            })

        # En modification partielle, utiliser la station existante.
        if station is None and self.instance is not None:
            station = self.instance.station

        if station.tenant_id != tenant.id:
            raise serializers.ValidationError({
                "station": (
                    "Cette station n'appartient pas "
                    "au tenant courant."
                )
            })

        if not station.active:
            raise serializers.ValidationError({
                "station": "Cette station est désactivée."
            })

        # Unicité tenant + station + code
        code = attrs.get("code")

        if code:
            queryset = PrestationBaie.objects.filter(
                tenant=tenant,
                station=station,
                code=code,
            )

            # En modification, exclure l'objet courant
            if self.instance:
                queryset = queryset.exclude(
                    pk=self.instance.pk
                )

            if queryset.exists():
                raise serializers.ValidationError({
                    "code": (
                        "Ce code existe déjà pour cette station."
                    )
                })

        return attrs