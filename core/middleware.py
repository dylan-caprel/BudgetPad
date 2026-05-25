"""Middlewares applicatifs BudgetPAD."""

from django.shortcuts import redirect
from django.urls import reverse


class ForcePasswordChangeMiddleware:
    """
    Si l'utilisateur authentifie a must_change_password=True, on le redirige
    vers la page de changement de mot de passe, sauf pour les URLs exemptees
    (logout, page de changement elle-meme, fichiers statiques, admin Django).

    L'interception se fait dans process_view pour avoir acces a la resolution
    d'URL (resolver_match), sinon la page de changement boucle sur elle-meme.
    """

    EXEMPT_URL_NAMES = {'logout', 'password_change_forced'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, 'user', None)
        if not (user and user.is_authenticated and getattr(user, 'must_change_password', False)):
            return None

        path = request.path
        if path.startswith('/static/') or path.startswith('/admin/'):
            return None

        match = getattr(request, 'resolver_match', None)
        url_name = match.url_name if match else None
        if url_name in self.EXEMPT_URL_NAMES:
            return None

        return redirect(reverse('password_change_forced'))
