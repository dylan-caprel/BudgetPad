"""
Réinitialise le mot de passe d'un ou plusieurs comptes BudgetPAD.

Exemples :
    # Tous les comptes -> mot de passe par défaut (Pad2025@)
    python manage.py reset_passwords --all

    # Tous les comptes -> mot de passe choisi
    python manage.py reset_passwords --all --password "MonMotDePasse1!"

    # Seulement certains comptes (par username)
    python manage.py reset_passwords --user admin directeur

    # Seulement un rôle
    python manage.py reset_passwords --role assistante_drh

    # Forcer le changement de mot de passe à la prochaine connexion
    python manage.py reset_passwords --all --must-change

    # Voir ce qui serait fait, sans rien modifier
    python manage.py reset_passwords --all --dry-run
"""

from django.core.management.base import BaseCommand, CommandError

from core.models import Utilisateur

DEFAULT_PASSWORD = 'Pad2025@'


class Command(BaseCommand):
    help = "Réinitialise le mot de passe d'un ou plusieurs utilisateurs."

    def add_arguments(self, parser):
        parser.add_argument(
            '--password', '-p', default=DEFAULT_PASSWORD,
            help=f"Nouveau mot de passe (défaut : {DEFAULT_PASSWORD}).",
        )
        parser.add_argument(
            '--user', '-u', nargs='+', metavar='USERNAME',
            help="Limiter à ces usernames (séparés par un espace).",
        )
        parser.add_argument(
            '--role', '-r', choices=[c[0] for c in Utilisateur.ROLE_CHOICES],
            help="Limiter à ce rôle.",
        )
        parser.add_argument(
            '--all', action='store_true',
            help="Cibler TOUS les comptes (obligatoire si aucun filtre --user/--role).",
        )
        parser.add_argument(
            '--must-change', action='store_true',
            help="Forcer le changement de mot de passe à la prochaine connexion.",
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help="Afficher les comptes concernés sans rien modifier.",
        )

    def handle(self, *args, **options):
        password = options['password']
        usernames = options.get('user')
        role = options.get('role')
        cibler_tous = options['all']
        must_change = options['must_change']
        dry_run = options['dry_run']

        # ── Sélection des comptes ─────────────────────────────────────────
        qs = Utilisateur.objects.all().order_by('username')
        filtre_applique = False

        if usernames:
            qs = qs.filter(username__in=usernames)
            filtre_applique = True
        if role:
            qs = qs.filter(role=role)
            filtre_applique = True

        # Garde-fou : pas de réinitialisation globale sans --all explicite
        if not filtre_applique and not cibler_tous:
            raise CommandError(
                "Aucun filtre fourni. Précisez --user / --role, "
                "ou ajoutez --all pour réinitialiser TOUS les comptes."
            )

        comptes = list(qs)
        if not comptes:
            self.stdout.write(self.style.WARNING("Aucun compte ne correspond aux critères."))
            return

        # Avertir si certains usernames demandés n'existent pas
        if usernames:
            trouves = {u.username for u in comptes}
            manquants = [u for u in usernames if u not in trouves]
            if manquants:
                self.stdout.write(self.style.WARNING(
                    f"Usernames introuvables (ignorés) : {', '.join(manquants)}"
                ))

        # ── Application ───────────────────────────────────────────────────
        verbe = "[dry-run] serait réinitialisé" if dry_run else "réinitialisé"
        for u in comptes:
            if not dry_run:
                u.set_password(password)
                u.must_change_password = must_change
                u.save(update_fields=['password', 'must_change_password'])
            self.stdout.write(
                f"  - {u.username:16} | {u.role:14} | {verbe}"
            )

        n = len(comptes)
        if dry_run:
            self.stdout.write(self.style.NOTICE(
                f"\n{n} compte(s) seraient mis à jour (mot de passe : {password})."
            ))
        else:
            flag = " (changement forcé à la 1ʳᵉ connexion)" if must_change else ""
            self.stdout.write(self.style.SUCCESS(
                f"\n{n} compte(s) réinitialisé(s) avec le mot de passe : {password}{flag}"
            ))
