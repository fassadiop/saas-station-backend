from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.pagination import PageNumberPagination
from finances_station.models import TransactionStation
from accounts.constants import UserRole

class StationOperationsPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100

class StationLastOperationsAPIView(APIView):
    """
    Historique des opérations financières d’une station.
    Visible uniquement par le GÉRANT.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user
        tenant = user.tenant
        station = user.station

        if user.role not in [
            UserRole.GERANT,
            UserRole.SUPERVISEUR,
        ]:
            return Response([], status=200)

        if not tenant or not station:
            return Response([], status=200)

        queryset = (
            TransactionStation.objects
            .filter(
                tenant=tenant,
                station=station,
                finance_status__in=[
                    "PROVISOIRE",
                    "CONFIRMEE",
                    "TRANSFERE",
                ]
            )
            .values(
                "id",
                "date",
                "type",
                "source_type",
                "montant",
                "finance_status",
            )
            .order_by("-date")
        )

        paginator = StationOperationsPagination()

        page = paginator.paginate_queryset(
            queryset,
            request
        )

        return paginator.get_paginated_response(page)