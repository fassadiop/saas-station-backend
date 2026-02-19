# accounts/constants.py (ou équivalent)

class UserRole:
    SUPERADMIN = "SUPERADMIN"
    ADMIN_TENANT_FINANCE = "ADMIN_TENANT_FINANCE"
    ADMIN_TENANT_STATION = "ADMIN_TENANT_STATION"

    GERANT = "GERANT"
    SUPERVISEUR = "SUPERVISEUR"
    POMPISTE = "POMPISTE"
    CAISSIER = "CAISSIER"
    PERSONNEL_ENTRETIEN = "PERSONNEL_ENTRETIEN"
    SECURITE = "SECURITE"
    TRESORIER = "TRESORIER"
    COLLECTEUR = "COLLECTEUR"

    CHOICES = [
        (SUPERADMIN, "Super Admin"),
        (ADMIN_TENANT_FINANCE, "Administrateur Finance"),
        (ADMIN_TENANT_STATION, "Administrateur Station"),
        (GERANT, "Chef de station"),
        (SUPERVISEUR, "Chef de piste"),
        (POMPISTE, "Agent de distribution"),
        (CAISSIER, "Vendeur boutique"),
        (PERSONNEL_ENTRETIEN, "Nettoyage"),
        (SECURITE, "Prévention des risques"),
        (TRESORIER, "Trésorier"),
        (COLLECTEUR, "Collecteur"),
    ]

class StationRoles:
    ALLOWED = (
        UserRole.GERANT,
        UserRole.SUPERVISEUR,
        UserRole.POMPISTE,
        UserRole.CAISSIER,
        UserRole.PERSONNEL_ENTRETIEN,
        UserRole.SECURITE,
    )