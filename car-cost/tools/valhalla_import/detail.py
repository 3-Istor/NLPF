"""Le détail que les fichiers Valhalla ne donnent pas : composants, matières, zones.

Les fichiers source s'arrêtent au premier niveau : « Culasse », « Porte dièdre »,
« Inverter moteur ». Tout ce qui est ici est **SYNTHÉTIQUE** et déterministe :
des décompositions plausibles, écrites en clair pour être relues, pas des
données constructeur.

Trois enrichissements :

- **Décomposition.** Une pièce achetée assez chère, dont le libellé correspond
  à une famille, devient un ensemble fabriqué : ses composants propres, des
  matières en kg et de la petite visserie standard. Certains composants se
  décomposent à leur tour (carte électronique, stator).
- **Matières et standards partagés.** Comme sur le Multipla, une matière ou une
  pièce standard est une seule pièce, consommée par des dizaines de parents.
- **Zones.** Les pièces d'un même emplacement (coin de suspension, siège,
  banc de culasse) sont regroupées dans un sous-ensemble compté × n.

Le coût de référence est **conservé au centime** : le prix d'une pièce
décomposée est réparti entre ses enfants et sa main-d'œuvre, et un composant de
quantité 1 absorbe l'arrondi. La masse unitaire aussi. Seul le CO2 change : il
est recalculé composant par composant.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from tools.bom_generator.price_drivers import normalize

from . import enrich

SCALE6 = Decimal("0.000001")
KG = Decimal("0.001")

#: En dessous de ce prix unitaire, une pièce reste achetée telle quelle : on ne
#: décompose pas un capteur à 70 €.
MIN_PRICE_EUR = Decimal("250")
#: Matières, standards et main-d'œuvre ne prennent jamais plus que cette part
#: du prix : le reste va aux composants propres, qui doivent rester crédibles.
MAX_FIXED_SHARE = Decimal("0.5")
#: Idem pour la masse : matières et standards n'en prennent pas plus.
MAX_FIXED_MASS_SHARE = Decimal("0.8")


# -- matières : libellé, profil, EUR/kg, kg CO2e/kg, fournisseur ----------------
MATERIALS: dict[str, tuple[str, str, str, str, str]] = {
    "PREPREG": ("Préimprégné carbone/époxy", "composite", "85.00", "28.00", "SUP-CARBONIA"),
    "HONEYCOMB": ("Âme nid d'abeille aramide", "composite", "62.00", "21.00", "SUP-MIDLANDS-COMP"),
    "CSIC": ("Carbone-céramique C/SiC", "composite", "210.00", "38.00", "SUP-CARBONIA"),
    "ALU-BILLET": ("Billette aluminium 7075", "aluminium", "9.50", "11.20", "SUP-SAXONIA"),
    "ALU-CAST": ("Alliage aluminium de fonderie A357", "aluminium", "6.20", "9.40", "SUP-CASTELLO"),
    "STEEL-FORGED": ("Acier forgé 42CrMo4", "steel", "3.40", "2.40", "SUP-BLACKCOUNTRY"),
    "INCONEL": ("Superalliage base nickel 625", "steel", "55.00", "14.50", "SUP-CASTELLO"),
    "TITANIUM": ("Titane Ti-6Al-4V", "steel", "38.00", "35.00", "SUP-SAXONIA"),
    "COPPER": ("Cuivre électrolytique", "cable", "11.00", "4.20", "SUP-OBERLAND-ELEK"),
    "FESI": ("Tôle électrique fer-silicium", "motor", "3.80", "2.60", "SUP-VOLTARIS"),
    "NDFEB": ("Aimant fritté NdFeB", "motor", "95.00", "30.00", "SUP-VOLTARIS"),
    "LEATHER": ("Cuir pleine fleur", "default", "48.00", "17.00", "SUP-SEVERN-RUBBER"),
    "ALCANTARA": ("Microfibre suédée", "default", "70.00", "12.00", "SUP-SEVERN-RUBBER"),
    "PU-FOAM": ("Mousse polyuréthane", "rubber", "6.00", "4.20", "SUP-SEVERN-RUBBER"),
    "EPDM": ("Caoutchouc EPDM", "rubber", "4.20", "3.00", "SUP-SEVERN-RUBBER"),
    "LAMINATED-GLASS": ("Verre feuilleté", "default", "7.50", "1.40", "SUP-BLACKCOUNTRY"),
    "POLYCARBONATE": ("Polycarbonate optique", "default", "6.80", "5.50", "SUP-MIDLANDS-COMP"),
    "PA66-GF": ("Polyamide 6.6 chargé verre", "default", "5.20", "6.40", "SUP-MIDLANDS-COMP"),
}

# -- standards : libellé, profil, EUR, kg, kg CO2e, fournisseur -----------------
COMMONS: dict[str, tuple[str, str, str, str, str, str]] = {
    "VIS-TORX-M5": ("Vis Torx M5 inox", "fastener", "0.42", "0.004", "0.012", "SUP-PENNINE-FIX"),
    "VIS-TORX-M6": ("Vis Torx M6 titane", "fastener", "2.80", "0.005", "0.180", "SUP-PENNINE-FIX"),
    "INSERT-M6": ("Insert fileté M6 à coller", "fastener", "1.90", "0.006", "0.020", "SUP-PENNINE-FIX"),
    "RIVET": ("Rivet aveugle aluminium", "fastener", "0.18", "0.002", "0.020", "SUP-PENNINE-FIX"),
    "JOINT-TORIQUE": ("Joint torique FKM", "rubber", "0.65", "0.002", "0.008", "SUP-SEVERN-RUBBER"),
    "BAGUE-ETANCHEITE": ("Bague d'étanchéité à lèvre", "rubber", "3.40", "0.015", "0.050", "SUP-SEVERN-RUBBER"),
    "SILENTBLOC": ("Silentbloc caoutchouc-métal", "rubber", "14.00", "0.180", "0.600", "SUP-SEVERN-RUBBER"),
    "ROULEMENT-BILLES": ("Roulement à billes hybride céramique", "steel", "38.00", "0.120", "0.400", "SUP-SAXONIA"),
    "ROULEMENT-AIGUILLES": ("Roulement à aiguilles", "steel", "12.00", "0.040", "0.130", "SUP-SAXONIA"),
    "CIRCLIP": ("Circlip acier", "steel", "0.35", "0.003", "0.008", "SUP-SAXONIA"),
    "CONNECTEUR-LV": ("Connecteur étanche basse tension", "electronics", "6.50", "0.020", "0.600", "SUP-THAMES-ELEC"),
    "CONNECTEUR-HV": ("Connecteur haute tension blindé", "electronics", "42.00", "0.110", "2.800", "SUP-THAMES-ELEC"),
    "MICROCONTROLEUR": ("Microcontrôleur automobile 32 bits", "electronics", "18.00", "0.003", "1.900", "SUP-OBERLAND-ELEK"),
    "CONDENSATEUR": ("Condensateur céramique multicouche", "electronics", "0.08", "0.0005", "0.020", "SUP-OBERLAND-ELEK"),
    "THERMISTANCE": ("Thermistance CTN", "electronics", "1.20", "0.001", "0.050", "SUP-OBERLAND-ELEK"),
    "CAPTEUR-HALL": ("Capteur à effet Hall", "electronics", "4.80", "0.004", "0.200", "SUP-THAMES-ELEC"),
    "LED": ("Diode LED haute puissance", "electronics", "1.60", "0.001", "0.080", "SUP-THAMES-ELEC"),
    "MOSFET-SIC": ("Transistor de puissance SiC", "electronics", "24.00", "0.010", "1.500", "SUP-OBERLAND-ELEK"),
}


@dataclass(frozen=True)
class Component:
    """Un composant propre à la pièce décomposée : sa référence en dérive."""

    key: str
    label: str
    quantity: int
    weight: int
    profile: str
    #: Famille de second niveau : le composant se décompose à son tour.
    detail: str | None = None


@dataclass(frozen=True)
class Family:
    name: str
    #: Expression sur le libellé normalisé (minuscules, sans accent).
    pattern: str
    components: tuple[Component, ...]
    #: (matière, part de la masse de la pièce)
    materials: tuple[tuple[str, str], ...] = ()
    #: (standard, quantité)
    commons: tuple[tuple[str, int], ...] = ()
    labour_minutes: int = 12


C = Component

#: L'ordre compte : la première famille dont le motif correspond l'emporte. Le
#: premier composant de chaque famille est de quantité 1 : il absorbe l'arrondi.
FAMILIES: tuple[Family, ...] = (
    Family("moteur_electrique", r"^(moteur electrique|emotor|e motor|edu avant|moteur epas|machine electrique)", (
        C("STATOR", "Stator bobiné", 1, 5, "motor", "stator"),
        C("ROTOR", "Rotor à aimants permanents", 1, 4, "motor"),
        C("CARTER", "Carter moteur à chemise d'eau", 1, 2, "aluminium"),
        C("RESOLVEUR", "Résolveur de position", 1, 1, "electronics"),
        C("FLASQUE", "Flasque palier", 2, 1, "aluminium"),
    ), materials=(("NDFEB", "0.04"),), commons=(
        ("ROULEMENT-BILLES", 2), ("BAGUE-ETANCHEITE", 2), ("CONNECTEUR-HV", 1),
        ("CAPTEUR-HALL", 1), ("VIS-TORX-M6", 12),
    ), labour_minutes=35),
    Family("electronique_puissance", r"^(inverter|onduleur|dc dc|on board charger|chargeur|hv junction|convertisseur)", (
        C("CARTE-COMMANDE", "Carte de commande", 1, 3, "electronics", "carte"),
        C("MODULE-PUISSANCE", "Module de puissance", 1, 5, "electronics"),
        C("BOITIER", "Boîtier moulé étanche", 1, 2, "aluminium"),
        C("PLAQUE-FROIDE", "Plaque froide à liquide", 1, 2, "aluminium"),
        C("BUSBAR", "Barre de puissance", 3, 1, "cable"),
        C("CONDENSATEUR-BUS", "Condensateur de bus continu", 1, 1, "electronics"),
    ), materials=(("COPPER", "0.06"),), commons=(
        ("CONNECTEUR-HV", 2), ("CONNECTEUR-LV", 1), ("MOSFET-SIC", 6),
        ("THERMISTANCE", 3), ("JOINT-TORIQUE", 4), ("VIS-TORX-M5", 16),
    ), labour_minutes=30),
    Family("calculateur", r"^(ecu|calculateur|controleur|bms|bcm|tcu|vcu|gateway|passerelle|amplificateur|"
           r"head unit|mechatronic|module de commande)", (
        C("CARTE", "Carte électronique", 1, 5, "electronics", "carte"),
        C("BOITIER", "Boîtier", 1, 2, "aluminium"),
        C("COUVERCLE", "Couvercle", 1, 1, "default"),
        C("DISSIPATEUR", "Dissipateur thermique", 1, 1, "aluminium"),
    ), commons=(
        ("CONNECTEUR-LV", 2), ("JOINT-TORIQUE", 1), ("VIS-TORX-M5", 6),
    ), labour_minutes=10),
    Family("capteur_vision", r"^(camera|radar|lidar|ecran|afficheur|combine|affichage tete haute)", (
        C("MODULE", "Module optique ou d'affichage", 1, 5, "electronics"),
        C("CARTE", "Carte de traitement", 1, 3, "electronics", "carte"),
        C("BOITIER", "Boîtier", 1, 1, "default"),
        C("SUPPORT", "Support de fixation", 1, 1, "aluminium"),
    ), commons=(("CONNECTEUR-LV", 1), ("VIS-TORX-M5", 4)), labour_minutes=8),
    Family("pack_batterie", r"^(pack batterie|boitier batterie)", (
        C("BOITIER", "Bac structurel", 1, 4, "aluminium"),
        C("PLAQUE-FROIDE", "Plaque de refroidissement", 2, 2, "aluminium"),
        C("BUSBAR", "Barres de liaison des modules", 6, 1, "cable"),
        C("CONTACTEUR", "Contacteur principal", 2, 2, "electronics"),
        C("FUSIBLE", "Fusible pyrotechnique", 1, 1, "electronics"),
        C("COUVERCLE", "Couvercle composite", 1, 2, "composite"),
    ), materials=(("COPPER", "0.03"),), commons=(
        ("CONNECTEUR-HV", 2), ("THERMISTANCE", 8), ("JOINT-TORIQUE", 6), ("VIS-TORX-M6", 40),
    ), labour_minutes=60),
    Family("module_batterie", r"^modules batterie", (
        C("CARTER", "Carter de module", 1, 3, "aluminium"),
        C("CARTE", "Carte de surveillance des cellules", 1, 2, "electronics", "carte"),
        C("BUSBAR", "Barre de liaison des cellules", 4, 1, "cable"),
        C("ISOLANT", "Isolant thermique inter-cellules", 1, 1, "default"),
    ), materials=(("COPPER", "0.02"),), commons=(("THERMISTANCE", 4), ("CONNECTEUR-LV", 1)),
        labour_minutes=20),
    Family("airbag", r"^airbag", (
        C("COUSSIN", "Coussin textile plié", 1, 3, "default"),
        C("GENERATEUR", "Générateur de gaz", 1, 3, "steel"),
        C("BOITIER", "Boîtier et couvercle", 1, 1, "default"),
    ), commons=(("CONNECTEUR-LV", 1), ("VIS-TORX-M5", 4)), labour_minutes=8),
    Family("boite", r"^(boite dct|boite de vitesses|e diff arriere|differentiel|reducteur)", (
        C("CARTER", "Carter de boîte", 1, 3, "aluminium"),
        C("PIGNONNERIE", "Jeu de pignons", 1, 5, "steel"),
        C("ARBRE-PRIMAIRE", "Arbre primaire", 1, 2, "steel"),
        C("ARBRE-SECONDAIRE", "Arbre secondaire", 1, 2, "steel"),
        C("EMBRAYAGE", "Embrayage multidisque", 2, 2, "steel"),
        C("POMPE-HUILE", "Pompe à huile", 1, 1, "steel"),
    ), materials=(("STEEL-FORGED", "0.10"),), commons=(
        ("ROULEMENT-BILLES", 6), ("ROULEMENT-AIGUILLES", 4), ("BAGUE-ETANCHEITE", 4),
        ("CIRCLIP", 12), ("CAPTEUR-HALL", 3), ("VIS-TORX-M6", 24),
    ), labour_minutes=45),
    Family("moteur_thermique", r"^(bloc cylindres|culasse|vilebrequin plat|arbres a cames|carter|collecteur admission)", (
        C("BRUT", "Brut de fonderie", 1, 4, "aluminium"),
        C("USINAGE", "Reprise d'usinage et traitement", 1, 3, "aluminium"),
        C("BAGUE", "Bague de guidage", 4, 1, "steel"),
        C("BOUCHON", "Bouchon d'expansion", 4, 1, "steel"),
    ), materials=(("ALU-CAST", "0.05"),), commons=(
        ("JOINT-TORIQUE", 6), ("VIS-TORX-M6", 10),
    ), labour_minutes=40),
    Family("turbo", r"^(turbocompresseur|wastegate)", (
        C("CARTER-TURBINE", "Carter de turbine", 1, 3, "steel"),
        C("ROUE-TURBINE", "Roue de turbine", 1, 3, "steel"),
        C("ROUE-COMPRESSEUR", "Roue de compresseur", 1, 2, "aluminium"),
        C("CARTER-CENTRAL", "Carter central", 1, 2, "steel"),
        C("ACTIONNEUR", "Actionneur de décharge", 1, 1, "electronics"),
    ), materials=(("INCONEL", "0.08"),), commons=(
        ("ROULEMENT-BILLES", 2), ("JOINT-TORIQUE", 4),
    ), labour_minutes=20),
    Family("echappement", r"^(collecteur echappement|downpipe|silencieux|catalyseur|filtre s particules|"
           r"sorties)", (
        C("TUBULURE", "Tubulure formée", 1, 4, "steel"),
        C("BRIDE", "Bride usinée", 2, 1, "steel"),
        C("ECRAN", "Écran thermique", 1, 1, "steel"),
        C("SUPPORT", "Support élastique", 2, 1, "rubber"),
    ), materials=(("INCONEL", "0.15"),), commons=(("VIS-TORX-M6", 6),), labour_minutes=15),
    Family("frein", r"^(etrier|disque)", (
        C("CORPS", "Corps", 1, 5, "aluminium"),
        C("PISTON", "Piston", 6, 1, "steel"),
        C("JOINT", "Joint de piston", 6, 1, "rubber"),
        C("PURGEUR", "Vis de purge", 2, 1, "steel"),
    ), materials=(("CSIC", "0.10"),), commons=(("BAGUE-ETANCHEITE", 1), ("VIS-TORX-M6", 4)),
        labour_minutes=15),
    Family("amortisseur", r"^(amortisseur|verin|actionneur hydraulique|actionneurs? (aile|lift))", (
        C("CORPS", "Corps et réservoir", 1, 4, "steel"),
        C("TIGE", "Tige chromée", 1, 2, "steel"),
        C("PISTON", "Piston et clapets", 1, 2, "steel"),
        C("VALVE", "Valve pilotée", 1, 2, "electronics"),
    ), commons=(("SILENTBLOC", 2), ("BAGUE-ETANCHEITE", 2), ("JOINT-TORIQUE", 4)),
        labour_minutes=20),
    Family("liaison_sol", r"^(porte moyeu|bras|sous cadre|traverse|crash box|rocker|pushrod|lien \d|"
           r"biellette|barre antiroulis|cremaillere|colonne de direction|demi arbre|pylones)", (
        C("CORPS", "Corps usiné", 1, 6, "aluminium"),
        C("ROTULE", "Rotule", 2, 1, "steel"),
        C("DOUILLE", "Douille", 2, 1, "steel"),
    ), materials=(("ALU-BILLET", "0.10"),), commons=(("SILENTBLOC", 2), ("CIRCLIP", 2)),
        labour_minutes=12),
    Family("jante", r"^jante", (
        C("VOILE", "Voile forgé", 1, 6, "aluminium"),
        C("ECROU", "Écrou central", 1, 1, "steel"),
        C("VALVE", "Valve et capteur de pression", 1, 1, "electronics"),
    ), materials=(("ALU-BILLET", "0.05"),), labour_minutes=10),
    Family("optique", r"^(projecteur|feu|eclairage)", (
        C("BOITIER", "Boîtier", 1, 2, "default"),
        C("GLACE", "Glace de protection", 1, 1, "default"),
        C("REFLECTEUR", "Réflecteur", 2, 1, "aluminium"),
        C("DRIVER", "Driver LED", 1, 3, "electronics", "carte"),
    ), materials=(("POLYCARBONATE", "0.15"),), commons=(
        ("LED", 24), ("CONNECTEUR-LV", 1), ("VIS-TORX-M5", 4),
    ), labour_minutes=12),
    Family("vitrage", r"^(pare brise|vitre|lunette|vitrage)", (
        C("FILM", "Film acoustique et sérigraphie", 1, 2, "default"),
        C("ENCADREMENT", "Encadrement surmoulé", 1, 2, "rubber"),
        C("CAPTEUR", "Capteur pluie et lumière", 1, 1, "electronics"),
    ), materials=(("LAMINATED-GLASS", "0.70"),), labour_minutes=10),
    Family("siege", r"^(coque siege|coussin foam|garniture|habillage|ciel de toit|tapis|planche de bord|"
           r"tableau de bord|console|volant$|panneau de porte)", (
        C("ARMATURE", "Armature", 1, 4, "composite"),
        C("REVETEMENT", "Revêtement cousu", 1, 3, "default"),
        C("RENFORT", "Renfort local", 2, 1, "composite"),
    ), materials=(("LEATHER", "0.08"), ("ALCANTARA", "0.04"), ("PU-FOAM", "0.10")),
        commons=(("INSERT-M6", 6), ("RIVET", 8)), labour_minutes=25),
    Family("faisceau", r"^(faisceau|cablage|cables hv)", (
        C("GAINE", "Gaines et protections", 1, 2, "rubber"),
        C("BOITIER-DERIVATION", "Boîtier de dérivation", 2, 2, "electronics"),
        C("TRONCON", "Tronçon préassemblé", 4, 1, "cable"),
    ), materials=(("COPPER", "0.45"),), commons=(("CONNECTEUR-LV", 12),), labour_minutes=30),
    Family("echangeur", r"^(radiateur|condenseur|echangeur|refroidisseur|refroidissement|evaporateur|chiller|"
           r"plaque froide|intercooler|air charge air cooler|pompe a chaleur)", (
        C("FAISCEAU", "Faisceau à ailettes brasé", 1, 5, "aluminium"),
        C("BOITE-EAU", "Boîte à eau", 2, 1, "default"),
        C("SUPPORT", "Support", 2, 1, "aluminium"),
    ), materials=(("ALU-CAST", "0.10"),), commons=(("JOINT-TORIQUE", 4), ("SILENTBLOC", 2)),
        labour_minutes=12),
    Family("pompe", r"^(pompe|module pompe|compresseur|ventilateur|soufflante|bloc abs|integrated power|"
           r"bloc valves|bloc hvac|systeme lift)", (
        C("CORPS", "Corps de pompe", 1, 3, "aluminium"),
        C("ROUE", "Roue ou rotor", 1, 2, "default"),
        C("MOTEUR", "Moteur d'entraînement", 1, 3, "motor"),
        C("CARTE", "Électronique de pilotage", 1, 2, "electronics"),
    ), commons=(("ROULEMENT-BILLES", 2), ("BAGUE-ETANCHEITE", 1), ("CONNECTEUR-LV", 1)),
        labour_minutes=12),
    Family("panneau_composite", r"^(aile|panneau|capot|porte diedre|fond plat|splitter|diffuseur|aileron|"
           r"bas de caisse|quarter|toit|pavillon|carenage|ecope|tunnels?|volets?|"
           r"structure superieure|monocoque|elements|bouclier|hayon|cloison|renforts?|"
           r"protections structurelles|cache moteur)", (
        C("PEAU-EXT", "Peau extérieure carbone", 1, 4, "composite"),
        C("PEAU-INT", "Peau intérieure carbone", 1, 3, "composite"),
        C("RENFORT", "Renfort local", 2, 1, "composite"),
        C("ATTACHE", "Attache usinée", 4, 1, "aluminium"),
    ), materials=(("PREPREG", "0.12"), ("HONEYCOMB", "0.05")), commons=(
        ("INSERT-M6", 12), ("RIVET", 16),
    ), labour_minutes=30),
)

#: Second niveau : un composant qui se décompose à son tour.
SUB_FAMILIES: dict[str, Family] = {
    "carte": Family("carte", "", (
        C("PCB", "Circuit imprimé multicouche", 1, 3, "electronics"),
        C("ALIM", "Étage d'alimentation", 1, 2, "electronics"),
    ), commons=(("MICROCONTROLEUR", 1), ("CONDENSATEUR", 60), ("THERMISTANCE", 2)),
        labour_minutes=4),
    "stator": Family("stator", "", (
        C("PAQUET", "Paquet de tôles empilées", 1, 3, "motor"),
        C("BOBINAGE", "Bobinage en épingles", 1, 4, "cable"),
        C("ISOLANT", "Isolant d'encoche", 1, 1, "default"),
    ), materials=(("COPPER", "0.20"), ("FESI", "0.25")), commons=(("THERMISTANCE", 3),),
        labour_minutes=15),
}


@dataclass(frozen=True)
class Zone:
    """Un emplacement : des pièces posées ensemble, × count."""

    group: str
    key: str
    label: str
    count: int
    #: Libellés normalisés des pièces qui y vont (après regroupement par position).
    members: tuple[str, ...]


ZONES: tuple[Zone, ...] = (
    Zone("chassis_suspension", "COIN-SUSPENSION", "Coin de suspension", 4,
         ("ressort", "amortisseur bilstein dtx", "porte moyeu", "roulement moyeu")),
    Zone("chassis_suspension", "TRAIN-AVANT", "Demi-train avant à poussoir", 2,
         ("bras superieur", "bras inferieur", "pushrod", "rocker/bellcrank")),
    Zone("chassis_suspension", "ESSIEU-MULTIBRAS", "Demi-essieu arrière multibras", 2,
         ("lien 1", "lien 2", "lien 3", "lien 4", "lien 5")),
    Zone("freinage", "COIN-FREIN", "Coin de frein", 4,
         ("jeu plaquettes", "capteurs vitesse roue", "capteurs usure plaquettes", "flexibles frein")),
    Zone("structure_carrosserie", "PORTE", "Porte dièdre équipée", 2,
         ("porte diedre", "charniere porte", "serrure porte", "gache porte",
          "joint peripherique porte", "poignee/commande exterieure", "assistance ouverture porte")),
    Zone("habitacle_securite", "SIEGE", "Siège baquet équipé", 2,
         ("coque siege carbone", "coussin/foam siege", "garniture siege", "rail/fixation siege")),
    Zone("habitacle_securite", "CEINTURE", "Ceinture de sécurité complète", 2,
         ("ceinture 3 points", "pretensionneur", "boucle ceinture")),
    Zone("thermique_essence", "BANC-CULASSE", "Banc de culasse", 2,
         ("culasse", "couvercle culasse", "joint culasse", "rail carburant hp")),
    Zone("thermique_essence", "TURBO", "Turbocompresseur équipé", 2,
         ("turbocompresseur", "wastegate turbo")),
    Zone("hybride_electrique_hv", "EDU", "Demi-unité d'entraînement avant", 2,
         ("moteur electrique", "reducteur", "arbre sortie edu")),
    Zone("vitrage_eclairage", "VITRAGE-PORTE", "Vitrage de porte", 2,
         ("vitre porte", "leve-vitre")),
    Zone("direction", "BIELLETTE", "Biellette de direction complète", 2,
         ("biellette direction", "rotule direction")),
    Zone("echappement", "LIGNE", "Demi-ligne d'échappement", 2,
         ("collecteur echappement", "downpipe")),
)


@dataclass
class NewPart:
    """Une pièce achetée ajoutée par le détail : composant, matière ou standard."""

    ref: str
    label: str
    unit: str
    price: Decimal
    mass: Decimal
    carbon: Decimal
    profile: str
    system: str
    category: str
    #: Fournisseur par défaut : nom de source (composant) ou identifiant (matière, standard).
    source_name: str | None = None
    supplier_id: str | None = None


@dataclass
class Assembly:
    """Une pièce devenue ensemble fabriqué : ses enfants et sa main-d'œuvre."""

    ref: str
    label: str
    children: dict[str, Decimal]
    labour_minutes: int


