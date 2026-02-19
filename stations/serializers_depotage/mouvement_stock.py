from rest_framework import serializers
from stations.models_depotage.mouvement_stock import MouvementStock


class MouvementStockSerializer(serializers.ModelSerializer):

    produit_code = serializers.CharField(
        source="cuve.produit.code",
        read_only=True
    )

    cuve_reference = serializers.CharField(
        source="cuve.reference",
        read_only=True
    )

    class Meta:
        model = MouvementStock
        fields = [
            "id",
            "type_mouvement",
            "quantite",
            "produit_code",
            "cuve_reference",
            "source_type",
            "source_id",
            "date_mouvement",
            "created_at",
        ]
