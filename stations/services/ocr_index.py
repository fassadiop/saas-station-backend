import re
from decimal import Decimal, InvalidOperation

import pytesseract
from PIL import Image, ImageOps, ImageFilter


# ============================================================
# CONFIGURATION TESSERACT
# ============================================================

pytesseract.pytesseract.tesseract_cmd = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe"
)


# ============================================================
# OUTILS
# ============================================================

def _normaliser_texte(texte):
    """
    Nettoie le texte retourné par Tesseract.

    Exemple :
        "18 871,00" -> "18871,00"
        "18871.00"  -> "18871.00"
    """

    if not texte:
        return ""

    texte = texte.strip()

    # Suppression des espaces introduits dans les nombres.
    texte = re.sub(r"\s+", "", texte)

    # Certains OCR peuvent produire des caractères
    # parasites autour du nombre.
    texte = texte.replace("O", "0")
    texte = texte.replace("o", "0")
    texte = texte.replace("I", "1")
    texte = texte.replace("l", "1")

    return texte


def _extraire_nombres(texte):
    """
    Extrait les nombres présents dans un texte OCR.

    Accepte :
        18871
        18871.00
        18871,00
        18 871,00
    """

    texte = _normaliser_texte(texte)

    if not texte:
        return []

    matches = re.findall(
        r"\d+(?:[.,]\d+)?",
        texte,
    )

    valeurs = []

    for match in matches:

        valeur_txt = match.replace(",", ".")

        try:
            valeur = Decimal(valeur_txt)
        except InvalidOperation:
            continue

        valeurs.append(valeur)

    return valeurs


def _normaliser_valeur_avec_reference(
    valeur,
    index_debut=None,
):
    """
    Corrige certains cas classiques où Tesseract perd
    le séparateur décimal.

    Exemple :
        OCR = 1887100
        index début = 18860.00

        => proposition : 18871.00

    La correction n'est appliquée que lorsqu'elle est
    cohérente avec l'index de début.

    Sans index_debut, aucune correction arbitraire
    n'est effectuée.
    """

    if valeur is None:
        return None

    if index_debut is None:
        return valeur

    try:
        index_debut = Decimal(str(index_debut))
    except (InvalidOperation, TypeError, ValueError):
        return valeur

    # --------------------------------------------------------
    # Cas normal
    # --------------------------------------------------------

    if valeur >= index_debut:
        return valeur

    # --------------------------------------------------------
    # Cas où Tesseract a probablement concaténé deux
    # décimales à la fin du compteur.
    #
    # Exemple :
    #     1887100
    # devient
    #     18871.00
    # --------------------------------------------------------

    texte = format(valeur, "f")

    if (
        "." not in texte
        and len(texte) >= 3
        and texte.endswith("00")
    ):
        candidat = valeur / Decimal("100")

        if candidat >= index_debut:
            return candidat

    return valeur


def _score_candidat(
    valeur,
    confiance,
    index_debut=None,
):
    """
    Calcule un score métier/OCR.

    L'objectif est de privilégier :
    - une bonne confiance OCR ;
    - une valeur cohérente avec l'index début.
    """

    score = Decimal(str(confiance))

    if index_debut is not None:

        try:
            index_debut = Decimal(str(index_debut))

            # Une valeur inférieure à l'index début est
            # fortement pénalisée.
            if valeur < index_debut:
                score -= Decimal("100")

            else:
                # Une petite différence avec l'index début
                # est généralement plus plausible qu'une
                # énorme différence.
                difference = valeur - index_debut

                if difference <= Decimal("100000"):
                    score += Decimal("10")

        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):
            pass

    return score


# ============================================================
# OCR INDEX
# ============================================================

