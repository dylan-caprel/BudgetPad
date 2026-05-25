"""Service de notifications utilisateur."""

import logging
from ..models import Notification, Utilisateur

logger = logging.getLogger('budgetpad')


class NotificationService:
    """Cree des notifications cibles selon des regles metier."""

    @staticmethod
    def notifier(utilisateur: Utilisateur, type_notif: str, titre: str,
                 message: str, entite_type: str = '', entite_id=None) -> Notification:
        """Cree une notification pour un utilisateur."""
        notif = Notification.objects.create(
            utilisateur=utilisateur,
            type=type_notif,
            titre=titre,
            message=message,
            entite_type=entite_type,
            entite_id=entite_id,
        )
        logger.info("Notification[%s] -> %s : %s", type_notif, utilisateur.username, titre)
        return notif

    @staticmethod
    def notifier_roles(roles: list[str], type_notif: str, titre: str,
                       message: str, entite_type: str = '', entite_id=None) -> int:
        """
        Cree une notification pour tous les utilisateurs actifs ayant l'un
        des roles indiques. Retourne le nombre de notifications creees.
        """
        users = Utilisateur.objects.filter(is_active=True, role__in=roles)
        notifs = [
            Notification(
                utilisateur=u,
                type=type_notif,
                titre=titre,
                message=message,
                entite_type=entite_type,
                entite_id=entite_id,
            )
            for u in users
        ]
        Notification.objects.bulk_create(notifs)
        logger.info("Notification[%s] -> roles=%s (%d destinataires)",
                    type_notif, roles, len(notifs))
        return len(notifs)

    @staticmethod
    def marquer_lues(utilisateur: Utilisateur, ids: list[int] = None) -> int:
        """Marque comme lues les notifications de l'utilisateur (toutes ou liste d'ids)."""
        qs = Notification.objects.filter(utilisateur=utilisateur, lu=False)
        if ids is not None:
            qs = qs.filter(pk__in=ids)
        return qs.update(lu=True)
