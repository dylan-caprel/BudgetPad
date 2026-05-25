"""Mixins pour Class-Based Views."""

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect


class RoleRequiredMixin(LoginRequiredMixin):
    """
    Mixin de permission base sur le champ `role` du modele Utilisateur.

    Usage :
        class MaVue(RoleRequiredMixin, ListView):
            allowed_roles = ('dag', 'directeur_drh')

    Le role 'admin' contourne toujours la restriction.
    """
    allowed_roles: tuple[str, ...] = ()
    permission_denied_redirect = 'dashboard'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        user_role = getattr(request.user, 'role', None)
        if user_role != 'admin' and user_role not in self.allowed_roles:
            messages.error(request, "Vous n'avez pas les droits pour cette action.")
            return redirect(self.permission_denied_redirect)
        return super().dispatch(request, *args, **kwargs)
