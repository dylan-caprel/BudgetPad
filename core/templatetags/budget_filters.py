from django import template
from decimal import Decimal

register = template.Library()


@register.filter
def fmt(value):
    """
    Formate un montant FCFA de façon lisible :
      120 000 000  →  120 M FCFA
       12 500 000  →  12,5 M FCFA
          500 000  →  500 K FCFA
           45 000  →  45 000 FCFA
    Fonctionne avec int, float et Decimal. Gère les valeurs négatives.
    """
    if value is None:
        return '0 FCFA'
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)

    sign = '-' if v < 0 else ''
    v = abs(v)

    if v >= 1_000_000:
        millions = v / 1_000_000
        # Affiche une décimale seulement si elle est non nulle
        if millions == int(millions):
            formatted = f"{int(millions)}"
        else:
            formatted = f"{millions:.1f}".replace('.', ',')
        return f"{sign}{formatted} M FCFA"

    if v >= 1_000:
        milliers = v / 1_000
        if milliers == int(milliers):
            formatted = f"{int(milliers)}"
        else:
            formatted = f"{milliers:.1f}".replace('.', ',')
        return f"{sign}{formatted} K FCFA"

    return f"{sign}{int(round(v))} FCFA"


@register.filter
def fmt_exact(value):
    """
    Montant exact avec séparateur de milliers (espace) :
      29 200 000  →  29 200 000 FCFA
         500 000  →  500 000 FCFA
    """
    if value is None:
        return '0 FCFA'
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)
    sign = '-' if v < 0 else ''
    v = abs(v)
    formatted = f"{int(round(v)):,}".replace(',', ' ')
    return f"{sign}{formatted} FCFA"


@register.filter
def fmt_court(value):
    """
    Version courte sans unité FCFA :
      12 500 000  →  12,5M
         500 000  →  500K
          45 000  →  45K
    """
    if value is None:
        return '0'
    try:
        v = float(value)
    except (TypeError, ValueError):
        return str(value)

    sign = '-' if v < 0 else ''
    v = abs(v)

    if v >= 1_000_000:
        millions = v / 1_000_000
        if millions == int(millions):
            return f"{sign}{int(millions)}M"
        return f"{sign}{millions:.1f}M".replace('.', ',')

    if v >= 1_000:
        milliers = v / 1_000
        if milliers == int(milliers):
            return f"{sign}{int(milliers)}K"
        return f"{sign}{milliers:.1f}K".replace('.', ',')

    return f"{sign}{int(round(v))}"
