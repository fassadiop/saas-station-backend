from stations.services.stock import appliquer_stock_relais

def perform_update(self, serializer):
    ancien_statut = self.get_object().status
    relais = serializer.save()

    if ancien_statut != "TRANSFERE" and relais.status == "TRANSFERE":
        appliquer_stock_relais(relais)