class Detailer:
    """Accumule, pour une variante, les pièces et ensembles ajoutés."""

    def __init__(self, prefix: str, labour_rate: Decimal) -> None:
        self.prefix = prefix
        self.minute_cost = labour_rate / 60
        self.parts: dict[str, NewPart] = {}
        self.assemblies: dict[str, Assembly] = {}

    # -- références partagées ---------------------------------------------------

    def _material(self, key: str) -> tuple[str, Decimal, Decimal]:
        label, profile, price, carbon, supplier = MATERIALS[key]
        ref = f"{self.prefix}-MAT-{key}"
        if ref not in self.parts:
            self.parts[ref] = NewPart(
                ref, label, "kg", Decimal(price), Decimal(1), Decimal(carbon), profile,
                "MAT", "material", supplier_id=supplier,
            )
        return ref, Decimal(price), Decimal(1)

    def _common(self, key: str) -> tuple[str, Decimal, Decimal]:
        label, profile, price, mass, carbon, supplier = COMMONS[key]
        ref = f"{self.prefix}-STD-{key}"
        if ref not in self.parts:
            self.parts[ref] = NewPart(
                ref, label, "pce", Decimal(price), Decimal(mass), Decimal(carbon), profile,
                "FIX", "fastener", supplier_id=supplier,
            )
        return ref, Decimal(price), Decimal(mass)

    # -- décomposition ----------------------------------------------------------

    def family_of(self, label: str) -> Family | None:
        name = normalize(label)
        return next((f for f in FAMILIES if re.search(f.pattern, name)), None)

    def decompose(
        self, ref: str, label: str, price: Decimal, mass: Decimal,
        family: Family, source_name: str, system: str, category: str,
    ) -> bool:
        """Transforme `ref` en ensemble si son prix et sa masse le permettent.

        Renvoie False sans rien enregistrer quand les matières, standards et
        main-d'œuvre dépasseraient la part autorisée : la pièce reste achetée.
        """
        fixed_cost = family.labour_minutes * self.minute_cost
        fixed_mass = Decimal(0)
        planned: list[tuple[str, Decimal, Decimal, Decimal]] = []  # ref, qté, prix, masse
        for key, share in family.materials:
            kg = (mass * Decimal(share)).quantize(KG)
            if kg <= 0:
                continue
            _, _, unit_price, _, _ = MATERIALS[key]
            planned.append((f"{self.prefix}-MAT-{key}", kg, Decimal(unit_price), Decimal(1)))
        for key, quantity in family.commons:
            _, _, unit_price, unit_mass, _, _ = COMMONS[key]
            planned.append(
                (f"{self.prefix}-STD-{key}", Decimal(quantity), Decimal(unit_price), Decimal(unit_mass))
            )
        for child, quantity, unit_price, unit_mass in planned:
            fixed_cost += quantity * unit_price
            fixed_mass += quantity * unit_mass
        if fixed_cost > price * MAX_FIXED_SHARE or fixed_mass > mass * MAX_FIXED_MASS_SHARE:
            return False

        remaining_price = price - fixed_cost
        remaining_mass = mass - fixed_mass
        total_weight = sum(c.weight * c.quantity for c in family.components)
        shares: list[tuple[Component, Decimal, Decimal]] = []
        for component in family.components[1:]:
            unit_price = (
                remaining_price * component.weight / total_weight
            ).quantize(SCALE6)
            unit_mass = (remaining_mass * component.weight / total_weight).quantize(SCALE6)
            shares.append((component, unit_price, unit_mass))
        first = family.components[0]
        assert first.quantity == 1, f"{family.name} : le premier composant absorbe l'arrondi"
        shares.insert(0, (
            first,
            remaining_price - sum(c.quantity * p for c, p, _ in shares),
            remaining_mass - sum(c.quantity * m for c, _, m in shares),
        ))
        if any(p <= 0 or m <= 0 for _, p, m in shares):
            return False

        # Faisable : les matières et standards entrent seulement maintenant,
        # sinon un refus laisserait des pièces que personne n'emploie.
        children: dict[str, Decimal] = {}
        for key, _ in family.materials:
            if any(p[0] == f"{self.prefix}-MAT-{key}" for p in planned):
                self._material(key)
        for key, _ in family.commons:
            self._common(key)
        for child, quantity, _, _ in planned:
            children[child] = quantity

        for component, unit_price, unit_mass in shares:
            child = f"{ref}-{component.key}"
            child_label = f"{label} — {component.label.lower()}"
            sub = SUB_FAMILIES.get(component.detail) if component.detail else None
            if sub is None or not self.decompose(
                child, child_label, unit_price, unit_mass, sub, source_name, system, category
            ):
                self.parts[child] = NewPart(
                    child, child_label, "pce", unit_price, unit_mass,
                    enrich.carbon_factor(child, unit_mass, component.profile),
                    component.profile, system, category, source_name=source_name,
                )
            children[child] = Decimal(component.quantity)

        self.assemblies[ref] = Assembly(ref, label, children, family.labour_minutes)
        return True


def in_zone(zone: Zone, label: str) -> bool:
    return normalize(label) in {normalize(member) for member in zone.members}
