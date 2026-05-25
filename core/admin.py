from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Utilisateur, ExerciceBudgetaire, Tache, VirementBudgetaire,
    Prestataire, DemandeAchat, Offre, BonCommande, LigneBC,
    HistoriqueStatut, JournalActivite, Notification, Alerte
)


@admin.register(Utilisateur)
class UtilisateurAdmin(UserAdmin):
    list_display = ['username', 'nom_complet', 'email', 'role', 'is_active']
    list_filter = ['role', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Informations BudgetPAD', {'fields': ('role', 'nom_complet')}),
    )


@admin.register(ExerciceBudgetaire)
class ExerciceAdmin(admin.ModelAdmin):
    list_display = ['annee', 'montant_global', 'statut', 'date_debut', 'date_fin']


@admin.register(Tache)
class TacheAdmin(admin.ModelAdmin):
    list_display = ['numero', 'titre', 'montant_initial', 'code_nature']
    list_filter = ['exercice']


@admin.register(VirementBudgetaire)
class VirementAdmin(admin.ModelAdmin):
    list_display = ['tache_source', 'tache_dest', 'montant', 'created_by', 'created_at']


@admin.register(Prestataire)
class PrestataireAdmin(admin.ModelAdmin):
    list_display = ['code', 'nom', 'telephone', 'email']


class OffreInline(admin.TabularInline):
    model = Offre
    extra = 0


@admin.register(DemandeAchat)
class DemandeAchatAdmin(admin.ModelAdmin):
    list_display = ['reference', 'objet', 'tache', 'montant_estime', 'statut']
    list_filter = ['statut']
    inlines = [OffreInline]


class LigneBCInline(admin.TabularInline):
    model = LigneBC
    extra = 0

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.bon_commande.statut in ('execute', 'annule'):
            return [f.name for f in self.model._meta.fields]
        return super().get_readonly_fields(request, obj)

    def has_add_permission(self, request, obj=None):
        if obj and obj.bon_commande.statut in ('execute', 'annule'):
            return False
        return super().has_add_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.bon_commande.statut in ('execute', 'annule'):
            return False
        return super().has_delete_permission(request, obj)


_BC_LOCKED_FIELDS = [
    'numero', 'demande', 'tache', 'exercice', 'prestataire', 'direction',
    'date_emission', 'taux_tva', 'montant_ht', 'montant_tva', 'montant_ttc',
    'statut', 'motif_annulation',
]


@admin.register(BonCommande)
class BonCommandeAdmin(admin.ModelAdmin):
    list_display = ['numero', 'tache', 'prestataire', 'montant_ttc', 'statut']
    list_filter = ['statut']
    inlines = [LigneBCInline]

    def get_readonly_fields(self, request, obj=None):
        if obj and obj.statut in ('execute', 'annule'):
            return _BC_LOCKED_FIELDS
        return super().get_readonly_fields(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj and obj.statut == 'execute':
            return False
        return super().has_delete_permission(request, obj)


@admin.register(JournalActivite)
class JournalAdmin(admin.ModelAdmin):
    list_display = ['type_action', 'description', 'utilisateur', 'created_at']
    list_filter = ['type_action']


admin.site.register(Notification)
admin.site.register(Alerte)
admin.site.register(HistoriqueStatut)

admin.site.site_header = "BudgetPAD — Administration"
admin.site.site_title = "BudgetPAD Admin"
admin.site.index_title = "Gestion des données"
