# stations/services/cloture_journaliere.py

from decimal import Decimal
from django.db.models import Sum
from stations.models import (
    RelaisEquipe,
    RelaisIlot,
    Depense,
    DetteStation,
    RelaisEcart,
    EncaissementRelais,
    Versement,
)

def generer_cloture_journaliere(
    station,
    date_debut,
    date_fin,
):
    relais = RelaisEquipe.objects.filter(
        station=station,
        fin_relais__date__gte=date_debut,
        fin_relais__date__lte=date_fin,
        status=RelaisEquipe.Statut.TRANSFERE
    )

    total_volume = Decimal("0")
    total_theorique = Decimal("0")
    total_encaisse = Decimal("0")
    total_versements = Decimal("0")

    for relais_item in relais:

        total_volume += relais_item.total_volume_vendu
        total_theorique += relais_item.total_theorique
        total_encaisse += relais_item.total_encaisse

        for ilot in relais_item.ilots.all():
            total_versements += ilot.total_versement

    depenses = Depense.objects.filter(
        station=station,
        statut=Depense.Statut.VALIDE,
        date_depense__gte=date_debut,
        date_depense__lte=date_fin,
    )

    total_depenses = depenses.aggregate(
        total=Sum("montant")
    )["total"] or Decimal("0")

    credits = DetteStation.objects.filter(
        relais__station=station,
        relais__status=RelaisEquipe.Statut.TRANSFERE,
        relais__fin_relais__date__gte=date_debut,
        relais__fin_relais__date__lte=date_fin,
    )

    total_credits = credits.aggregate(
        total=Sum("montant_initial")
    )["total"] or Decimal("0")

    ecarts = RelaisEcart.objects.filter(
        relais__station=station,
        date_relais__gte=date_debut,
        date_relais__lte=date_fin,
    )

    ecarts_valides = ecarts.exclude(
        montant_theorique=0
    )

    total_ecarts = ecarts_valides.aggregate(
        total=Sum("montant")
    )["total"] or Decimal("0")

    solde_theorique = (
        total_encaisse
        - total_versements
        - total_depenses
    )

    resume = {
        "volume_vendu": float(total_volume),
        "vente_theorique": float(total_theorique),
        "encaissements": float(total_encaisse),
        "versements": float(total_versements),
        "depenses": float(total_depenses),
        "credits": float(total_credits),
        "ecarts": float(total_ecarts),
    }

    ilots_data = []

    for relais_item in relais:

        for ilot in relais_item.ilots.all():

            ilots_data.append({
                "relais_id": relais_item.id,
                "ilot": ilot.ilot.nom,
                "responsable": str(ilot.responsable),
                "volume_vendu": float(ilot.total_volume_vendu),
                "vente_theorique": float(ilot.total_theorique),
                "encaissements": float(ilot.total_encaisse),
                "versements": float(ilot.total_versement),
            })
    
    depenses_data = []

    for depense in depenses:

        depenses_data.append({
            "id": depense.id,
            "categorie": (
                depense.categorie.nom
                if depense.categorie
                else "-"
            ),
            "description": depense.description,
            "montant": float(depense.montant),
            "date": depense.date_depense.isoformat(),
            "statut": depense.statut,
        })

    depenses_bloc = {
        "total": float(total_depenses),
        "nombre": len(depenses_data),
        "details": depenses_data,
    }

    credits_data = []

    for dette in credits:

        credits_data.append({
            "id": dette.id,
            "client": str(dette.client),
            "produit": str(dette.produit),
            "volume": float(dette.volume),
            "prix_unitaire": float(dette.prix_unitaire),
            "montant_initial": float(dette.montant_initial),
            "montant_regle": float(dette.montant_regle),
            "reste": float(
                dette.montant_initial - dette.montant_regle
            ),
            "statut": dette.statut,
            "date": dette.created_at.date().isoformat(),
        })

    credits_bloc = {
        "total": float(total_credits),
        "nombre": len(credits_data),
        "details": credits_data,
    }

    ecarts_valides = ecarts.exclude(
        montant_theorique=0
    )

    ecarts_data = []

    for ecart in ecarts_valides:

        ecarts_data.append({
            "id": ecart.id,
            "responsable": str(ecart.responsable),
            "type": ecart.type_ecart,
            "montant": float(ecart.montant),
            "theorique": float(ecart.montant_theorique),
            "encaisse": float(ecart.montant_encaisse),
            "date": (
                ecart.date_relais.isoformat()
                if ecart.date_relais
                else None
            ),
        })

    total_manques = sum(
        float(e.montant)
        for e in ecarts_valides
        if e.type_ecart == "MANQUE"
    )

    total_excedents = sum(
        float(e.montant)
        for e in ecarts_valides
        if e.type_ecart == "EXCEDENT"
    )

    ecarts_bloc = {
        "total": float(
            ecarts_valides.aggregate(
                total=Sum("montant")
            )["total"] or 0
        ),
        "manques": total_manques,
        "excedents": total_excedents,
        "nombre": len(ecarts_data),
        "details": ecarts_data,
    }
    
    meta = {
        "station": station.nom,
        "date_debut": date_debut.isoformat(),
        "date_fin": date_fin.isoformat(),
        "nombre_relais": relais.count(),
        "nombre_ilots": len(ilots_data),
    }

    analyse = {
        "ecart_vente_encaissement": float(
            total_theorique - total_encaisse
        ),
        "taux_encaissement": round(
            (total_encaisse / total_theorique) * 100,
            2
        ) if total_theorique else 0,
        "taux_versement": round(
            (total_versements / total_encaisse) * 100,
            2
        ) if total_encaisse else 0,
    }
    
    return {
        "meta": meta,
        "resume": resume,
        "ilots": ilots_data,
        "depenses": depenses_bloc,
        "credits": credits_bloc,
        "ecarts": ecarts_bloc,
        "analyse": analyse,
        "synthese": {
            "solde_theorique": float(solde_theorique),
        },
    }

    