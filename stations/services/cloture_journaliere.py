# stations/services/cloture_journaliere.py

from decimal import Decimal

from django.db.models import Sum

from accounts.constants import UserRole
from stations.models import (
    RelaisEquipe,
    Depense,
    DetteStation,
    RelaisEcart,
    RelaisJauge,
    VenteLubrifiant,
)

from stations.models_baie.operation import OperationBaie
from stations.models_depotage.mouvement_stock import MouvementStock


def generer_cloture_journaliere(
    station,
    date_debut,
    date_fin,
    user,
):

    # ==================================================
    # RELAIS DE LA PERIODE
    # ==================================================
    if user.role == UserRole.POMPISTE:

        relais_qs = (
            RelaisEquipe.objects
            .filter(
                station=station,
                equipe_entrante=user.get_full_name(),
                status=RelaisEquipe.Statut.TRANSFERE,
            )
            .order_by("-fin_relais")
        )

        relais_item = relais_qs.first()

        if not relais_item:
            raise ValueError(
                "Aucun relais transféré trouvé pour ce pompiste."
            )

        date_debut = relais_item.debut_relais.date()
        date_fin = relais_item.fin_relais.date()

        # Le relais réellement concerné
        relais_concernes = RelaisEquipe.objects.filter(
            pk=relais_item.pk
        )

    else:

        relais_concernes = (
            RelaisEquipe.objects
            .filter(
                station=station,
                fin_relais__date__gte=date_debut,
                fin_relais__date__lte=date_fin,
                status=RelaisEquipe.Statut.TRANSFERE,
            )
        )

    # ==================================================
    # TOTAUX GENERAUX
    # ==================================================

    total_volume = Decimal("0")
    total_theorique = Decimal("0")
    total_encaisse = Decimal("0")
    total_versements = Decimal("0")

    total_ventes_lubrifiants = Decimal("0")
    total_operations_baie = Decimal("0")

    # ==================================================
    # JAUGES
    # ==================================================

    jauges_data = []

    # ==================================================
    # VENTES LUBRIFIANTS
    # ==================================================

    ventes_lubrifiants_data = []

    # ==================================================
    # OPERATIONS DE BAIE
    # ==================================================

    operations_baie_data = []

    # ==================================================
    # PARCOURS DES RELAIS
    # ==================================================

    for relais_item in relais_concernes:

        # ----------------------------------------------
        # CARBURANTS
        # ----------------------------------------------

        total_volume += (
            relais_item.total_volume_vendu
        )

        total_theorique += (
            relais_item.total_theorique
        )

        total_encaisse += (
            relais_item.total_encaisse
        )

        # ----------------------------------------------
        # VERSEMENTS
        # ----------------------------------------------

        for ilot in relais_item.ilots.all():

            total_versements += (
                ilot.total_versement
            )

                # ----------------------------------------------
        # JAUGES / CONTROLE DE STOCK
        # ----------------------------------------------

        jauges_qs = (
            RelaisJauge.objects
            .filter(
                relais=relais_item
            )
            .select_related(
                "produit"
            )
            .order_by(
                "produit__code"
            )
        )

        for jauge in jauges_qs:

            produit = jauge.produit

            stock_depart = (
                jauge.jauge_debut
                or Decimal("0")
            )

            stock_reel_arrivee = (
                jauge.jauge_fin
                or Decimal("0")
            )

            # ------------------------------------------
            # DEPOTAGES
            # ------------------------------------------

            entrees_depotage = (
                MouvementStock.objects
                .filter(
                    station=relais_item.station,
                    cuve__produit=produit,
                    type_mouvement=MouvementStock.MOUVEMENT_ENTREE,
                    source_type="DEPOTAGE",
                    date_mouvement__gte=relais_item.debut_relais,
                    date_mouvement__lte=relais_item.fin_relais,
                )
                .aggregate(
                    total=Sum("quantite")
                )["total"]
                or Decimal("0")
            )

            # ------------------------------------------
            # VOLUME DISTRIBUE
            # ------------------------------------------

            volume_distribue = (
                MouvementStock.objects
                .filter(
                    station=relais_item.station,
                    cuve__produit=produit,
                    type_mouvement=MouvementStock.MOUVEMENT_SORTIE,
                    source_type="RELAIS",
                    source_id=relais_item.id,
                )
                .aggregate(
                    total=Sum("quantite")
                )["total"]
                or Decimal("0")
            )

            # ------------------------------------------
            # RETOURS EN CUVE
            # ------------------------------------------

            retour_cuve = (
                MouvementStock.objects
                .filter(
                    station=relais_item.station,
                    cuve__produit=produit,
                    type_mouvement=MouvementStock.MOUVEMENT_ENTREE,
                    source_type="RETOUR_CUVE",
                    source_id=relais_item.id,
                )
                .aggregate(
                    total=Sum("quantite")
                )["total"]
                or Decimal("0")
            )

            # ------------------------------------------
            # VOLUME REELLEMENT VENDU
            # ------------------------------------------

            volume_vendu = (
                volume_distribue
                - retour_cuve
            )

            # ------------------------------------------
            # STOCK THEORIQUE
            # ------------------------------------------

            stock_theorique = (
                stock_depart
                + entrees_depotage
                - volume_distribue
                + retour_cuve
            )

            # ------------------------------------------
            # ECART DE STOCK
            # ------------------------------------------

            ecart_stock = (
                stock_reel_arrivee
                - stock_theorique
            )

            # ------------------------------------------
            # INDEX DES POMPES
            # ------------------------------------------

            indexes_data = []

            for ilot in relais_item.ilots.all():

                for index in (
                    ilot.indexes
                    .select_related(
                        "index_pompe",
                        "index_pompe__pompe",
                        "index_pompe__produit",
                    )
                    .all()
                ):

                    # Le produit appartient à IndexPompe
                    if index.index_pompe.produit_id != produit.id:
                        continue

                    indexes_data.append({
                        "ilot": ilot.ilot.nom,
                        "pompe": str(index.index_pompe.pompe),

                        "index_debut": index.index_debut,
                        "index_fin": index.index_fin,

                        "volume": index.volume_vendu,

                        "retour_en_cuve": (
                            index.retour_en_cuve
                            or Decimal("0")
                        ),

                        "volume_reel": index.volume_reellement_vendu,

                        "prix_unitaire": index.prix_unitaire,

                        "montant": index.montant_theorique,
                    })

            jauges_data.append({

                "relais_id": relais_item.id,

                "produit": produit.nom,

                "produit_code": produit.code,

                "stock_depart": float(
                    stock_depart
                ),

                "entrees": float(
                    entrees_depotage
                ),

                "volume_distribue": float(
                    volume_distribue
                ),

                "retour_cuve": float(
                    retour_cuve
                ),

                "volume_vendu": float(
                    volume_vendu
                ),

                "stock_theorique": float(
                    stock_theorique
                ),

                "stock_reel_arrivee": float(
                    stock_reel_arrivee
                ),

                "indexes": indexes_data,

                "ecart_negatif": ecart_stock < 0,
                "ecart_positif": ecart_stock > 0,

            })

        # ----------------------------------------------
        # VENTES LUBRIFIANTS
        # ----------------------------------------------

        ventes_qs = (
            VenteLubrifiant.objects
            .filter(
                relais=relais_item
            )
            .select_related(
                "lubrifiant"
            )
            .order_by(
                "lubrifiant__designation",
                "id"
            )
        )

        for vente in ventes_qs:

            montant = (
                vente.montant
                or Decimal("0")
            )

            total_ventes_lubrifiants += (
                montant
            )

            ventes_lubrifiants_data.append({

                "relais_id": relais_item.id,

                "lubrifiant": str(
                    vente.lubrifiant
                ),

                "quantite": float(
                    vente.quantite
                ),

                "prix_unitaire": float(
                    vente.prix_unitaire
                ),

                "montant": float(
                    montant
                ),

                "date": (
                    vente.date_vente.isoformat()
                    if vente.date_vente
                    else None
                ),

            })

        # ----------------------------------------------
        # OPERATIONS DE BAIE
        # ----------------------------------------------

        operations_qs = (
            OperationBaie.objects
            .filter(
                relais=relais_item
            )
            .select_related(
                "prestation"
            )
            .order_by(
                "prestation__designation",
                "id"
            )
        )

        for operation in operations_qs:

            montant = (
                operation.montant
                or Decimal("0")
            )

            total_operations_baie += (
                montant
            )

            operations_baie_data.append({

                "relais_id": relais_item.id,

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

                "date": (
                    operation.created_at.isoformat()
                    if operation.created_at
                    else None
                ),

            })

    # ==================================================
    # DEPENSES
    # ==================================================

    depenses = Depense.objects.filter(
        relais__in=relais_concernes,
        statut=Depense.Statut.VALIDE,
    )

    total_depenses = (
        depenses.aggregate(
            total=Sum("montant")
        )["total"]
        or Decimal("0")
    )

    # ==================================================
    # CREDITS
    # ==================================================

    credits = DetteStation.objects.filter(
        relais__in=relais_concernes
    )

    total_credits = (
        credits.aggregate(
            total=Sum("montant_initial")
        )["total"]
        or Decimal("0")
    )

    # ==================================================
    # ECARTS
    # ==================================================

    ecarts = RelaisEcart.objects.filter(
        relais__in=relais_concernes
    )

    ecarts_valides = ecarts.exclude(
        montant_theorique=0
    )

    total_ecarts = (
        ecarts_valides.aggregate(
            total=Sum("montant")
        )["total"]
        or Decimal("0")
    )

    # ==================================================
    # SOLDE THEORIQUE
    # ==================================================

    solde_theorique = (
        total_encaisse
        - total_versements
        - total_depenses
    )

    # ==================================================
    # RESUME
    # ==================================================

    resume = {

        "volume_vendu": float(
            total_volume
        ),

        "vente_theorique": float(
            total_theorique
        ),

        "encaissements": float(
            total_encaisse
        ),

        "versements": float(
            total_versements
        ),

        "ventes_lubrifiants": float(
            total_ventes_lubrifiants
        ),

        "operations_baie": float(
            total_operations_baie
        ),

        "depenses": float(
            total_depenses
        ),

        "credits": float(
            total_credits
        ),

        "ecarts": float(
            total_ecarts
        ),

    }

    # ==================================================
    # ILOTS
    # ==================================================

    ilots_data = []

    for relais_item in relais_concernes:

        for ilot in relais_item.ilots.all():

            ilots_data.append({

                "relais_id": relais_item.id,

                "ilot": ilot.ilot.nom,

                "responsable": str(
                    ilot.responsable
                ),

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
                    ilot.total_versement
                ),

            })

    # ==================================================
    # DEPENSES DETAIL
    # ==================================================

    depenses_data = []

    for depense in depenses:

        depenses_data.append({

            "id": depense.id,

            "categorie": (
                depense.categorie.nom
                if depense.categorie
                else "-"
            ),

            "description": (
                depense.description
            ),

            "montant": float(
                depense.montant
            ),

            "date": (
                depense.date_depense.isoformat()
            ),

            "statut": depense.statut,

        })

    depenses_bloc = {

        "total": float(
            total_depenses
        ),

        "nombre": len(
            depenses_data
        ),

        "details": depenses_data,

    }

    # ==================================================
    # CREDITS DETAIL
    # ==================================================

    credits_data = []

    for dette in credits:

        credits_data.append({

            "id": dette.id,

            "client": str(
                dette.client
            ),

            "produit": str(
                dette.produit
            ),

            "volume": float(
                dette.volume
            ),

            "prix_unitaire": float(
                dette.prix_unitaire
            ),

            "montant_initial": float(
                dette.montant_initial
            ),

            "montant_regle": float(
                dette.montant_regle
            ),

            "reste": float(
                dette.montant_initial
                - dette.montant_regle
            ),

            "statut": dette.statut,

            "date": (
                dette.created_at
                .date()
                .isoformat()
            ),

        })

    credits_bloc = {

        "total": float(
            total_credits
        ),

        "nombre": len(
            credits_data
        ),

        "details": credits_data,

    }

    # ==================================================
    # ECARTS DETAIL
    # ==================================================

    ecarts_valides = (
        ecarts
        .exclude(
            montant_theorique=0
        )
    )

    ecarts_data = []

    for ecart in ecarts_valides:

        ecarts_data.append({

            "id": ecart.id,

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

            "date": (
                ecart.date_relais.isoformat()
                if ecart.date_relais
                else None
            ),

        })

    # ==================================================
    # TOTAUX ECARTS
    # ==================================================

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
            )["total"]
            or 0

        ),

        "manques": total_manques,

        "excedents": total_excedents,

        "nombre": len(
            ecarts_data
        ),

        "details": ecarts_data,

    }

    # ==================================================
    # META
    # ==================================================

    meta = {

        "station": station.nom,

        "date_debut": (
            date_debut.isoformat()
        ),

        "date_fin": (
            date_fin.isoformat()
        ),

        "nombre_relais": relais_concernes.count(),

        "nombre_ilots": len(
            ilots_data
        ),

    }

    # ==================================================
    # ANALYSE
    # ==================================================

    analyse = {

        "ecart_vente_encaissement": float(
            total_theorique
            - total_encaisse
        ),

        "taux_encaissement": round(

            (
                total_encaisse
                / total_theorique
            ) * 100,

            2

        )
        if total_theorique
        else 0,

        "taux_versement": round(

            (
                total_versements
                / total_encaisse
            ) * 100,

            2

        )
        if total_encaisse
        else 0,

    }

    # ==================================================
    # NOMBRE TOTAL D'INDEX
    # ==================================================

    nombre_indexes = sum(
        len(jauge.get("indexes", []))
        for jauge in jauges_data
    )

    # ==================================================
    # RETOUR
    # ==================================================

    return {

        "meta": meta,

        "resume": resume,

        "ilots": ilots_data,

        "jauges": jauges_data,

        "nombre_indexes": nombre_indexes,

        "ventes_lubrifiants": (
            ventes_lubrifiants_data
        ),

        "operations_baie": (
            operations_baie_data
        ),

        "depenses": depenses_bloc,

        "credits": credits_bloc,

        "ecarts": ecarts_bloc,

        "analyse": analyse,

        "synthese": {

            "solde_theorique": float(
                solde_theorique
            ),

        },

    }