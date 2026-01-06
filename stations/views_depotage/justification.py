from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from stations.models import JustificationDepotage
from stations.serializers import JustificationDepotageSerializer


class JustificationDepotageViewSet(ModelViewSet):
    serializer_class = JustificationDepotageSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(justifie_par=self.request.user)
