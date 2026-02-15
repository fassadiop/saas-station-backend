# stations/constants.py

from django.db import models


REGIONS_DEPARTEMENTS = {
    "Dakar": [
        "Dakar",
        "Guédiawaye",
        "Keur Massar",
        "Pikine",
        "Rufisque",
    ],
    "Thiès": [
        "Thiès",
        "Mbour",
        "Tivaouane",
    ],
    "Diourbel": [
        "Diourbel",
        "Bambey",
        "Mbacké",
    ],
    "Fatick": [
        "Fatick",
        "Foundiougne",
        "Gossas",
    ],
    "Kaolack": [
        "Kaolack",
        "Nioro du Rip",
    ],
    "Kaffrine": [
        "Kaffrine",
        "Birkelane",
        "Koungheul",
        "Malem Hodar",
    ],
    "Tambacounda": [
        "Tambacounda",
        "Bakel",
        "Goudiry",
        "Vélingara",
    ],
    "Kédougou": [
        "Kédougou",
        "Salémata",
        "Saraya",
    ],
    "Sédhiou": [
        "Sédhiou",
        "Bignona",
        "Goudomp",
    ],
    "Kolda": [
        "Kolda",
        "Médina Yoro Foulah",
        "Vélingara",
    ],
    "Ziguinchor": [
        "Ziguinchor",
        "Bignona",
        "Oussouye",
    ],
    "Louga": [
        "Louga",
        "Linguère",
        "Kébémer",
    ],
    "Matam": [
        "Matam",
        "Kanel",
        "Ranérou-Ferlo",
    ],
    "Saint-Louis": [
        "Saint-Louis",
        "Dagana",
        "Podor",
    ],
}

REGION_CHOICES = [(r, r) for r in REGIONS_DEPARTEMENTS.keys()]


class DepotageStatus(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMIS = "SOUMIS", "Soumis"
    CONFIRME = "CONFIRME", "Confirmé"


class RelaisStatus(models.TextChoices):
    BROUILLON = "BROUILLON", "Brouillon"
    SOUMIS = "SOUMIS", "Soumis"
    VALIDE = "VALIDE", "Validé"
    TRANSFERE = "TRANSFERE", "Transféré"
