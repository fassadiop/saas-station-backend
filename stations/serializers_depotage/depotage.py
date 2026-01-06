from rest_framework import serializers
from django.utils import timezone

from stations.models_depotage import Depotage
from stations.constants import DepotageStatus

class DepotageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Depotage
        fields = "__all__"
        read_only_fields = (
            "id",
            "station",
            "statut",
            "variation_cuve",
            "created_by",
            "validated_by",
            "created_at",
            "updated_at",
        )

    def validate(self, attrs):
        # Champs nécessaires selon statut
        jauge_avant = attrs.get("jauge_avant", self.instance.jauge_avant if self.instance else None)
        jauge_apres = attrs.get("jauge_apres", self.instance.jauge_apres if self.instance else None)
        q_livree = attrs.get("quantite_livree", self.instance.quantite_livree if self.instance else None)
        q_acceptee = attrs.get("quantite_acceptee", self.instance.quantite_acceptee if self.instance else None)

        if q_livree is not None and q_acceptee is not None:
            if q_acceptee > q_livree:
                raise serializers.ValidationError(
                    "La quantité acceptée ne peut pas dépasser la quantité livrée."
                )

        if jauge_avant is not None and jauge_apres is not None:
            if jauge_apres < jauge_avant:
                raise serializers.ValidationError(
                    "La jauge après ne peut pas être inférieure à la jauge avant."
                )

        return attrs

    def create(self, validated_data):
        user = self.context["request"].user

        validated_data["station"] = user.station
        validated_data["created_by"] = user

        # Calcul automatique
        validated_data["variation_cuve"] = (
            validated_data["jauge_apres"] - validated_data["jauge_avant"]
        )

        # Calcul financier
        validated_data["montant_total"] = (
            validated_data["quantite_acceptee"] * validated_data["prix_unitaire"]
        )

        return super().create(validated_data)

    def update(self, instance, validated_data):
        if instance.statut == DepotageStatus.CONFIRME:
            raise serializers.ValidationError(
                "Un dépotage confirmé ne peut plus être modifié."
            )

        instance = super().update(instance, validated_data)

        # Recalculs automatiques
        instance.variation_cuve = instance.jauge_apres - instance.jauge_avant
        instance.montant_total = instance.quantite_acceptee * instance.prix_unitaire
        instance.save(update_fields=["variation_cuve", "montant_total"])

        return instance
