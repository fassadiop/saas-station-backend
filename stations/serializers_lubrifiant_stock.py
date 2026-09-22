# stations/serializers_lubrifiant_stock.py

from decimal import Decimal

from rest_framework import serializers

from stations.models import Station
from stations.models_lubrifiant import (
    MouvementStockLubrifiant,
    StockLubrifiant,
)
from stations.models_produit import Lubrifiants


class StockLubrifiantSerializer(serializers.ModelSerializer):
    """
    Serializer de consultation du stock de lubrifiants.

    Le stock actuel est une donnée calculée et gérée par le
    service métier. Il est donc en lecture seule ici.
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

    seuil_alerte = serializers.DecimalField(
        source="lubrifiant.seuil_alerte",
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    actif = serializers.BooleanField(
        source="lubrifiant.actif",
        read_only=True,
    )

    class Meta:
        model = StockLubrifiant
        fields = [
            "id",
            "tenant",
            "station",
            "lubrifiant",
            "lubrifiant_code",
            "lubrifiant_designation",
            "nature",
            "unite",
            "stock_actuel",
            "seuil_alerte",
            "actif",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "tenant",
            "stock_actuel",
            "created_at",
            "updated_at",
        ]


class MouvementStockLubrifiantSerializer(serializers.ModelSerializer):
    """
    Serializer de consultation de l'historique des mouvements
    de stock des lubrifiants.
    """

    lubrifiant_code = serializers.CharField(
        source="lubrifiant.code",
        read_only=True,
    )

    lubrifiant_designation = serializers.CharField(
        source="lubrifiant.designation",
        read_only=True,
    )

    class Meta:
        model = MouvementStockLubrifiant
        fields = [
            "id",
            "tenant",
            "station",
            "lubrifiant",
            "lubrifiant_code",
            "lubrifiant_designation",
            "type_mouvement",
            "quantite",
            "source_type",
            "source_id",
            "date_mouvement",
            "created_at",
        ]

        read_only_fields = [
            "id",
            "tenant",
            "type_mouvement",
            "source_type",
            "source_id",
            "created_at",
        ]


class MouvementStockLubrifiantActionSerializer(
    serializers.Serializer
):
    """
    Serializer utilisé pour les actions métier :

    - entrée de stock
    - sortie de stock

    Le serializer valide les données d'entrée.
    La modification effective du stock est réalisée exclusivement
    par le service métier.
    """

    station = serializers.PrimaryKeyRelatedField(
        queryset=Station.objects.none(),
    )

    lubrifiant = serializers.PrimaryKeyRelatedField(
        queryset=Lubrifiants.objects.none(),
    )

    quantite = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    date_mouvement = serializers.DateTimeField(
        required=False,
        allow_null=True,
    )

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
        # Lubrifiants du tenant courant uniquement
        # ----------------------------------------------

        self.fields["lubrifiant"].queryset = (
            Lubrifiants.objects
            .filter(
                tenant=tenant,
                actif=True,
            )
            .order_by("code")
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

        # ----------------------------------------------
        # Vérification tenant / station
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

        # ----------------------------------------------
        # Vérification tenant / lubrifiant
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

        # ----------------------------------------------
        # Le lubrifiant doit être actif
        # ----------------------------------------------

        if not lubrifiant.actif:
            raise serializers.ValidationError(
                {
                    "lubrifiant": (
                        "Ce lubrifiant est désactivé."
                    )
                }
            )

        # ----------------------------------------------
        # La station doit être active
        # ----------------------------------------------

        if not station.active:
            raise serializers.ValidationError(
                {
                    "station": (
                        "Cette station est désactivée."
                    )
                }
            )

        return attrs