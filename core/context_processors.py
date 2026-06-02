"""Context processors BudgetPAD."""

from .models import ExerciceBudgetaire, Notification


def notifications_count(request):
    """Expose le nombre de notifications non lues + les 5 plus recentes."""
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated):
        return {'notif_count': 0, 'notif_recent': []}

    qs = Notification.objects.filter(utilisateur=user, lu=False)
    unread = qs.count()
    recent = list(qs.order_by('-created_at')[:5])
    return {'notif_count': unread, 'notif_recent': recent}


def exercices_context(request):
    """
    Expose l'exercice courant (selection utilisateur + actif par defaut) et
    la liste de tous les exercices pour le selecteur.
    """
    user = getattr(request, 'user', None)
    if not (user and user.is_authenticated):
        return {'exercices_all': [], 'exercice_courant': None}

    exercices_all = list(ExerciceBudgetaire.objects.order_by('-annee'))
    selected_annee = request.session.get('exercice_annee')
    exercice_courant = None
    if selected_annee:
        exercice_courant = next((e for e in exercices_all if e.annee == selected_annee), None)
    if exercice_courant is None:
        exercice_courant = next((e for e in exercices_all if e.is_active), None)
        if exercice_courant is None:
            exercice_courant = next((e for e in exercices_all if e.statut == 'actif'), None)
        if exercice_courant is None and exercices_all:
            exercice_courant = exercices_all[0]
    return {
        'exercices_all': exercices_all,
        'exercice_courant': exercice_courant,
    }
