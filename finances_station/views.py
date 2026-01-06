from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from accounts.constants import UserRole

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

    @action(detail=True, methods=["post"])
    def confirmer(self, request, pk=None):
        transaction = self.get_object()
        user = request.user

        # 🔐 Sécurité rôle
        if user.role != UserRole.GERANT:
            raise PermissionDenied(
                "Seul le gérant peut confirmer une transaction financière."
            )

        # 🔁 État attendu
        if transaction.finance_status != "PROVISOIRE":
            return Response(
                {"detail": "Transaction déjà confirmée ou invalide."},
                status=400
            )

        # ✅ Confirmation financière
        transaction.finance_status = "CONFIRMEE"
        transaction.save(update_fields=["finance_status"])

        return Response({
            "status": "confirmée",
            "transaction_id": transaction.id
        })