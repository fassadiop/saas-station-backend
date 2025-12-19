from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated

from finances_station.models import TransactionStation
from finances_station.serializers import TransactionStationSerializer


class TransactionStationViewSet(ReadOnlyModelViewSet):
    """
    Lecture seule des transactions financières de station.
    Les créations se font exclusivement via les flux STATION → FINANCES.
    """
    serializer_class = TransactionStationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user

        qs = TransactionStation.objects.filter(
            tenant_id=user.tenant_id
        )

        # Chef de station : uniquement sa station
        if getattr(user, "station_id", None):
            qs = qs.filter(station_id=user.station_id)

        return qs
