from django import template

register = template.Library()


@register.filter
def fcfa(valeur):
    """Affiche un montant : 35775 -> « 35 775 FCFA »."""
    try:
        entier = int(valeur)
    except (TypeError, ValueError):
        return valeur
    return f'{entier:,}'.replace(',', '\u202f') + '\u00a0FCFA'


@register.filter
def nombre(valeur):
    """Affiche un nombre avec séparateur de milliers."""
    try:
        return f'{int(valeur):,}'.replace(',', '\u202f')
    except (TypeError, ValueError):
        return valeur
