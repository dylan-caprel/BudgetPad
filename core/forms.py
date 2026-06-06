from django import forms
from decimal import Decimal
from .models import (
    Tache, LigneBudgetaire, VirementBudgetaire, Prestataire,
    DemandeAchat, BonCommande, Offre, ImputationBC, ProlongationBC,
    ConsommationDirecte, ExerciceBudgetaire, LigneBC,
)
from .constants import TVA_RATE


def _solde_disponible_ligne(ligne, exclude_da_pk=None):
    """Solde réellement disponible sur une ligne budgétaire :
    solde comptable (budget ajusté − consommation) MOINS les montants déjà
    engagés par les autres DA actives (créée / transmise DAG / validée, sans BC).

    Retourne (solde_comptable, montant_engage, solde_disponible).
    """
    from django.db.models import Sum, Value, DecimalField
    from django.db.models.functions import Coalesce
    zero = Value(Decimal('0'), output_field=DecimalField(max_digits=15, decimal_places=2))

    annot = LigneBudgetaire.objects.filter(pk=ligne.pk).with_aggregates().first()
    solde_comptable = (annot.solde if annot else None) or Decimal('0')

    qs = DemandeAchat.objects.filter(
        ligne_budgetaire=ligne, statut__in=['cree', 'en_etude', 'validee'],
    )
    if exclude_da_pk:
        qs = qs.exclude(pk=exclude_da_pk)
    engage = qs.aggregate(t=Coalesce(Sum('montant_estime'), zero))['t'] or Decimal('0')

    return solde_comptable, engage, (solde_comptable - engage)


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
        fields = ['reference', 'ligne_budgetaire', 'objet', 'montant_estime',
                  'nature_prestation', 'periode_engagement', 'priorite']
        widgets = {
            'reference': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: DAC2406DLA00042 (laisser vide pour auto-génération)',
            }),
            'ligne_budgetaire': forms.Select(attrs={'class': 'form-select'}),
            'objet': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: Achat consommables informatiques',
            }),
            'montant_estime': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '1000',
                'placeholder': '0',
            }),
            'nature_prestation': forms.Select(attrs={'class': 'form-select'}),
            'periode_engagement': forms.Select(attrs={'class': 'form-select'}),
            'priorite': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        exercice = kwargs.pop('exercice', None)
        super().__init__(*args, **kwargs)
        self.fields['reference'].required = False
        self.fields['reference'].label = "Numéro DA (optionnel)"
        qs = LigneBudgetaire.objects.none()
        if exercice:
            qs = (
                LigneBudgetaire.objects
                .filter(tache__exercice=exercice, actif=True)
                .select_related('tache')
                .order_by('tache__numero', 'code_nature')
            )
        self.fields['ligne_budgetaire'].queryset = qs
        self.fields['ligne_budgetaire'].label_from_instance = (
            lambda obj: f"{obj.tache.numero} › {obj.code_nature} — {obj.libelle_nature}"
        )
        self.fields['ligne_budgetaire'].empty_label = "Choisir une ligne budgétaire…"

    def clean_montant_estime(self):
        montant = self.cleaned_data.get('montant_estime')
        if montant is not None and montant <= 0:
            raise forms.ValidationError("Le montant estimé doit être supérieur à zéro.")
        return montant

    def clean(self):
        cleaned = super().clean()
        ligne = cleaned.get('ligne_budgetaire')
        montant = cleaned.get('montant_estime')
        if ligne and montant:
            comptable, engage, dispo = _solde_disponible_ligne(
                ligne, exclude_da_pk=(self.instance.pk if self.instance and self.instance.pk else None),
            )
            if montant > dispo:
                raise forms.ValidationError(
                    f"Solde insuffisant sur la ligne {ligne.code_nature} — {ligne.libelle_nature}. "
                    f"Disponible réel : {dispo:,.0f} FCFA "
                    f"(solde {comptable:,.0f} − déjà engagé {engage:,.0f} par d'autres DA). "
                    f"Montant demandé : {montant:,.0f} FCFA."
                )
        return cleaned


class DemandeAchatEditForm(forms.ModelForm):
    """Formulaire d'édition d'une DA existante."""
    class Meta:
        model = DemandeAchat
        fields = ['reference', 'ligne_budgetaire', 'objet', 'montant_estime',
                  'nature_prestation', 'periode_engagement', 'priorite']
        widgets = {
            'reference': forms.TextInput(attrs={'class': 'form-control'}),
            'ligne_budgetaire': forms.Select(attrs={'class': 'form-select'}),
            'objet': forms.TextInput(attrs={'class': 'form-control'}),
            'montant_estime': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '1000',
            }),
            'nature_prestation': forms.Select(attrs={'class': 'form-select'}),
            'periode_engagement': forms.Select(attrs={'class': 'form-select'}),
            'priorite': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        exercice = kwargs.pop('exercice', None)
        super().__init__(*args, **kwargs)
        qs = LigneBudgetaire.objects.none()
        if exercice:
            qs = (
                LigneBudgetaire.objects
                .filter(tache__exercice=exercice, actif=True)
                .select_related('tache')
                .order_by('tache__numero', 'code_nature')
            )
        self.fields['ligne_budgetaire'].queryset = qs
        self.fields['ligne_budgetaire'].label_from_instance = (
            lambda obj: f"{obj.tache.numero} › {obj.code_nature} — {obj.libelle_nature}"
        )

    def clean(self):
        cleaned = super().clean()
        ligne = cleaned.get('ligne_budgetaire')
        montant = cleaned.get('montant_estime')
        if ligne and montant:
            comptable, engage, dispo = _solde_disponible_ligne(
                ligne, exclude_da_pk=(self.instance.pk if self.instance and self.instance.pk else None),
            )
            if montant > dispo:
                raise forms.ValidationError(
                    f"Solde insuffisant sur la ligne {ligne.code_nature} — {ligne.libelle_nature}. "
                    f"Disponible réel : {dispo:,.0f} FCFA "
                    f"(solde {comptable:,.0f} − déjà engagé {engage:,.0f} par d'autres DA). "
                    f"Montant demandé : {montant:,.0f} FCFA."
                )
        return cleaned


