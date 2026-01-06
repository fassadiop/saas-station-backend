from django.db.models import Sum


def sum_montant(qs):
    """
    Retourne la somme des montants d'un queryset TransactionStation
    """
    return qs.aggregate(total=Sum("montant"))["total"] or 0
