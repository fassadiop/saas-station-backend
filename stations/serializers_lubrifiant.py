# stations/serializers_lubrifiant.py

from decimal import Decimal

from rest_framework import serializers

from stations.models_produit import Lubrifiants


class LubrifiantSerializer(serializers.ModelSerializer):
    """
    Serializer CRUD du catalogue des lubrifiants.

    Le tenant est déterminé côté backend et ne peut pas être
    fourni ou modifié par le client.
    """

    class Meta:
        model = Lubrifiants
        fields = [
            "id",
            "tenant",
            "code",
            "designation",
            "nature",
            "unite",
            "prix_vente",
            "prix_achat",
            "seuil_alerte",
            "actif",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "tenant",
            "created_at",
            "updated_at",
        ]

    def validate_code(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "Le code du lubrifiant est obligatoire."
            )

        return value

    def validate_designation(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "La désignation du lubrifiant est obligatoire."
            )

        return value

    def validate_nature(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "La nature ou le format du lubrifiant est obligatoire."
            )

        return value

    def validate_unite(self, value):
        value = value.strip()

        if not value:
            raise serializers.ValidationError(
                "L'unité de conditionnement est obligatoire."
            )

        return value

    def validate_prix_vente(self, value):
        if value < Decimal("0"):
            raise serializers.ValidationError(
                "Le prix de vente ne peut pas être négatif."
            )

        return value

    def validate_prix_achat(self, value):
        if value is not None and value < Decimal("0"):
            raise serializers.ValidationError(
                "Le prix d'achat ne peut pas être négatif."
            )

        return value

    def validate_seuil_alerte(self, value):
        if value < Decimal("0"):
            raise serializers.ValidationError(
                "Le seuil d'alerte ne peut pas être négatif."
            )

        return value