def extraire_index_ocr(
    photo_file,
    index_debut=None,
):
    """
    Extrait une proposition d'index depuis une photo.

    Paramètres
    ----------
    photo_file :
        fichier image envoyé à Tesseract.

    index_debut :
        index de début du relais.
        Facultatif mais fortement recommandé.

    Retour
    ------
    {
        "valeur": Decimal(...) | None,
        "confiance": Decimal(...) | None,
    }

    IMPORTANT
    ---------
    La valeur retournée est une proposition OCR.

    Cette fonction ne modifie jamais :
        RelaisIndex.index_fin
    """

    # --------------------------------------------------------
    # 1. OUVERTURE
    # --------------------------------------------------------

    photo_file.seek(0)

    image = Image.open(photo_file)

    # Respect de l'orientation EXIF des photos prises
    # avec un téléphone.
    image = ImageOps.exif_transpose(image)

    # --------------------------------------------------------
    # 2. PRÉTRAITEMENT
    # --------------------------------------------------------

    image = image.convert("L")

    largeur, hauteur = image.size

    # Agrandissement des petites images.
    if largeur < 1200:
        facteur = 2

        image = image.resize(
            (
                largeur * facteur,
                hauteur * facteur,
            )
        )

    # Amélioration du contraste.
    image = ImageOps.autocontrast(image)

    # Netteté.
    image = image.filter(
        ImageFilter.SHARPEN
    )

    # --------------------------------------------------------
    # 3. CONFIGURATIONS OCR
    # --------------------------------------------------------

    configs = [
        # Une seule ligne.
        (
            "--psm 7 "
            "-c tessedit_char_whitelist=0123456789.,"
        ),

        # Bloc de texte uniforme.
        (
            "--psm 6 "
            "-c tessedit_char_whitelist=0123456789.,"
        ),

        # Texte dispersé.
        (
            "--psm 11 "
            "-c tessedit_char_whitelist=0123456789.,"
        ),
    ]

    candidats = []

    # --------------------------------------------------------
    # 4. PLUSIEURS PASSES OCR
    # --------------------------------------------------------

    for config in configs:

        try:

            data = pytesseract.image_to_data(
                image,
                config=config,
                output_type=pytesseract.Output.DICT,
            )

        except Exception:
            continue

        textes = data.get("text", [])
        confiances = data.get("conf", [])

        for i, texte in enumerate(textes):

            texte = _normaliser_texte(texte)

            if not texte:
                continue

            valeurs = _extraire_nombres(
                texte
            )

            if not valeurs:
                continue

            # ------------------------------------------------
            # Confiance Tesseract
            # ------------------------------------------------

            confiance = Decimal("0")

            if i < len(confiances):

                try:
                    confiance = Decimal(
                        str(confiances[i])
                    )

                except (
                    InvalidOperation,
                    TypeError,
                    ValueError,
                ):
                    confiance = Decimal("0")

            # Tesseract peut retourner une confiance
            # négative pour certains éléments.
            if confiance < 0:
                confiance = Decimal("0")

            # ------------------------------------------------
            # Candidats
            # ------------------------------------------------

            for valeur in valeurs:

                valeur_corrigee = (
                    _normaliser_valeur_avec_reference(
                        valeur,
                        index_debut=index_debut,
                    )
                )

                score = _score_candidat(
                    valeur_corrigee,
                    confiance,
                    index_debut=index_debut,
                )

                candidats.append(
                    {
                        "valeur": valeur_corrigee,
                        "confiance": confiance,
                        "score": score,
                    }
                )

    # --------------------------------------------------------
    # 5. AUCUN CANDIDAT
    # --------------------------------------------------------

    if not candidats:
        return {
            "valeur": None,
            "confiance": None,
        }

    # --------------------------------------------------------
    # 6. MEILLEUR CANDIDAT
    # --------------------------------------------------------

    meilleur = max(
        candidats,
        key=lambda item: (
            item["score"],
            item["confiance"],
        ),
    )

    return {
        "valeur": meilleur["valeur"],
        "confiance": meilleur["confiance"],
    }