class BonCommandeForm(forms.ModelForm):
    class Meta:
        model = BonCommande
        fields = ['numero', 'tache', 'prestataire', 'montant_ht', 'delai_execution_jours']
        widgets = {
            'numero': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex: BC-DRH-2026-042 (laisser vide pour auto-génération)',
            }),
            'tache': forms.Select(attrs={'class': 'form-select'}),
            'prestataire': forms.Select(attrs={'class': 'form-select'}),
            'montant_ht': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '1000',
            }),
            'delai_execution_jours': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '1',
                'placeholder': 'Délai en jours',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['numero'].required = False
        self.fields['numero'].label = "Numéro BC (optionnel)"


class BonCommandeEditForm(forms.ModelForm):
    """Formulaire d'édition d'un BC (champs modifiables selon statut)."""
    class Meta:
        model = BonCommande
        fields = ['numero', 'objet', 'numero_capri', 'date_capri',
                  'montant_ht', 'taux_tva',
                  'condition_paiement', 'rib_paiement',
                  'date_notification', 'delai_execution_semaines', 'date_echeance']
        widgets = {
            'numero': forms.TextInput(attrs={'class': 'form-control'}),
            'objet': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'numero_capri': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': 'Ex : CAPRI-2026-00143',
            }),
            'date_capri': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }, format='%Y-%m-%d'),
            'montant_ht': forms.NumberInput(attrs={'class': 'form-control', 'step': '1000'}),
            'taux_tva': forms.NumberInput(attrs={
                'class': 'form-control', 'step': '0.01',
            }),
            'condition_paiement': forms.Select(attrs={'class': 'form-select'}),
            'rib_paiement': forms.TextInput(attrs={
                'class': 'form-control', 'placeholder': '10003 03900 06000053467 94',
            }),
            'date_notification': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }, format='%Y-%m-%d'),
            'delai_execution_semaines': forms.NumberInput(attrs={
                'class': 'form-control', 'min': '1', 'max': '52', 'placeholder': 'Semaines',
            }),
            'date_echeance': forms.DateInput(attrs={
                'class': 'form-control', 'type': 'date',
            }, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in ['objet', 'rib_paiement', 'date_notification',
                  'delai_execution_semaines', 'date_echeance']:
            self.fields[f].required = False
        # Règle R11 : CAPRI obligatoire (n° + date)
        self.fields['numero_capri'].required = True
        self.fields['date_capri'].required = True
        self.fields['date_notification'].input_formats = ['%Y-%m-%d']
        self.fields['date_echeance'].input_formats = ['%Y-%m-%d']
        self.fields['date_capri'].input_formats = ['%Y-%m-%d']


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


class ConsommationDirecteForm(forms.ModelForm):
    class Meta:
        model = ConsommationDirecte
        fields = ['motif', 'montant', 'description', 'date_consommation',
                  'numero_capri', 'date_capri']
        widgets = {
            'motif': forms.Select(attrs={'class': 'form-select'}),
            'montant': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '0',
                'step': '1',
                'min': '1',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Ex : Assistance sociale urgente pour l\'agent…',
            }),
            'date_consommation': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }, format='%Y-%m-%d'),
            'numero_capri': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ex : CAPRI-2026-00143',
            }),
            'date_capri': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }, format='%Y-%m-%d'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Règle R11 : l'avis CAPRI est obligatoire pour toute imputation
        self.fields['numero_capri'].required = True
        self.fields['date_capri'].required = True
        self.fields['date_consommation'].input_formats = ['%Y-%m-%d']
        self.fields['date_capri'].input_formats = ['%Y-%m-%d']


# ──────────────────────────────────────────────────────────────
# FORMSET — Lignes d'articles d'un Bon de Commande (format réel PAD)
# ──────────────────────────────────────────────────────────────

LigneBCFormSet = forms.inlineformset_factory(
    BonCommande,
    LigneBC,
    fields=['reference_article', 'designation', 'unite', 'quantite', 'prix_unitaire_ht'],
    extra=4,
    can_delete=True,
    widgets={
        'reference_article': forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Ex: SER000072',
        }),
        'designation': forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': "Désignation de l'article / prestation",
        }),
        'unite': forms.Select(attrs={'class': 'form-select form-select-sm'}),
        'quantite': forms.NumberInput(attrs={
            'class': 'form-control form-control-sm ligne-qte',
            'step': '0.01', 'min': '0',
        }),
        'prix_unitaire_ht': forms.NumberInput(attrs={
            'class': 'form-control form-control-sm ligne-pu',
            'step': '100', 'min': '0',
        }),
    },
)
