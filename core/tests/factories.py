"""Factories de test (factory_boy)."""

import factory
from decimal import Decimal
from datetime import date
from core.models import (
    Utilisateur, ExerciceBudgetaire, Tache, Prestataire,
    DemandeAchat, BonCommande, LigneBudgetaire,
)


class UtilisateurFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Utilisateur
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@test.cm")
    role = 'assistante_drh'
    nom_complet = factory.Faker('name', locale='fr_FR')
    is_active = True
    must_change_password = False

    @factory.post_generation
    def password(obj, create, extracted, **kwargs):
        obj.set_password(extracted or 'testpassword')
        if create:
            obj.save()


class ExerciceBudgetaireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ExerciceBudgetaire

    annee = factory.Sequence(lambda n: 2024 + n)
    date_debut = factory.LazyAttribute(lambda o: date(o.annee, 1, 1))
    date_fin = factory.LazyAttribute(lambda o: date(o.annee, 12, 31))
    montant_global = Decimal('500000000')
    statut = 'actif'


class TacheFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Tache
        skip_postgeneration_save = True

    exercice = factory.SubFactory(ExerciceBudgetaireFactory)
    numero = factory.Sequence(lambda n: f"T-{n:03d}")
    titre = factory.Faker('catch_phrase', locale='fr_FR')

    @factory.post_generation
    def montant_initial(obj, create, extracted, **kwargs):
        """
        Compat tests : le budget est désormais porté par LigneBudgetaire.
        Crée automatiquement une ligne active dont le montant = `montant_initial`
        (défaut 10 000 000). Permet TacheFactory(montant_initial=...) comme avant.
        """
        if not create:
            return
        montant = extracted if extracted is not None else Decimal('10000000')
        LigneBudgetaire.objects.create(
            tache=obj, code_nature='60410', libelle_nature='Fournitures',
            montant_initial=montant, actif=True,
        )


class LigneBudgetaireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = LigneBudgetaire

    tache = factory.SubFactory(TacheFactory)
    code_nature = factory.Sequence(lambda n: f"6041{n:03d}")
    libelle_nature = 'Fournitures de bureau'
    montant_initial = Decimal('10000000')
    actif = True


class PrestataireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Prestataire

    code = factory.Sequence(lambda n: f"PREST-{n:03d}")
    nom = factory.Faker('company', locale='fr_FR')
    adresse = "Douala"
    telephone = "+237 233 00 00 00"
    email = factory.LazyAttribute(lambda o: f"contact@{o.nom.lower().replace(' ', '')[:10]}.cm")


class DemandeAchatFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DemandeAchat

    reference = factory.Sequence(lambda n: f"DA-TEST-{n:03d}")
    exercice = factory.SubFactory(ExerciceBudgetaireFactory)
    ligne_budgetaire = factory.SubFactory(LigneBudgetaireFactory)
    objet = factory.Faker('sentence', nb_words=4, locale='fr_FR')
    montant_estime = Decimal('500000')
    statut = 'cree'


class BonCommandeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BonCommande

    numero = factory.Sequence(lambda n: f"BC-2025-{n:04d}")
    tache = factory.SubFactory(TacheFactory)
    exercice = factory.SubFactory(ExerciceBudgetaireFactory)
    prestataire = factory.SubFactory(PrestataireFactory)
    montant_ht = Decimal('1000000')
    montant_tva = Decimal('192500')
    montant_ttc = Decimal('1192500')
    statut = 'cree'
