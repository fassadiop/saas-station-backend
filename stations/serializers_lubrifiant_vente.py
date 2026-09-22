# stations/serializers_lubrifiant_vente.py

from decimal import Decimal

from rest_framework import serializers

from stations.models import Station, RelaisEquipe
from stations.models_lubrifiant import VenteLubrifiant
from stations.models_produit import Lubrifiants


class VenteLubrifiantSerializer(serializers.ModelSerializer):
    """
    Serializer des ventes de lubrifiants.

    Le prix unitaire et le montant sont calculés par le
    service métier à partir du prix de vente du catalogue.

    Ils sont donc en lecture seule côté API.
    """

    lubrifiant_code = serializers.CharField(
        source="lubrifiant.code",
        read_only=True,
    )

    lubrifiant_designation = serializers.CharField(
        source="lubrifiant.designation",
        read_only=True,
    )

    nature = serializers.CharField(
        source="lubrifiant.nature",
        read_only=True,
    )

    unite = serializers.CharField(
        source="lubrifiant.unite",
        read_only=True,
    )

    station_nom = serializers.CharField(
        source="station.nom",
        read_only=True,
    )

    date_vente = serializers.DateTimeField(
        required=False,
        allow_null=True,
    )

    class Meta:
        model = VenteLubrifiant

        fields = [
            "id",
            "tenant",
            "station",
            "station_nom",
            "relais",
            "lubrifiant",
            "lubrifiant_code",
            "lubrifiant_designation",
            "nature",
            "unite",
            "quantite",
            "prix_unitaire",
            "montant",
            "date_vente",
            "created_by",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "tenant",
            "prix_unitaire",
            "montant",
            "created_by",
            "created_at",
        ]

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
        # Lubrifiants actifs du tenant courant
        # ----------------------------------------------

        self.fields["lubrifiant"].queryset = (
            Lubrifiants.objects
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

    def validate_quantite(self, value):
        if value <= Decimal("0"):
            raise serializers.ValidationError(
                "La quantité doit être supérieure à zéro."
            )

        return value

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
        lubrifiant = attrs["lubrifiant"]
        relais = attrs.get("relais")

        # ----------------------------------------------
        # Tenant / station
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
        # Tenant / lubrifiant
        # ----------------------------------------------

        if lubrifiant.tenant_id != tenant.id:
            raise serializers.ValidationError(
                {
                    "lubrifiant": (
                        "Ce lubrifiant n'appartient pas "
                        "au tenant courant."
                    )
                }
            )

        if not lubrifiant.actif:
            raise serializers.ValidationError(
                {
                    "lubrifiant": (
                        "Ce lubrifiant est désactivé."
                    )
                }
            )

        # ----------------------------------------------
        # Relais facultatif
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
                            "Une vente ne peut être ajoutée "
                            "qu'à un relais à l'état BROUILLON."
                        )
                    }
                )

        return attrs