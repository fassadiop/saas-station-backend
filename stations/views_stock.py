from django.db.models import Sum
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from stations.models_depotage.cuve import Cuve, CuveStatus
from stations.models_produit import ProduitCarburant
from stations.services.stock import get_stock_global_produit


class StockGlobalStationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        station = request.user.station

        produits = ProduitCarburant.objects.filter(
            tenant=station.tenant,
            actif=True
        )

        data = []

        for produit in produits:

            stock_global = get_stock_global_produit(
                station=station,
                produit=produit
            )

            data.append({
                "produit": produit.code,
                "stock_global": stock_global,
                "seuil_critique_percent": produit.seuil_critique_percent,
            })

        return Response(data)
