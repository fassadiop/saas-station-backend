# dashboard/views.py
from django.db.models import Sum, Count
from django.db.models.functions import TruncDate
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from dashboard.permissions import DashboardPermission
from core.permissions import IsTenantAdminOnly
from core.models import Transaction, Projet, Membre, Cotisation
from django.contrib.auth import get_user_model

Utilisateur = get_user_model()

class DashboardView(APIView):
    permission_classes = [IsTenantAdminOnly]

    def get(self, request):
        user = request.user
        tenant = getattr(user, "tenant", None)

        if not tenant:
            return Response(
                {"detail": "Utilisateur sans tenant"},
                status=403
            )

        start_date = request.query_params.get("start_date")
        end_date = request.query_params.get("end_date")

        # =========================
        # TRANSACTIONS (BASE)
        # =========================
        qs_transactions = Transaction.objects.filter(
            tenant=tenant
        )

        if start_date:
            qs_transactions = qs_transactions.filter(date__gte=start_date)
        if end_date:
            qs_transactions = qs_transactions.filter(date__lte=end_date)

        # =========================
        # KPI
        # =========================
        total_recettes = (
            qs_transactions
            .filter(type="Recette")
            .aggregate(total=Sum("montant"))["total"]
            or 0
        )

        total_depenses = (
            qs_transactions
            .filter(type="Depense")
            .aggregate(total=Sum("montant"))["total"]
            or 0
        )

        solde = total_recettes - total_depenses

        # =========================
        # TAUX DE COTISATION
        # =========================
        membres_total = Membre.objects.filter(
            tenant=tenant,
        ).count()

        membres_a_jour = (
            Cotisation.objects.filter(
                membre__tenant=tenant,
                statut="Payé"
            )
            .values("membre")
            .distinct()
            .count()
        )

        taux_cotisation = (
            round((membres_a_jour / membres_total) * 100, 2)
            if membres_total > 0 else 0
        )

        # =========================
        # GRAPHIQUE RecetteS / DepenseS
        # =========================
        chart_qs = (
            qs_transactions
            .annotate(jour=TruncDate("date"))
            .values("jour", "type")
            .annotate(total=Sum("montant"))
            .order_by("jour")
        )

        chart_map = {}
        for item in chart_qs:
            jour = item["jour"].isoformat()
            if jour not in chart_map:
                chart_map[jour] = {
                    "date": jour,
                    "recettes": 0,
                    "depenses": 0,
                }

            if item["type"] == "Recette":
                chart_map[jour]["recettes"] = float(item["total"])
            elif item["type"] == "Depense":
                chart_map[jour]["depenses"] = float(item["total"])

        # =========================
        # DepenseS PAR CATEGORIE
        # =========================
        depenses_par_categorie = list(
            qs_transactions
            .filter(type="Depense")
            .values("categorie")
            .annotate(montant=Sum("montant"))
        )

        for d in depenses_par_categorie:
            d["montant"] = float(d["montant"])

        # =========================
        # PROJETS
        # =========================
        projets_data = []
        projets = Projet.objects.filter(
            tenant=tenant,
            statut="EN_COURS"
        )

        for p in projets:
            depenses = (
                Transaction.objects.filter(
                    tenant=tenant,
                    projet=p,
                    type="Depense"
                )
                .aggregate(total=Sum("montant"))["total"]
                or 0
            )

            taux = (
                round((depenses / p.budget) * 100, 2)
                if p.budget else 0
            )

            projets_data.append({
                "id": p.id,
                "nom": p.nom,
                "budget": float(p.budget),
                "depenses": float(depenses),
                "taux_execution": taux,
                "statut": p.statut,
            })

        # =========================
        # TRANSACTIONS RECENTES
        # =========================
        recent_transactions = list(
            qs_transactions
            .order_by("-date")[:5]
            .values(
                "id",
                "date",
                "type",
                "categorie",
                "montant",
                "mode_paiement"
            )
        )

        for t in recent_transactions:
            t["montant"] = float(t["montant"])
            t["date"] = t["date"].isoformat()

        # ---------------------------
        # STAFF (Collecteurs & Trésoriers)
        # ---------------------------
        staff_qs = Utilisateur.objects.filter(
            tenant=user.tenant,
            role__in=["Collecteur", "Tresorier"]
        )

        staff_total = staff_qs.count()
        collecteurs_count = staff_qs.filter(role="Collecteur").count()
        tresoriers_count = staff_qs.filter(role="Tresorier").count()

        # ---------------------------
        # STATS RECETTES PAR COLLECTEUR
        # ---------------------------
        recettes_par_collecteur = (
            Transaction.objects.filter(
                tenant=tenant,
                type="Recette",
                created_by__role="Collecteur"
            )
            .values(
                "created_by__id",
                "created_by__first_name",
                "created_by__last_name",
            )
            .annotate(total=Sum("montant"))
            .order_by("-total")
        )

        recettes_collecteurs = [
            {
                "id": r["created_by__id"],
                "nom": f'{r["created_by__first_name"]} {r["created_by__last_name"]}'.strip(),
                "total": r["total"],
            }
            for r in recettes_par_collecteur
        ]

        # =========================
        # RESPONSE
        # =========================
        return Response({
            "period": {
                "start_date": start_date,
                "end_date": end_date,
            },
            "kpis": {
                "solde": float(solde),
                "total_recettes": float(total_recettes),
                "total_depenses": float(total_depenses),
                "taux_cotisation": taux_cotisation,
            },
            "charts": {
                "recettes_depenses": list(chart_map.values()),
                "depenses_par_categorie": depenses_par_categorie,
            },
            "projets": projets_data,
            "recent_transactions": recent_transactions,
            "alerts": [],
            "staff": {
                "total": staff_total,
                "collecteurs": collecteurs_count,
                "tresoriers": tresoriers_count,
            },
            "staff_stats": {
                "recettes_par_collecteur": recettes_collecteurs
            }
        })
