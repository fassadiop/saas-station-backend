from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from finances_station.models import TransactionStation
from accounts.constants import UserRole


class StationLastOperationsAPIView(APIView):
    """
    Dernières opérations financières d’une station.
    Visible uniquement par le GÉRANT.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        tenant = user.tenant
        station = user.station

        # 🔒 Gouvernance stricte
        if user.role != UserRole.GERANT:
            return Response([], status=200)

        if not tenant or not station:
            return Response([], status=200)

        qs = (
            TransactionStation.objects
            .filter(
                tenant=tenant,
                station=station,
                finance_status__in=["PROVISOIRE", "CONFIRMEE"]
            )
            .order_by("-date")[:10]
            .values(
                "id",
                "date",
                "type",
                "source_type",
                "montant",
                "finance_status",
            )
        )

        return Response(list(qs))
