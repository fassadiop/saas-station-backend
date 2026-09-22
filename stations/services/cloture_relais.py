from decimal import Decimal
from django.db.models import Sum
from stations.models import (
    RelaisEcart,
    EncaissementRelais,
    DetteStation,
    RelaisJauge,
    VenteLubrifiant,
)
from stations.models_baie.operation import OperationBaie

def generer_cloture_relais(relais):

    # ==================================================
    # META
    # ==================================================

    meta = {
        "tenant": relais.tenant.nom,
        "relais_id": relais.id,
        "station": relais.station.nom,
        "date_debut": relais.debut_relais.isoformat(),
        "date_fin": relais.fin_relais.isoformat(),
        "statut": relais.status,
    }

    # ==================================================
    # EQUIPES
    # ==================================================

    equipes = {
        "sortante": relais.equipe_sortante,
        "entrante": relais.equipe_entrante,
    }

    # ==================================================
    # ILOTS
    # ==================================================

    ilots_data = []
    indexes_data = []

    total_versements = Decimal("0")

    # ==================================================
    # JAUGES
    # ==================================================

    jauges_data = []

    jauges_qs = (
        RelaisJauge.objects
        .filter(relais=relais)
        .select_related("produit")
        .order_by("produit__code")
    )

    for jauge in jauges_qs:

        jauges_data.append({
            "produit": jauge.produit.nom,
            "produit_code": jauge.produit.code,

            "stock_depart": float(
                jauge.jauge_debut
                or Decimal("0")
            ),

            "stock_reel_arrivee": float(
                jauge.jauge_fin
                or Decimal("0")
            ),
        })

    # ==================================================
    # VENTES LUBRIFIANTS
    # ==================================================

    ventes_lubrifiants_qs = (
        VenteLubrifiant.objects
        .filter(relais=relais)
        .select_related("lubrifiant")
        .order_by("lubrifiant__designation", "id")
    )

    ventes_lubrifiants_data = []

    total_ventes_lubrifiants = Decimal("0")

    for vente in ventes_lubrifiants_qs:

        montant = vente.montant or Decimal("0")

        total_ventes_lubrifiants += montant

        ventes_lubrifiants_data.append({
            "lubrifiant": str(vente.lubrifiant),
            "quantite": float(
                vente.quantite
            ),
            "prix_unitaire": float(
                vente.prix_unitaire
            ),
            "montant": float(
                montant
            ),
        })

    # ==================================================
    # OPERATIONS DE BAIE
    # ==================================================

    operations_baie_qs = (
        OperationBaie.objects
        .filter(relais=relais)
        .select_related("prestation")
        .order_by("prestation__designation", "id")
    )

    operations_baie_data = []

    total_operations_baie = Decimal("0")

    for operation in operations_baie_qs:

        montant = operation.montant or Decimal("0")

        total_operations_baie += montant

        operations_baie_data.append({
            "prestation": str(
                operation.prestation
            ),
            "quantite": float(
                operation.quantite
            ),
            "prix_unitaire": float(
                operation.prix_unitaire
            ),
            "montant": float(
                montant
            ),
        })

    # ==================================================
    # ILOTS
    # ==================================================
    for ilot in relais.ilots.all():

        versement = ilot.total_versement

        solde_ilot = (
            ilot.total_encaisse
            - ilot.total_versement
        )

        total_versements += versement

        ilots_data.append({
            "ilot": ilot.ilot.nom,
            "responsable": str(ilot.responsable),
            "volume_vendu": float(
                ilot.total_volume_vendu
            ),
            "vente_theorique": float(
                ilot.total_theorique
            ),
            "encaissements": float(
                ilot.total_encaisse
            ),
            "versements": float(
                versement
            ),
            "solde": float(solde_ilot),
        })

        for index in ilot.indexes.all():

            indexes_data.append({
                "ilot": ilot.ilot.nom,

                "responsable": str(
                    ilot.responsable
                ),

                "pompe": (
                    f"{index.index_pompe.pompe.reference}"
                ),

                "produit": (
                    index.index_pompe
                    .produit
                    .code
                ),

                "face": (
                    index.index_pompe
                    .face
                ),

                "index_debut": float(
                    index.index_debut
                ),

                "index_fin": float(
                    index.index_fin or 0
                ),

                "volume": float(
                    index.volume_vendu
                ),

                "prix_unitaire": float(
                    index.prix_unitaire or 0
                ),

                "montant_theorique": float(
                    index.montant_theorique or 0
                ),
            })
    

    # ==================================================
    # ENCAISSEMENTS
    # ==================================================

    encaissements_qs = EncaissementRelais.objects.filter(
        relais_ilot__relais=relais
    )

    total_encaissements = (
        encaissements_qs.aggregate(
            total=Sum("montant")
        )["total"]
        or Decimal("0")
    )

    encaissements_par_mode = []

    for mode in (
        encaissements_qs
        .values("mode_paiement__nom")
        .annotate(
            total=Sum("montant")
        )
    ):

        montant = mode["total"] or Decimal("0")

        pourcentage = (
            (montant / total_encaissements) * 100
            if total_encaissements > 0
            else Decimal("0")
        )

        encaissements_par_mode.append({
            "mode": mode["mode_paiement__nom"],
            "montant": float(montant),
            "pourcentage": round(
                float(pourcentage),
                2
            ),
        })


    credits_qs = DetteStation.objects.filter(
        relais=relais
    )

    credits_data = {
        "nombre": credits_qs.count(),
        "montant_total": float(
            credits_qs.aggregate(
                total=Sum("montant_initial")
            )["total"] or 0
        )
    }

    # ==================================================
    # ECARTS
    # ==================================================

    ecarts_qs = RelaisEcart.objects.filter(
        relais=relais
    ).exclude(
        montant_theorique=0
    )

    ecarts_data = []

    total_manques = Decimal("0")
    total_excedents = Decimal("0")

    for ecart in ecarts_qs:

        if ecart.type_ecart == "MANQUE":
            total_manques += ecart.montant

        if ecart.type_ecart == "EXCEDENT":
            total_excedents += ecart.montant

        ecarts_data.append({
            "responsable": str(
                ecart.responsable
            ),
            "type": ecart.type_ecart,
            "montant": float(
                ecart.montant
            ),
            "theorique": float(
                ecart.montant_theorique
            ),
            "encaisse": float(
                ecart.montant_encaisse
            ),
        })

    # ==================================================
    # RESUME
    # ==================================================

    resume = {
        "volume_vendu": float(
            relais.total_volume_vendu
        ),
        "vente_theorique": float(
            relais.total_theorique
        ),
        "encaissements": float(
            relais.total_encaisse
        ),
        "versements": float(
            total_versements
        ),
    }

    # ==================================================
    # SYNTHESE
    # ==================================================

    solde = (
        relais.total_encaisse
        - total_versements
    )

    synthese = {
        "nombre_ilots": relais.ilots.count(),
        "solde": float(solde),
        "manques": float(total_manques),
        "excedents": float(total_excedents),
    }

    return {
        "meta": meta,
        "equipes": equipes,
        "resume": resume,
        "ilots": ilots_data,
        "indexes": indexes_data,
        "jauges": jauges_data,
        "ventes_lubrifiants": ventes_lubrifiants_data,
        "operations_baie": operations_baie_data,
        "encaissements": {
            "total": float(total_encaissements),
            "par_mode": encaissements_par_mode,
        },
        "credits": credits_data,
        "ecarts": ecarts_data,
        "synthese": synthese,
    }