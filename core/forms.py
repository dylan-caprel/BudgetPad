from django import forms
from decimal import Decimal
from .models import (
    Tache, VirementBudgetaire, Prestataire, DemandeAchat,
    BonCommande, Offre,
)
from .constants import TVA_RATE


class VirementForm(forms.ModelForm):
    """Formulaire pour créer un virement budgétaire"""

    class Meta:
        model = VirementBudgetaire
        fields = ['tache_source', 'tache_dest', 'montant', 'motif']
        widgets = {
            'tache_source': forms.Select(attrs={'class': 'form-select'}),
            'tache_dest': forms.Select(attrs={'class': 'form-select'}),
            'montant': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
                'placeholder': '0.00'
            }),
            'motif': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Raison du virement...'
            }),
        }

    def __init__(self, *args, **kwargs):
        exercice = kwargs.pop('exercice', None)
        super().__init__(*args, **kwargs)
        if exercice:
            qs = Tache.objects.filter(exercice=exercice)
            self.fields['tache_source'].queryset = qs
            self.fields['tache_dest'].queryset = qs

    def clean(self):
        cleaned_data = super().clean()
        source = cleaned_data.get('tache_source')
        dest = cleaned_data.get('tache_dest')
        montant = cleaned_data.get('montant')

        if source and dest and source == dest:
            raise forms.ValidationError(
                "La source et destination doivent être différentes."
            )

        if montant and source:
            if montant <= 0:
                raise forms.ValidationError("Le montant doit être positif.")
            if montant > source.solde:
                raise forms.ValidationError(
                    f"Solde insuffisant. Disponible: {source.solde:,.0f} FCFA"
                )

        return cleaned_data


class PrestataireForm(forms.ModelForm):
    """Formulaire pour gérer les prestataires"""
    
    class Meta:
        model = Prestataire
        fields = ['nom', 'adresse', 'telephone', 'email']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom du prestataire',
                'required': True
            }),
            'adresse': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Adresse complète'
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'tel',
                'placeholder': '+237 2XX XXX XXX'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com'
            }),
        }


class TacheForm(forms.ModelForm):
    """Formulaire pour créer/modifier une tâche"""
    
    class Meta:
        model = Tache
        fields = ['numero', 'titre', 'code_nature', 'libelle_nature', 'montant_initial', 'taux_previsionnel']
        widgets = {
            'numero': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'T-001',
                'readonly': True  # Auto-généré
            }),
            'titre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Fournitures de bureau'
            }),
            'code_nature': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '60410'
            }),
            'libelle_nature': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Fournitures de bureau'
            }),
            'montant_initial': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
            }),
            'taux_previsionnel': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'max': '100',
                'step': '0.1',
            }),
        }
    
    def clean_montant_initial(self):
        montant = self.cleaned_data.get('montant_initial')
        if montant and montant < 0.01:
            raise forms.ValidationError("Le montant doit être >= 0.01 FCFA")
        return montant


class DemandeAchatForm(forms.ModelForm):
    """Formulaire pour créer une demande d'achat"""

    class Meta:
        model = DemandeAchat
        fields = ['tache', 'objet', 'montant_estime']
        widgets = {
            'tache': forms.Select(attrs={'class': 'form-select'}),
            'objet': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Achat fournitures bureau'
            }),
            'montant_estime': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
            }),
        }

    def clean_montant_estime(self):
        montant = self.cleaned_data.get('montant_estime')
        if montant is not None and montant <= 0:
            raise forms.ValidationError("Le montant estimé doit être supérieur à zéro.")
        return montant


class BonCommandeForm(forms.ModelForm):
    """Formulaire pour créer un bon de commande"""
    
    class Meta:
        model = BonCommande
        fields = ['tache', 'prestataire', 'montant_ht']
        widgets = {
            'tache': forms.Select(attrs={'class': 'form-select'}),
            'prestataire': forms.Select(attrs={'class': 'form-select'}),
            'montant_ht': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
            }),
        }
    
    def clean(self):
        cleaned_data = super().clean()
        tache = cleaned_data.get('tache')
        montant_ht = cleaned_data.get('montant_ht')

        if tache and montant_ht:
            montant_ttc = montant_ht * (1 + TVA_RATE / 100)
            if montant_ttc > tache.solde:
                raise forms.ValidationError(
                    f"Montant TTC ({montant_ttc:,.0f}) dépasse le solde ({tache.solde:,.0f})"
                )

        return cleaned_data


class OffreSolliciterForm(forms.Form):
    """Formulaire de sollicitation d'un prestataire (sans montant encore connu)."""
    prestataire = forms.ModelChoiceField(
        queryset=Prestataire.objects.order_by('nom'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Prestataire à contacter',
        empty_label='Choisir un prestataire...',
    )


class OffreSaisirForm(forms.Form):
    """Formulaire de saisie du montant d'une offre reçue."""
    montant = forms.DecimalField(
        max_digits=15, decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '1',
            'step': '1',
            'placeholder': 'Montant en FCFA',
        }),
        label='Montant proposé (FCFA)',
    )

    def clean_montant(self):
        montant = self.cleaned_data.get('montant')
        if montant is not None and montant <= 0:
            raise forms.ValidationError("Le montant doit être supérieur à zéro.")
        return montant


class OffreRefuserForm(forms.Form):
    """Formulaire de refus manuel d'une offre (motif obligatoire)."""
    motif = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Motif du refus…',
        }),
        label='Motif du refus',
        min_length=3,
    )

    def clean_motif(self):
        motif = self.cleaned_data.get('motif', '').strip()
        if not motif:
            raise forms.ValidationError("Motif obligatoire.")
        return motif
