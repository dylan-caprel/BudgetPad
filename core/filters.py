"""FilterSets django-filter pour les listes."""

import django_filters
from django import forms
from .models import BonCommande, DemandeAchat, JournalActivite, Prestataire, Tache


class BonCommandeFilter(django_filters.FilterSet):
    numero = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'N° BC...'}),
        label='Numéro',
    )
    statut = django_filters.ChoiceFilter(
        choices=BonCommande.STATUT_CHOICES,
        empty_label='Tous',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    tache = django_filters.ModelChoiceFilter(
        queryset=Tache.objects.all(),
        empty_label='Toutes les tâches',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    prestataire = django_filters.ModelChoiceFilter(
        queryset=Prestataire.objects.all(),
        empty_label='Tous les prestataires',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )

    class Meta:
        model = BonCommande
        fields = ['numero', 'statut', 'tache', 'prestataire']


class DemandeAchatFilter(django_filters.FilterSet):
    reference = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Référence...'}),
        label='Référence',
    )
    objet = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Objet...'}),
    )
    statut = django_filters.ChoiceFilter(
        choices=DemandeAchat.STATUT_CHOICES,
        empty_label='Tous',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    tache = django_filters.ModelChoiceFilter(
        queryset=Tache.objects.all(),
        empty_label='Toutes les tâches',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )

    class Meta:
        model = DemandeAchat
        fields = ['reference', 'objet', 'statut', 'tache']


class JournalFilter(django_filters.FilterSet):
    type_action = django_filters.ChoiceFilter(
        choices=JournalActivite.TYPE_CHOICES,
        empty_label='Tous les types',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
        label='Type',
    )
    description = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Recherche...'}),
    )

    class Meta:
        model = JournalActivite
        fields = ['type_action', 'description']


class PrestataireFilter(django_filters.FilterSet):
    nom = django_filters.CharFilter(
        lookup_expr='icontains',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Nom...'}),
    )

    class Meta:
        model = Prestataire
        fields = ['nom']
