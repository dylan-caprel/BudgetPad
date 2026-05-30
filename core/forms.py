from django import forms
from decimal import Decimal
from .models import (
    Tache, LigneBudgetaire, VirementBudgetaire, Prestataire,
    DemandeAchat, BonCommande, Offre, ImputationBC, ProlongationBC,
)
from .constants import TVA_RATE


class VirementForm(forms.ModelForm):
    """Formulaire pour créer un virement budgétaire (entre lignes)."""

    class Meta:
        model = VirementBudgetaire
        fields = ['ligne_source', 'ligne_destination', 'montant', 'motif']
        widgets = {
            'ligne_source': forms.Select(attrs={'class': 'form-select'}),
            'ligne_destination': forms.Select(attrs={'class': 'form-select'}),
            'montant': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
                'placeholder': '0.00',
            }),
            'motif': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Raison du virement...',
            }),
        }

    def __init__(self, *args, **kwargs):
        exercice = kwargs.pop('exercice', None)
        super().__init__(*args, **kwargs)
        if exercice:
            qs = LigneBudgetaire.objects.filter(
                tache__exercice=exercice, actif=True,
            ).select_related('tache').order_by('tache__numero', 'code_nature')
            self.fields['ligne_source'].queryset = qs
            self.fields['ligne_destination'].queryset = qs

    def clean(self):
        cleaned_data = super().clean()
        source = cleaned_data.get('ligne_source')
        dest   = cleaned_data.get('ligne_destination')
        montant = cleaned_data.get('montant')

        if source and dest and source == dest:
            raise forms.ValidationError("La ligne source et destination doivent être différentes.")

        if montant and source:
            if montant <= 0:
                raise forms.ValidationError("Le montant doit être positif.")
            # Calcul du solde de la ligne source (sans annotation complète, on fait une requête simple)
            lignes = LigneBudgetaire.objects.with_aggregates().filter(pk=source.pk)
            if lignes.exists():
                ligne_annotee = lignes.first()
                solde_source = getattr(ligne_annotee, 'solde', None)
                if solde_source is not None and montant > solde_source:
                    raise forms.ValidationError(
                        f"Solde insuffisant sur la ligne source. Disponible : {solde_source:,.0f} FCFA"
                    )

        return cleaned_data


class PrestataireForm(forms.ModelForm):
    class Meta:
        model = Prestataire
        fields = ['nom', 'adresse', 'telephone', 'email']
        widgets = {
            'nom': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nom du prestataire',
            }),
            'adresse': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Adresse complète',
            }),
            'telephone': forms.TextInput(attrs={
                'class': 'form-control',
                'type': 'tel',
                'placeholder': '+237 2XX XXX XXX',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'email@example.com',
            }),
        }


class TacheForm(forms.ModelForm):
    class Meta:
        model = Tache
        fields = ['numero', 'titre']
        widgets = {
            'numero': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 3101069',
            }),
            'titre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: REVISION DE LA CONVENTION COLLECTIVE',
            }),
        }


class LigneBudgetaireForm(forms.ModelForm):
    class Meta:
        model = LigneBudgetaire
        fields = ['code_nature', 'libelle_nature', 'montant_initial']
        widgets = {
            'code_nature': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: 6047210',
            }),
            'libelle_nature': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: FOURNITURES DE BUREAU SUR STOCK',
            }),
            'montant_initial': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '1',
            }),
        }


class DemandeAchatForm(forms.ModelForm):
    class Meta:
        model = DemandeAchat
        fields = ['tache', 'objet', 'montant_estime']
        widgets = {
            'tache': forms.Select(attrs={'class': 'form-select'}),
            'objet': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Achat fournitures bureau',
            }),
            'montant_estime': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
            }),
        }

    def __init__(self, *args, **kwargs):
        exercice = kwargs.pop('exercice', None)
        super().__init__(*args, **kwargs)
        if exercice:
            self.fields['tache'].queryset = Tache.objects.filter(
                exercice=exercice, actif=True,
            ).order_by('numero')

    def clean_montant_estime(self):
        montant = self.cleaned_data.get('montant_estime')
        if montant is not None and montant <= 0:
            raise forms.ValidationError("Le montant estimé doit être supérieur à zéro.")
        return montant


class BonCommandeForm(forms.ModelForm):
    class Meta:
        model = BonCommande
        fields = ['tache', 'prestataire', 'montant_ht', 'delai_execution_jours']
        widgets = {
            'tache': forms.Select(attrs={'class': 'form-select'}),
            'prestataire': forms.Select(attrs={'class': 'form-select'}),
            'montant_ht': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
            }),
            'delai_execution_jours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Délai en jours',
            }),
        }


class ProlongationBCForm(forms.ModelForm):
    class Meta:
        model = ProlongationBC
        fields = ['nouvelle_echeance', 'motif']
        widgets = {
            'nouvelle_echeance': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'motif': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Motif de la prolongation...',
            }),
        }

    def clean_nouvelle_echeance(self):
        from datetime import date as _date
        val = self.cleaned_data.get('nouvelle_echeance')
        if val and val <= _date.today():
            raise forms.ValidationError("La nouvelle échéance doit être dans le futur.")
        return val


class OffreSolliciterForm(forms.Form):
    prestataire = forms.ModelChoiceField(
        queryset=Prestataire.objects.order_by('nom'),
        widget=forms.Select(attrs={'class': 'form-select'}),
        label='Prestataire à contacter',
        empty_label='Choisir un prestataire...',
    )


class OffreSaisirForm(forms.Form):
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
