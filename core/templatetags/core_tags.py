from django import template
from core.models import Prestataire, JournalActivite

register = template.Library()


@register.simple_tag
def all_prestataires():
    return Prestataire.objects.all()


@register.simple_tag
def type_choices():
    return JournalActivite.TYPE_CHOICES


@register.filter(name='has_role')
def has_role(user, roles):
    """
    Verifie qu'un utilisateur authentifie possede un des roles indiques
    (chaine separee par des virgules). 'admin' est toujours autorise.

    Usage : {% if request.user|has_role:"dag,admin" %}
    """
    if not getattr(user, 'is_authenticated', False):
        return False
    user_role = getattr(user, 'role', None)
    if user_role == 'admin':
        return True
    allowed = {r.strip() for r in (roles or '').split(',') if r.strip()}
    return user_role in allowed


@register.filter(name='get_item')
def get_item(dictionary, key):
    """Accès dict par clé variable. Usage : {{ dict|get_item:key }}"""
    return dictionary.get(key)


@register.filter(name='in_csv')
def in_csv(value, csv):
    """
    Test d'appartenance strict a une liste CSV (sans piege substring).

    Usage : {% if bc.statut|in_csv:"execute,annule" %}
    """
    if value is None:
        return False
    items = {s.strip() for s in (csv or '').split(',') if s.strip()}
    return str(value) in items
