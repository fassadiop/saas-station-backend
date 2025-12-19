from rest_framework import serializers
from finances_station.models import TransactionStation


class TransactionStationSerializer(serializers.ModelSerializer):
    class Meta:
        model = TransactionStation
        fields = "__all__"
