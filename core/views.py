import csv
import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.password_validation import validate_password
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import urlencode, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from functools import wraps
from decimal import Decimal
from .models import (
    Utilisateur, ExerciceBudgetaire, Tache, VirementBudgetaire,
    Prestataire, DemandeAchat, Offre, BonCommande, LigneBC,
    JournalActivite, Notification, Alerte, HistoriqueStatut, PieceJointe,
)
from .forms import VirementForm, PrestataireForm, TacheForm, DemandeAchatForm, BonCommandeForm, OffreSolliciterForm, OffreSaisirForm, OffreRefuserForm
from .filters import BonCommandeFilter, DemandeAchatFilter, JournalFilter, PrestataireFilter
from .services import (
    BonCommandeService, DemandeAchatService, NotificationService,
    SequenceService, TacheService, VirementService,
)
import logging
security_logger = logging.getLogger('budgetpad.security')
app_logger = logging.getLogger('budgetpad')

PAGE_SIZE = 25


def _paginate(request, queryset, page_size=PAGE_SIZE):
    """Pagine un queryset et renvoie (page_obj, querystring_sans_page)."""
    paginator = Paginator(queryset, page_size)
    page_obj = paginator.get_page(request.GET.get('page'))
    qd = request.GET.copy()
    qd.pop('page', None)
    querystring = urlencode(qd, doseq=True)
    return page_obj, querystring


def _safe_referer_redirect(request, fallback='dashboard'):
    """Redirige vers le Referer uniquement s'il appartient au même hôte."""
    referer = request.META.get('HTTP_REFERER', '')
    if referer and url_has_allowed_host_and_scheme(referer, allowed_hosts={request.get_host()}):
        return redirect(referer)
    return redirect(fallback)


def _exercice_courant(request):
    """
    Resoud l'exercice a utiliser dans la requete :
    - session['exercice_annee'] si defini
    - sinon l'exercice 'actif'
    - sinon le plus recent
    """
    annee = request.session.get('exercice_annee')
    if annee:
        ex = ExerciceBudgetaire.objects.filter(annee=annee).first()
        if ex:
            return ex
    return ExerciceBudgetaire.get_actif() or ExerciceBudgetaire.objects.order_by('-annee').first()


# ============ HELPERS ============

def log_action(user, type_action, description, entite_type='', entite_id=None):
    """Enregistre une action dans le journal d'activité."""
    JournalActivite.objects.create(
        type_action=type_action,
        description=description,
        entite_type=entite_type,
        entite_id=entite_id,
        utilisateur=user
    )

def role_required(*roles):
    """Décorateur pour vérifier le rôle de l'utilisateur. À chaîner après @login_required."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            user_role = getattr(request.user, 'role', None)
            if user_role in roles or user_role == 'admin':
                return view_func(request, *args, **kwargs)
            messages.error(request, "Vous n'avez pas les droits pour cette action.")
            return redirect('dashboard')
        return wrapper
    return decorator


# ============ AUTH ============

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            security_logger.info("LOGIN_SUCCESS user=%s ip=%s", username, request.META.get('REMOTE_ADDR'))
            return redirect('dashboard')
        security_logger.warning("LOGIN_FAILED user=%s ip=%s", username, request.META.get('REMOTE_ADDR'))
        messages.error(request, "Identifiants incorrects.")
    return render(request, 'registration/login.html')

@require_POST
def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def password_change_forced_view(request):
    """Page de changement de mot de passe imposee au 1er login."""
    if request.method == 'POST':
        ancien = request.POST.get('old_password', '')
        nouveau = request.POST.get('new_password', '')
        confirm = request.POST.get('new_password_confirm', '')

        if not request.user.check_password(ancien):
            messages.error(request, "Ancien mot de passe incorrect.")
        elif nouveau != confirm:
            messages.error(request, "Les deux nouveaux mots de passe ne correspondent pas.")
        elif nouveau == ancien:
            messages.error(request, "Le nouveau mot de passe doit être différent de l'ancien.")
        else:
            try:
                validate_password(nouveau, request.user)
            except ValidationError as e:
                for msg in e.messages:
                    messages.error(request, msg)
                return render(request, 'registration/password_change_forced.html')
            request.user.set_password(nouveau)
            request.user.must_change_password = False
            request.user.save(update_fields=['password', 'must_change_password'])
            # set_password invalide la session courante ; on reconnecte.
            # En presence de plusieurs backends d'auth (axes + ModelBackend),
            # il faut indiquer explicitement lequel utiliser.
            login(request, request.user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, "Mot de passe modifié avec succès.")
            return redirect('dashboard')

    return render(request, 'registration/password_change_forced.html')


# ============ DASHBOARD ============

def _get_periode_filter(request, bcs_qs):
    """Filtre un queryset de BC selon le paramètre GET 'periode'."""
    periode = request.GET.get('periode', 'annuel')
    if periode == 'mensuel':
        now = timezone.now()
        bcs_qs = bcs_qs.filter(created_at__year=now.year, created_at__month=now.month)
    elif periode == 'trimestriel':
        now = timezone.now()
        quarter_start_month = ((now.month - 1) // 3) * 3 + 1
        bcs_qs = bcs_qs.filter(
            created_at__year=now.year,
            created_at__month__gte=quarter_start_month,
        )
    return bcs_qs, periode


@login_required
def dashboard_view(request):
    exercice = _exercice_courant(request)
    if not exercice:
        return render(request, 'core/dashboard.html', {'exercice': None})

    taches = Tache.objects.filter(exercice=exercice).with_aggregates()
    bcs_base = BonCommande.objects.filter(exercice=exercice)
    bcs, periode = _get_periode_filter(request, bcs_base)

    budget_total = exercice.montant_global
    total_engage = bcs.exclude(statut='annule').aggregate(t=Sum('montant_ttc'))['t'] or 0
    solde = budget_total - total_engage
    taux_global = round((float(total_engage) / float(budget_total)) * 100, 1) if budget_total > 0 else 0
    taux_disponible = round(100 - taux_global, 1)

    taches_top = sorted(taches, key=lambda t: float(t.taux_consommation), reverse=True)[:5]
    top_labels = [t.numero for t in taches_top]
    top_data = [float(t.taux_consommation) for t in taches_top]
    top_colors = ['#E74C3C' if d >= 90 else '#F39C12' if d >= 70 else '#1A5632' for d in top_data]

    derniers_bc = bcs.select_related('tache', 'prestataire').order_by('-created_at')[:5]
    alertes = Alerte.objects.filter(lu=False).order_by('-created_at')[:5]

    bc_counts = bcs.aggregate(
        cree=Count('id', filter=Q(statut='cree')),
        notifie=Count('id', filter=Q(statut='notifie')),
        en_cours=Count('id', filter=Q(statut='en_cours')),
        execute=Count('id', filter=Q(statut='execute')),
        annule=Count('id', filter=Q(statut='annule')),
        total=Count('id'),
        actifs=Count('id', filter=~Q(statut__in=['annule', 'execute'])),
    )

    context = {
        'exercice': exercice,
        'periode': periode,
        'budget_total': budget_total,
        'total_engage': total_engage,
        'solde': solde,
        'taux_global': taux_global,
        'taux_disponible': taux_disponible,
        'bc_actifs': bc_counts['actifs'],
        'nb_bc_total': bc_counts['total'],
        'top_labels': top_labels,
        'top_data': top_data,
        'top_colors': top_colors,
        'donut_data': [float(total_engage), max(0.0, float(solde))],
        'derniers_bc': derniers_bc,
        'alertes': alertes,
        'bc_counts': bc_counts,
    }
    return render(request, 'core/dashboard.html', context)


# ============ TACHES ============

@login_required
def taches_list(request):
    exercice = _exercice_courant(request)
    if exercice:
        taches = Tache.objects.filter(exercice=exercice).with_aggregates()
    else:
        taches = Tache.objects.none()
    return render(request, 'core/taches_list.html', {'exercice': exercice, 'taches': taches})

@login_required
def tache_detail(request, pk):
    tache = get_object_or_404(Tache.objects.with_aggregates(), pk=pk)
    bcs = tache.bons_commande.select_related('prestataire').order_by('-created_at')
    return render(request, 'partials/_tache_detail.html', {'tache': tache, 'bcs': bcs})


@login_required
@role_required('admin', 'assistante_drh')
@require_POST
def tache_create(request):
    form = TacheForm(request.POST)
    if form.is_valid():
        exercice = ExerciceBudgetaire.get_actif()
        if exercice is None:
            messages.error(request, "Aucun exercice budgétaire actif.")
            return redirect('taches_list')
        tache = form.save(commit=False)
        tache.exercice = exercice
        tache.numero = SequenceService.next_tache_numero(exercice.annee)
        tache.save()
        log_action(request.user, 'Tache.create', f"Création de la tâche {tache.numero} — {tache.titre}", 'tache', tache.id)
        messages.success(request, f"Tâche {tache.numero} créée avec succès.")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    return redirect('taches_list')

@login_required
@role_required('admin', 'assistante_drh')
@require_POST
def tache_delete(request, pk):
    tache = get_object_or_404(Tache, pk=pk)
    has_linked = (
        tache.bons_commande.exists()
        or tache.demandes_achat.exists()
        or tache.virements_sortants.exists()
        or tache.virements_entrants.exists()
    )
    if has_linked:
        messages.error(request, "Impossible de supprimer une tâche avec des BC, DA ou virements associés.")
    else:
        log_action(request.user, 'Tache.delete', f"Suppression de la tâche {tache.numero} — {tache.titre}", 'tache', tache.id)
        tache.delete()
        messages.success(request, "Tâche supprimée.")
    return redirect('taches_list')


# ============ TRANSFERTS ============

@login_required
def virements_list(request):
    exercice = _exercice_courant(request)
    qs = VirementBudgetaire.objects.select_related('tache_source', 'tache_dest', 'created_by').all()
    page_obj, querystring = _paginate(request, qs)
    # Pré-annote pour éviter N+1 sur .solde dans le modal
    taches = (
        Tache.objects.filter(exercice=exercice).with_aggregates().order_by('numero')
        if exercice else []
    )
    return render(request, 'core/virements_list.html', {
        'virements': page_obj.object_list,
        'page_obj': page_obj,
        'querystring': querystring,
        'taches': taches,
        'exercice': exercice,
    })

@login_required
@role_required('admin', 'assistante_drh')
@require_POST
def virement_create(request):
    exercice = ExerciceBudgetaire.get_actif()
    form = VirementForm(request.POST, exercice=exercice)
    if form.is_valid():
        try:
            virement = VirementService.creer_virement(
                tache_source=form.cleaned_data['tache_source'],
                tache_dest=form.cleaned_data['tache_dest'],
                montant=form.cleaned_data['montant'],
                motif=form.cleaned_data['motif'],
                utilisateur=request.user
            )
            messages.success(request, f"Virement de {virement.montant:,.0f} FCFA effectué avec succès.")
        except ValueError as e:
            messages.error(request, str(e))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")

    return redirect('virements_list')


@login_required
def virement_detail(request, pk):
    v = get_object_or_404(
        VirementBudgetaire.objects.select_related('tache_source', 'tache_dest', 'created_by'),
        pk=pk
    )
    return render(request, 'partials/_virement_detail.html', {'v': v})


# ============ PRESTATAIRES ============

@login_required
def prestataires_list(request):
    f = PrestataireFilter(request.GET, queryset=Prestataire.objects.all())
    page_obj, querystring = _paginate(request, f.qs)
    return render(request, 'core/prestataires_list.html', {
        'prestataires': page_obj.object_list,
        'page_obj': page_obj,
        'querystring': querystring,
        'filter': f,
    })

@login_required
@role_required('admin', 'dag')
@require_POST
def prestataire_create(request):
    form = PrestataireForm(request.POST)
    if form.is_valid():
        prestataire = form.save(commit=False)
        prestataire.code = SequenceService.next_prestataire_code()
        prestataire.save()
        log_action(request.user, 'Prestataire.create', f"Création du prestataire {prestataire.nom}", 'prestataire', prestataire.id)
        messages.success(request, f"Prestataire {prestataire.nom} ajouté avec succès.")
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    return redirect('prestataires_list')

@login_required
@role_required('admin', 'dag')
@require_POST
def prestataire_delete(request, pk):
    prest = get_object_or_404(Prestataire, pk=pk)
    if prest.bons_commande.exists():
        messages.error(request, "Impossible de supprimer un prestataire lié à des BC.")
    else:
        log_action(request.user, 'Prestataire.delete', f"Suppression du prestataire {prest.nom}", 'prestataire', prest.id)
        prest.delete()
        messages.success(request, "Prestataire supprimé.")
    return redirect('prestataires_list')


@login_required
def prestataire_detail(request, pk):
    prest = get_object_or_404(Prestataire, pk=pk)
    bcs = prest.bons_commande.select_related('tache', 'exercice').order_by('-created_at')
    total_ttc = bcs.exclude(statut='annule').aggregate(t=Sum('montant_ttc'))['t'] or Decimal('0')
    return render(request, 'partials/_prestataire_detail.html', {
        'prest': prest, 'bcs': bcs, 'total_ttc': total_ttc,
    })


# ============ DEMANDES D'ACHAT ============

@login_required
def da_list(request):
    exercice = _exercice_courant(request)
    base_qs = DemandeAchat.objects.select_related('tache', 'created_by')
    if exercice:
        base_qs = base_qs.filter(exercice=exercice)
    f = DemandeAchatFilter(request.GET, queryset=base_qs)
    page_obj, querystring = _paginate(request, f.qs)
    taches = exercice.taches.all() if exercice else []
    return render(request, 'core/da_list.html', {
        'demandes': page_obj.object_list,
        'page_obj': page_obj,
        'querystring': querystring,
        'filter': f,
        'taches': taches,
    })

@login_required
@role_required('admin', 'directeur_drh', 'assistante_drh')
@require_POST
def da_create(request):
    form = DemandeAchatForm(request.POST)
    if form.is_valid():
        try:
            da = DemandeAchatService.creer(
                tache=form.cleaned_data['tache'],
                objet=form.cleaned_data['objet'],
                montant_estime=form.cleaned_data['montant_estime'],
                utilisateur=request.user,
            )
            messages.success(request, f"Demande {da.reference} créée.")
        except ValueError as e:
            messages.error(request, str(e))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                messages.error(request, f"{field}: {error}")
    return redirect('da_list')

@login_required
@role_required('dag')
@require_POST
@transaction.atomic
def da_en_etude(request, pk):
    """Passe une DA de « créée » à « en étude » (instruction DAG)."""
    da = get_object_or_404(DemandeAchat, pk=pk)
    peut, msg = da.peut_transiter_vers('en_etude')
    if not peut:
        messages.error(request, msg)
        return redirect('da_list')
    ancien = da.statut
    da.statut = 'en_etude'
    da.save(update_fields=['statut'])
    HistoriqueStatut.objects.create(
        type_entite='DA', entite_id=da.id,
        ancien_statut=ancien, nouveau_statut='en_etude',
        utilisateur=request.user,
    )
    log_action(request.user, 'DA.en_etude', f"Mise en étude de {da.reference}", 'da', da.id)
    app_logger.info("DA en étude : %s par %s", da.reference, request.user.username)
    messages.info(request, f"{da.reference} mise en étude.")
    return redirect('da_list')


@login_required
@role_required('dag')
@require_POST
@transaction.atomic
def da_valider(request, pk):
    """Valide une DA (uniquement depuis en_étude, avec offres + PJ)."""
    da = get_object_or_404(DemandeAchat, pk=pk)
    peut, msg = da.peut_transiter_vers('validee')
    if not peut:
        messages.error(request, msg)
        return redirect('da_list')
    ancien = da.statut
    da.statut = 'validee'
    da.save(update_fields=['statut'])
    HistoriqueStatut.objects.create(
        type_entite='DA', entite_id=da.id,
        ancien_statut=ancien, nouveau_statut='validee',
        utilisateur=request.user,
    )
    log_action(request.user, 'DA.validate', f"Validation de {da.reference}", 'da', da.id)
    if da.created_by_id and da.created_by_id != request.user.id:
        NotificationService.notifier(
            utilisateur=da.created_by,
            type_notif='da_validee',
            titre=f"{da.reference} validée",
            message=f"Votre demande « {da.objet} » a été validée par le DAG.",
            entite_type='da', entite_id=da.id,
        )
    app_logger.info("DA validée : %s par %s", da.reference, request.user.username)
    messages.success(request, f"{da.reference} validée.")
    return redirect('da_list')


@login_required
@role_required('dag')
@require_POST
@transaction.atomic
def da_refuser(request, pk):
    """Refuse une DA (uniquement depuis en_étude, motif obligatoire)."""
    da = get_object_or_404(DemandeAchat, pk=pk)
    motif = request.POST.get('motif', '').strip()
    if not motif:
        messages.error(request, "Motif de refus obligatoire.")
        return redirect('da_list')
    # Pré-remplir le champ pour que peut_transiter_vers() puisse le vérifier
    da.motif_refus = motif
    peut, msg = da.peut_transiter_vers('refusee')
    if not peut:
        messages.error(request, msg)
        return redirect('da_list')
    ancien = da.statut
    da.statut = 'refusee'
    da.save(update_fields=['statut', 'motif_refus'])
    HistoriqueStatut.objects.create(
        type_entite='DA', entite_id=da.id,
        ancien_statut=ancien, nouveau_statut='refusee',
        utilisateur=request.user, commentaire=motif,
    )
    log_action(request.user, 'DA.refuse', f"Refus de {da.reference} : {motif}", 'da', da.id)
    if da.created_by_id and da.created_by_id != request.user.id:
        NotificationService.notifier(
            utilisateur=da.created_by,
            type_notif='da_refusee',
            titre=f"{da.reference} refusée",
            message=f"Votre demande a été refusée. Motif : {motif}",
            entite_type='da', entite_id=da.id,
        )
    app_logger.info("DA refusée : %s par %s (motif=%s)", da.reference, request.user.username, motif)
    messages.warning(request, f"{da.reference} refusée.")
    return redirect('da_list')


@login_required
def da_detail(request, pk):
    da = get_object_or_404(
        DemandeAchat.objects.select_related('tache', 'created_by')
                            .prefetch_related('offres__prestataire', 'bons_commande'),
        pk=pk
    )
    offres = da.offres.select_related('prestataire').order_by('date_sollicitation')
    nb_contactes = offres.count()
    nb_recues    = offres.filter(statut__in=['recue', 'retenue', 'refusee']).count()
    nb_en_retard = sum(1 for o in offres if o.est_en_retard)
    # Prestataires pas encore sollicités pour ce DA
    prest_deja_ids = list(offres.values_list('prestataire_id', flat=True))
    form_solliciter = OffreSolliciterForm()
    form_solliciter.fields['prestataire'].queryset = (
        Prestataire.objects.exclude(pk__in=prest_deja_ids).order_by('nom')
    )
    pieces_jointes = PieceJointe.objects.filter(type_entite='da', entite_id=pk).select_related('uploaded_by')
    return render(request, 'partials/_da_detail.html', {
        'da': da,
        'offres': offres,
        'nb_contactes': nb_contactes,
        'nb_recues': nb_recues,
        'nb_en_retard': nb_en_retard,
        'form_solliciter': form_solliciter,
        'can_manage': request.user.role in ('admin', 'dag'),
        'pieces_jointes': pieces_jointes,
    })


@login_required
@role_required('admin', 'dag')
@require_POST
def offre_solliciter(request, da_pk):
    """Sollicite un prestataire pour une DA — crée une offre en_attente sans montant."""
    da = get_object_or_404(DemandeAchat, pk=da_pk)
    form = OffreSolliciterForm(request.POST)
    if form.is_valid():
        prestataire = form.cleaned_data['prestataire']
        if Offre.objects.filter(demande=da, prestataire=prestataire).exists():
            messages.warning(
                request,
                f"« {prestataire.nom} » a déjà été sollicité pour {da.reference}."
            )
        else:
            Offre.objects.create(demande=da, prestataire=prestataire, statut='en_attente')
            log_action(
                request.user, 'Offre.solliciter',
                f"Sollicitation de {prestataire.nom} pour {da.reference}", 'da', da.pk
            )
            messages.success(request, f"« {prestataire.nom} » sollicité pour {da.reference}.")
    else:
        messages.error(request, "Veuillez sélectionner un prestataire valide.")
    return redirect('da_list')


@login_required
@role_required('admin', 'dag')
@require_POST
def offre_saisir(request, pk):
    """Enregistre le montant d'une offre reçue et passe son statut à 'recue'."""
    from django.utils import timezone as tz
    offre = get_object_or_404(Offre, pk=pk)
    if offre.statut != 'en_attente':
        messages.warning(request, "Cette offre a déjà été enregistrée.")
        return redirect('da_list')
    form = OffreSaisirForm(request.POST)
    if form.is_valid():
        offre.montant        = form.cleaned_data['montant']
        offre.statut         = 'recue'
        offre.date_reception = tz.now()
        offre.save()
        log_action(
            request.user, 'Offre.saisir',
            f"Saisie offre {offre.prestataire.nom} : {offre.montant:,.0f} FCFA "
            f"pour {offre.demande.reference}",
            'da', offre.demande.pk
        )
        messages.success(
            request,
            f"Offre de « {offre.prestataire.nom} » enregistrée : {offre.montant:,.0f} FCFA."
        )
    else:
        messages.error(request, "Montant invalide — veuillez saisir un montant positif.")
    return redirect('da_list')


@login_required
@role_required('admin', 'dag', 'directeur_drh')
@require_POST
@transaction.atomic
def offre_retenir(request, pk):
    """Retient une offre (reçue → retenue) et refuse automatiquement toutes les autres reçues."""
    offre = get_object_or_404(Offre.objects.select_related('demande', 'prestataire'), pk=pk)
    peut, msg = offre.peut_transiter_vers('retenue')
    if not peut:
        messages.error(request, msg)
        return redirect('da_list')

    offre.statut = 'retenue'
    offre.save(update_fields=['statut'])

    # Auto-refuser toutes les autres offres reçues de la même DA
    autres_refusees = offre.demande.offres.filter(statut='recue').exclude(pk=pk)
    nb_refusees = autres_refusees.count()
    autres_refusees.update(statut='refusee')

    log_action(
        request.user, 'Offre.retenir',
        f"Offre retenue : {offre.prestataire.nom} ({offre.montant:,.0f} FCFA) "
        f"pour {offre.demande.reference} — {nb_refusees} autre(s) auto-refusée(s)",
        'da', offre.demande.pk,
    )
    app_logger.info(
        "Offre retenue : %s pour DA %s par %s",
        offre.prestataire.nom, offre.demande.reference, request.user.username,
    )
    messages.success(
        request,
        f"Offre de « {offre.prestataire.nom} » retenue."
        + (f" {nb_refusees} autre(s) offre(s) automatiquement refusée(s)." if nb_refusees else ""),
    )
    return redirect('da_list')


@login_required
@role_required('admin', 'dag', 'directeur_drh')
@require_POST
@transaction.atomic
def offre_refuser(request, pk):
    """Refuse manuellement une offre reçue (motif obligatoire)."""
    offre = get_object_or_404(Offre.objects.select_related('demande', 'prestataire'), pk=pk)
    form = OffreRefuserForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Motif de refus obligatoire.")
        return redirect('da_list')
    motif = form.cleaned_data['motif']

    peut, msg = offre.peut_transiter_vers('refusee')
    if not peut:
        messages.error(request, msg)
        return redirect('da_list')

    offre.statut = 'refusee'
    offre.motif_refus = motif
    offre.save(update_fields=['statut', 'motif_refus'])

    log_action(
        request.user, 'Offre.refuser',
        f"Offre refusée : {offre.prestataire.nom} pour {offre.demande.reference} — {motif}",
        'da', offre.demande.pk,
    )
    messages.warning(
        request, f"Offre de « {offre.prestataire.nom} » refusée."
    )
    return redirect('da_list')


# ============ BONS DE COMMANDE ============

@login_required
def bc_list(request):
    exercice = _exercice_courant(request)
    base_qs = BonCommande.objects.select_related('tache', 'prestataire', 'exercice')
    if exercice:
        base_qs = base_qs.filter(exercice=exercice)
    f = BonCommandeFilter(request.GET, queryset=base_qs)
    bc_counts = base_qs.aggregate(
        cree=Count('id', filter=Q(statut='cree')),
        notifie=Count('id', filter=Q(statut='notifie')),
        en_cours=Count('id', filter=Q(statut='en_cours')),
        execute=Count('id', filter=Q(statut='execute')),
        annule=Count('id', filter=Q(statut='annule')),
    )
    page_obj, querystring = _paginate(request, f.qs)
    exercice_actif = ExerciceBudgetaire.get_actif()
    # Pré-annote les tâches pour éviter N+1 (accès à .solde dans le modal)
    taches_actif = (
        Tache.objects.filter(exercice=exercice_actif).with_aggregates().order_by('numero')
        if exercice_actif else Tache.objects.none()
    )
    # DAs validées avec offre retenue — utilisées pour le modal "Créer BC"
    das_validees = (
        DemandeAchat.objects
        .filter(statut='validee', exercice=exercice_actif)
        .prefetch_related('offres__prestataire')
        .select_related('tache')
        .order_by('reference')
        if exercice_actif else DemandeAchat.objects.none()
    )
    # Ne garder que celles qui ont effectivement 1 offre retenue
    das_validees = [da for da in das_validees if da.offres.filter(statut='retenue').exists()]

    return render(request, 'core/bc_list.html', {
        'bcs': page_obj.object_list,
        'page_obj': page_obj,
        'querystring': querystring,
        'filter': f,
        'exercice': exercice,
        'exercice_actif': exercice_actif,
        'taches_actif': taches_actif,
        'bc_counts': bc_counts,
        'all_prestataires': Prestataire.objects.order_by('nom'),
        'das_validees': das_validees,
    })

@login_required
@role_required('dag')
@require_POST
@transaction.atomic
def bc_create(request):
    """Crée un BC depuis une DA validée ; prestataire + montant auto-remplis depuis l'offre retenue."""
    da_id = request.POST.get('da_id', '').strip()
    if not da_id:
        messages.error(request, "Veuillez sélectionner une demande d'achat validée.")
        return redirect('bc_list')

    try:
        da = DemandeAchat.objects.select_related('tache').prefetch_related('offres__prestataire').get(pk=int(da_id))
    except (DemandeAchat.DoesNotExist, ValueError):
        messages.error(request, "Demande d'achat introuvable.")
        return redirect('bc_list')

    # Vérifier que la DA peut générer un BC (validee → bc_cree)
    peut, msg = da.peut_transiter_vers('bc_cree')
    if not peut:
        messages.error(request, msg)
        return redirect('bc_list')

    offre_retenue = da.offres.filter(statut='retenue').select_related('prestataire').first()
    if not offre_retenue:
        messages.error(request, f"Aucune offre retenue pour {da.reference}.")
        return redirect('bc_list')

    if not offre_retenue.montant or offre_retenue.montant <= 0:
        messages.error(request, "L'offre retenue n'a pas de montant valide.")
        return redirect('bc_list')

    try:
        bc = BonCommandeService.creer(
            tache=da.tache,
            prestataire=offre_retenue.prestataire,
            montant_ht=offre_retenue.montant,
            utilisateur=request.user,
            demande=da,
        )
        TacheService.verifier_alertes(bc.tache)
        app_logger.info("BC %s créé depuis DA %s par %s", bc.numero, da.reference, request.user.username)
        messages.success(request, f"Bon de commande {bc.numero} créé (DA : {da.reference}).")
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('bc_list')

@login_required
def bc_pdf(request, pk):
    """Telecharge le PDF officiel du BC."""
    from .services.pdf_service import generer_pdf_bon_commande
    bc = get_object_or_404(
        BonCommande.objects.select_related('tache', 'prestataire', 'exercice'),
        pk=pk,
    )
    pdf_bytes = generer_pdf_bon_commande(bc)
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="BC-{bc.numero}.pdf"'
    app_logger.info("PDF BC %s genere par %s", bc.numero, request.user.username)
    return response


@login_required
@role_required('dag')
@require_POST
def bc_change_statut(request, pk, nouveau_statut):
    bc = get_object_or_404(BonCommande, pk=pk)
    motif = request.POST.get('motif', '').strip()

    # Motif obligatoire pour annulation
    if nouveau_statut == 'annule' and not motif:
        messages.error(request, "Motif d'annulation obligatoire.")
        return redirect('bc_list')

    try:
        result = BonCommandeService.changer_statut(
            bc, nouveau_statut, request.user, motif=motif
        )
        messages.success(request, result['message'])
        if nouveau_statut == 'annule':
            TacheService.verifier_alertes(bc.tache)
    except ValueError as e:
        messages.error(request, str(e))

    return redirect('bc_list')


@login_required
def bc_detail(request, pk):
    """Retourne le fragment HTML de détail d'un BC (pour l'offcanvas)."""
    bc = get_object_or_404(
        BonCommande.objects.select_related('tache', 'prestataire', 'exercice', 'demande')
                           .prefetch_related('lignes'),
        pk=pk
    )
    historiques    = HistoriqueStatut.objects.filter(
        type_entite='BC', entite_id=pk
    ).select_related('utilisateur').order_by('-created_at')
    pieces_jointes = PieceJointe.objects.filter(type_entite='bc', entite_id=pk).select_related('uploaded_by')
    return render(request, 'partials/_bc_detail.html', {
        'bc': bc,
        'historiques': historiques,
        'pieces_jointes': pieces_jointes,
    })


# ============ BILANS ============

@login_required
def bilans_view(request):
    exercice = _exercice_courant(request)
    if not exercice:
        return render(request, 'core/bilans.html', {'exercice': None})

    taches = Tache.objects.filter(exercice=exercice).with_aggregates()
    bcs_base = BonCommande.objects.filter(exercice=exercice)
    bcs, periode = _get_periode_filter(request, bcs_base)

    budget_total = exercice.montant_global
    consommation = bcs.exclude(statut='annule').aggregate(t=Sum('montant_ttc'))['t'] or 0
    solde = budget_total - consommation
    taux = round((float(consommation) / float(budget_total)) * 100, 1) if budget_total > 0 else 0

    taches_sorted = sorted(taches, key=lambda t: float(t.taux_consommation), reverse=True)
    chart_labels = [t.numero for t in taches_sorted]
    chart_data = [float(t.taux_consommation) for t in taches_sorted]
    chart_colors = ['#E74C3C' if d >= 90 else '#F39C12' if d >= 70 else '#1A5632' for d in chart_data]

    bc_statuts = bcs.aggregate(
        cree=Count('id', filter=Q(statut='cree')),
        notifie=Count('id', filter=Q(statut='notifie')),
        en_cours=Count('id', filter=Q(statut='en_cours')),
        execute=Count('id', filter=Q(statut='execute')),
        annule=Count('id', filter=Q(statut='annule')),
    )

    _donut_meta = [
        ('cree',     'Créé',     '#6c757d'),
        ('notifie',  'Notifié',  '#0dcaf0'),
        ('en_cours', 'En cours', '#0d6efd'),
        ('execute',  'Exécuté',  '#198754'),
        ('annule',   'Annulé',   '#dc3545'),
    ]
    bc_donut = [
        {'label': lbl, 'value': bc_statuts[key], 'color': col}
        for key, lbl, col in _donut_meta
        if bc_statuts[key] > 0
    ]

    context = {
        'exercice': exercice,
        'periode': periode,
        'budget_total': budget_total,
        'consommation': consommation,
        'solde': solde,
        'taux': taux,
        'taches': taches_sorted,
        'chart_labels': chart_labels,
        'chart_data': chart_data,
        'chart_colors': chart_colors,
        'bc_statuts': bc_statuts,
        'bc_donut': bc_donut,
    }
    return render(request, 'core/bilans.html', context)


@login_required
def bilan_csv_export(request):
    """Export CSV du bilan par tâche pour l'exercice courant."""
    exercice = _exercice_courant(request)
    if not exercice:
        messages.error(request, "Aucun exercice sélectionné.")
        return redirect('bilans')

    taches = Tache.objects.filter(exercice=exercice).with_aggregates()

    response = HttpResponse(content_type='text/csv; charset=utf-8-sig')
    response['Content-Disposition'] = (
        f'attachment; filename="bilan_{exercice.annee}.csv"'
    )
    writer = csv.writer(response, delimiter=';')
    writer.writerow(['N° Tâche', 'Titre', 'Nature', 'Budget ajusté (FCFA)',
                     'Consommation (FCFA)', 'Solde (FCFA)', 'Taux (%)'])
    for t in taches:
        writer.writerow([
            t.numero, t.titre, t.libelle_nature or t.code_nature,
            float(t.budget_ajuste), float(t.consommation),
            float(t.solde), float(t.taux_consommation),
        ])
    app_logger.info("Export CSV bilan %s par %s", exercice.annee, request.user.username)
    return response


@login_required
def bilan_pdf_export(request):
    """Génère et télécharge le rapport PDF du bilan budgétaire."""
    from .services.pdf_service import generer_pdf_bilan
    exercice = _exercice_courant(request)
    if not exercice:
        messages.error(request, "Aucun exercice sélectionné.")
        return redirect('bilans')

    taches       = list(Tache.objects.filter(exercice=exercice).with_aggregates())
    bcs_base     = BonCommande.objects.filter(exercice=exercice)
    bcs, periode = _get_periode_filter(request, bcs_base)

    budget_total = exercice.montant_global
    consommation = bcs.exclude(statut='annule').aggregate(t=Sum('montant_ttc'))['t'] or 0
    solde        = budget_total - consommation
    taux         = round((float(consommation) / float(budget_total)) * 100, 1) if budget_total > 0 else 0
    taches_sorted = sorted(taches, key=lambda t: float(t.taux_consommation), reverse=True)

    bc_statuts = bcs.aggregate(
        cree=Count('id', filter=Q(statut='cree')),
        notifie=Count('id', filter=Q(statut='notifie')),
        en_cours=Count('id', filter=Q(statut='en_cours')),
        execute=Count('id', filter=Q(statut='execute')),
        annule=Count('id', filter=Q(statut='annule')),
    )

    pdf_bytes = generer_pdf_bilan(
        exercice=exercice,
        taches=taches_sorted,
        consommation=consommation,
        budget_total=budget_total,
        solde=solde,
        taux=taux,
        bc_statuts=bc_statuts,
        periode=periode,
    )
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="bilan_{exercice.annee}_{periode}.pdf"'
    )
    app_logger.info("Export PDF bilan %s (%s) par %s", exercice.annee, periode, request.user.username)
    return response


# ============ PIÈCES JOINTES ============

@login_required
@require_POST
def piece_jointe_upload(request):
    """Upload d'une pièce jointe sur une DA ou un BC."""
    type_entite = request.POST.get('type_entite', '').strip()
    entite_id   = request.POST.get('entite_id', '').strip()
    fichier     = request.FILES.get('fichier')

    REDIRECT_MAP = {'da': 'da_list', 'bc': 'bc_list'}
    redirect_url = REDIRECT_MAP.get(type_entite, 'da_list')

    if not fichier:
        messages.error(request, "Aucun fichier sélectionné.")
        return redirect(redirect_url)

    if fichier.size > PieceJointe.TAILLE_MAX:
        messages.error(request, f"Fichier trop volumineux (max 10 Mo, reçu {fichier.size // 1024 // 1024} Mo).")
        return redirect(redirect_url)

    # Validation extension
    ext_ok = fichier.name.lower().rsplit('.', 1)[-1] in (
        'pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'doc', 'docx', 'xls', 'xlsx'
    )
    if not ext_ok:
        messages.error(request, "Type de fichier non autorisé (PDF, images, Word, Excel uniquement).")
        return redirect(redirect_url)

    type_piece = request.POST.get('type_piece', 'autre').strip()
    valid_types = {c[0] for c in PieceJointe.TYPE_PIECE_CHOICES}
    if type_piece not in valid_types:
        type_piece = 'autre'

    PieceJointe.objects.create(
        type_entite=type_entite,
        entite_id=int(entite_id),
        type_piece=type_piece,
        fichier=fichier,
        nom_original=fichier.name,
        taille=fichier.size,
        uploaded_by=request.user,
    )
    log_action(request.user, 'PJ.upload',
               f"Upload pièce jointe « {fichier.name} » sur {type_entite.upper()} #{entite_id}",
               type_entite, int(entite_id))
    messages.success(request, f"Fichier « {fichier.name} » joint avec succès.")
    return redirect(redirect_url)


@login_required
@require_POST
def piece_jointe_delete(request, pk):
    """Suppression d'une pièce jointe (auteur ou admin uniquement)."""
    pj = get_object_or_404(PieceJointe, pk=pk)
    redirect_url = {'da': 'da_list', 'bc': 'bc_list'}.get(pj.type_entite, 'da_list')

    if pj.uploaded_by != request.user and request.user.role != 'admin':
        messages.error(request, "Vous n'êtes pas autorisé à supprimer cette pièce jointe.")
        return redirect(redirect_url)

    nom = pj.nom_original
    pj.fichier.delete(save=False)   # supprime le fichier physique
    pj.delete()
    log_action(request.user, 'PJ.delete',
               f"Suppression pièce jointe « {nom} »", pj.type_entite, pj.entite_id)
    messages.success(request, f"Pièce jointe « {nom} » supprimée.")
    return redirect(redirect_url)


# ============ RECHERCHE GLOBALE ============

@login_required
def recherche_view(request):
    """Recherche globale multi-modules."""
    q = request.GET.get('q', '').strip()
    resultats = {}

    if len(q) >= 2:
        resultats = {
            'taches': Tache.objects.filter(
                Q(numero__icontains=q) | Q(titre__icontains=q) | Q(libelle_nature__icontains=q)
            ).order_by('numero')[:8],
            'bcs': BonCommande.objects.select_related('tache', 'prestataire').filter(
                Q(numero__icontains=q) | Q(prestataire__nom__icontains=q) | Q(tache__titre__icontains=q)
            ).order_by('-created_at')[:8],
            'das': DemandeAchat.objects.select_related('tache', 'created_by').filter(
                Q(reference__icontains=q) | Q(objet__icontains=q)
            ).order_by('-created_at')[:8],
            'prestataires': Prestataire.objects.filter(
                Q(nom__icontains=q) | Q(code__icontains=q) | Q(email__icontains=q)
            ).order_by('nom')[:8],
            'virements': VirementBudgetaire.objects.select_related('tache_source', 'tache_dest').filter(
                Q(tache_source__numero__icontains=q) | Q(tache_dest__numero__icontains=q)
                | Q(motif__icontains=q)
            ).order_by('-created_at')[:6],
        }
        total = sum(qs.count() for qs in resultats.values())
    else:
        total = 0

    return render(request, 'core/recherche.html', {
        'q': q,
        'resultats': resultats,
        'total': total,
        'trop_court': len(q) == 1,
    })


# ============ JOURNAL ============

@login_required
def journal_view(request):
    base_qs = JournalActivite.objects.select_related('utilisateur').all()
    f = JournalFilter(request.GET, queryset=base_qs)
    page_obj, querystring = _paginate(request, f.qs, page_size=50)
    return render(request, 'core/journal.html', {
        'entries': page_obj.object_list,
        'page_obj': page_obj,
        'querystring': querystring,
        'filter': f,
    })


# ============ UTILISATEURS ============

@login_required
@role_required('admin')
def utilisateurs_list(request):
    page_obj, querystring = _paginate(request, Utilisateur.objects.all().order_by('role', 'nom_complet'))
    # Récupère le mot de passe temporaire généré lors du reset (une seule fois)
    reset_pwd_info = request.session.pop('reset_pwd_info', None)
    return render(request, 'core/utilisateurs.html', {
        'users': page_obj.object_list,
        'page_obj': page_obj,
        'querystring': querystring,
        'role_choices': Utilisateur.ROLE_CHOICES,
        'reset_pwd_info': reset_pwd_info,
    })


@login_required
@role_required('admin')
@require_POST
def utilisateur_create(request):
    username   = request.POST.get('username', '').strip()
    nom_complet = request.POST.get('nom_complet', '').strip()
    email      = request.POST.get('email', '').strip()
    role       = request.POST.get('role', 'lecteur')
    password   = request.POST.get('password', '').strip()
    if not username or not password:
        messages.error(request, "Nom d'utilisateur et mot de passe obligatoires.")
        return redirect('utilisateurs_list')
    if len(password) < 6:
        messages.error(request, "Le mot de passe doit contenir au moins 6 caractères.")
        return redirect('utilisateurs_list')
    if Utilisateur.objects.filter(username=username).exists():
        messages.error(request, f"Le nom d'utilisateur « {username} » existe déjà.")
        return redirect('utilisateurs_list')
    u = Utilisateur.objects.create_user(
        username=username, email=email, password=password,
        nom_complet=nom_complet, role=role, must_change_password=True,
    )
    log_action(request.user, 'User.create', f"Création de l'utilisateur {u.username} (rôle : {u.role})", 'user', u.pk)
    messages.success(request, f"Utilisateur « {u.username} » créé. Il devra changer son mot de passe à la première connexion.")
    return redirect('utilisateurs_list')


@login_required
@role_required('admin')
@require_POST
def utilisateur_edit(request, pk):
    u = get_object_or_404(Utilisateur, pk=pk)
    u.nom_complet = request.POST.get('nom_complet', u.nom_complet).strip()
    u.email       = request.POST.get('email', u.email).strip()
    u.role        = request.POST.get('role', u.role)
    u.save()
    log_action(request.user, 'User.edit', f"Modification de {u.username} (rôle : {u.role})", 'user', u.pk)
    messages.success(request, f"Utilisateur « {u.username} » mis à jour.")
    return redirect('utilisateurs_list')


@login_required
@role_required('admin')
@require_POST
def utilisateur_reset_pwd(request, pk):
    u = get_object_or_404(Utilisateur, pk=pk)
    import secrets, string
    alphabet = string.ascii_letters + string.digits + "!@#$"
    new_pwd = ''.join(secrets.choice(alphabet) for _ in range(12))
    u.set_password(new_pwd)
    u.must_change_password = True
    u.save()
    log_action(request.user, 'User.reset_pwd', f"Réinitialisation du mot de passe de {u.username}", 'user', u.pk)
    # Stocke le mot de passe en session (affiché une seule fois, sans passer par les messages)
    request.session['reset_pwd_info'] = {'username': u.username, 'password': new_pwd}
    return redirect('utilisateurs_list')


@login_required
@role_required('admin')
@require_POST
def utilisateur_toggle_actif(request, pk):
    u = get_object_or_404(Utilisateur, pk=pk)
    if u.pk == request.user.pk:
        messages.error(request, "Vous ne pouvez pas désactiver votre propre compte.")
        return redirect('utilisateurs_list')
    u.is_active = not u.is_active
    u.save()
    etat = "activé" if u.is_active else "désactivé"
    log_action(request.user, 'User.toggle_actif', f"Compte {u.username} {etat}", 'user', u.pk)
    messages.success(request, f"Compte « {u.username} » {etat}.")
    return redirect('utilisateurs_list')


@login_required
@role_required('admin')
@require_POST
def utilisateur_delete(request, pk):
    u = get_object_or_404(Utilisateur, pk=pk)
    if u.pk == request.user.pk:
        messages.error(request, "Vous ne pouvez pas supprimer votre propre compte.")
        return redirect('utilisateurs_list')
    username = u.username
    u.delete()
    log_action(request.user, 'User.delete', f"Suppression de l'utilisateur {username}", 'user')
    messages.success(request, f"Utilisateur « {username} » supprimé.")
    return redirect('utilisateurs_list')


# ============ RGPD ============

@login_required
def rgpd_export_view(request):
    """
    Export RGPD : renvoie toutes les donnees de l'utilisateur courant au
    format JSON (article 20 du RGPD - droit a la portabilite).
    """
    import json
    from django.http import HttpResponse

    user = request.user
    data = {
        'utilisateur': {
            'username': user.username,
            'email': user.email,
            'nom_complet': user.nom_complet,
            'role': user.role,
            'date_joined': user.date_joined.isoformat(),
            'last_login': user.last_login.isoformat() if user.last_login else None,
        },
        'demandes_achat_creees': [
            {
                'reference': d.reference,
                'objet': d.objet,
                'montant_estime': float(d.montant_estime),
                'statut': d.statut,
                'created_at': d.created_at.isoformat(),
                'tache_numero': d.tache.numero,
            }
            for d in DemandeAchat.objects.filter(created_by=user).select_related('tache')
        ],
        'virements_crees': [
            {
                'tache_source': v.tache_source.numero,
                'tache_dest': v.tache_dest.numero,
                'montant': float(v.montant),
                'motif': v.motif,
                'created_at': v.created_at.isoformat(),
            }
            for v in VirementBudgetaire.objects.filter(created_by=user).select_related('tache_source', 'tache_dest')
        ],
        'journal_actions': [
            {
                'type_action': j.type_action,
                'description': j.description,
                'entite_type': j.entite_type,
                'entite_id': j.entite_id,
                'created_at': j.created_at.isoformat(),
                'hash_chain': j.hash_chain,
            }
            for j in JournalActivite.objects.filter(utilisateur=user)
        ],
        'notifications': [
            {
                'type': n.type,
                'titre': n.titre,
                'message': n.message,
                'lu': n.lu,
                'created_at': n.created_at.isoformat(),
            }
            for n in Notification.objects.filter(utilisateur=user)
        ],
        '_meta': {
            'export_date': timezone.now().isoformat(),
            'export_version': '1.0',
            'note': "Export RGPD - article 20 (droit a la portabilite).",
        },
    }
    app_logger.info("Export RGPD pour user=%s", user.username)
    response = HttpResponse(
        json.dumps(data, indent=2, ensure_ascii=False),
        content_type='application/json; charset=utf-8',
    )
    response['Content-Disposition'] = (
        f'attachment; filename="budgetpad_export_{user.username}_{timezone.now().date()}.json"'
    )
    return response


# ============ EXERCICE ============

@login_required
def exercices_list(request):
    exercices = ExerciceBudgetaire.objects.order_by('-annee')
    stats = {}
    for ex in exercices:
        taches = ex.taches.all()
        budget = sum(t.budget_ajuste for t in taches)
        conso = sum(t.consommation for t in taches)
        stats[ex.pk] = {
            'budget': budget,
            'conso': conso,
            'taux': round(float(conso) / float(budget) * 100, 1) if budget else 0,
            'nb_taches': taches.count(),
            'nb_bc': BonCommande.objects.filter(tache__exercice=ex).count(),
        }
    return render(request, 'core/exercices_list.html', {
        'exercices': exercices,
        'stats': stats,
    })


@login_required
@role_required('admin')
@require_POST
def exercice_create(request):
    from datetime import date as date_type
    annee_raw   = request.POST.get('annee', '').strip()
    date_debut  = request.POST.get('date_debut', '').strip()
    date_fin    = request.POST.get('date_fin', '').strip()
    montant_raw = request.POST.get('montant_global', '').strip()
    try:
        annee   = int(annee_raw)
        montant = Decimal(montant_raw)
        if not (2000 <= annee <= 2099):
            messages.error(request, "L'année doit être comprise entre 2000 et 2099.")
            return redirect('exercices_list')
        if montant <= 0:
            messages.error(request, "Le montant global doit être supérieur à zéro.")
            return redirect('exercices_list')
        if ExerciceBudgetaire.objects.filter(annee=annee).exists():
            messages.error(request, f"Un exercice {annee} existe déjà.")
            return redirect('exercices_list')
        # Validation des dates
        from datetime import datetime
        try:
            d_debut = datetime.strptime(date_debut, '%Y-%m-%d').date()
            d_fin   = datetime.strptime(date_fin,   '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Format de date invalide. Utilisez le format JJ/MM/AAAA.")
            return redirect('exercices_list')
        if d_fin <= d_debut:
            messages.error(request, "La date de fin doit être postérieure à la date de début.")
            return redirect('exercices_list')
        if d_debut.year != annee or d_fin.year != annee:
            messages.error(request, f"Les dates doivent appartenir à l'année {annee}.")
            return redirect('exercices_list')
        ExerciceBudgetaire.objects.create(
            annee=annee,
            date_debut=d_debut,
            date_fin=d_fin,
            montant_global=montant,
            statut='actif',
        )
        log_action(request.user, 'Exercice.create', f"Création de l'exercice {annee}", 'exercice')
        messages.success(request, f"Exercice {annee} créé avec succès.")
    except (ValueError, TypeError):
        messages.error(request, "Données invalides. Vérifiez l'année et le montant.")
    return redirect('exercices_list')


@login_required
@role_required('admin')
@require_POST
def exercice_cloturer(request, pk):
    ex = get_object_or_404(ExerciceBudgetaire, pk=pk)
    if ex.statut == 'cloture':
        messages.warning(request, f"L'exercice {ex.annee} est déjà clôturé.")
        return redirect('exercices_list')
    ex.statut = 'cloture'
    ex.save()
    log_action(request.user, 'Exercice.cloturer', f"Clôture de l'exercice {ex.annee}", 'exercice', ex.pk)
    messages.success(request, f"Exercice {ex.annee} clôturé.")
    return redirect('exercices_list')


# ============ EXERCICE SWITCH ============

@login_required
@require_POST
def exercice_switch(request):
    """Change l'exercice consulte (stocke en session)."""
    annee_raw = request.POST.get('annee', '').strip()
    if annee_raw == 'actif':
        request.session.pop('exercice_annee', None)
        messages.info(request, "Exercice : retour à l'exercice actif.")
    else:
        try:
            annee = int(annee_raw)
            ex = ExerciceBudgetaire.objects.filter(annee=annee).first()
            if not ex:
                messages.error(request, "Exercice introuvable.")
            else:
                request.session['exercice_annee'] = annee
                messages.info(request, f"Exercice {annee} sélectionné.")
        except (TypeError, ValueError):
            messages.error(request, "Année invalide.")
    return _safe_referer_redirect(request, fallback='dashboard')


# ============ NOTIFICATIONS ============

@login_required
@require_POST
def notifications_marquer_lues(request):
    """Marque toutes les notifications de l'utilisateur courant comme lues."""
    nb = NotificationService.marquer_lues(request.user)
    messages.success(request, f"{nb} notification(s) marquée(s) comme lues.")
    return _safe_referer_redirect(request, fallback='dashboard')


# ============ PARAMETRES ============

@login_required
@role_required('admin')
def parametres_view(request):
    if request.method == 'POST' and 'reset_seed' in request.POST:
        from django.conf import settings
        if not settings.DEBUG:
            messages.error(
                request,
                "La réinitialisation des données de démonstration est interdite en production."
            )
            return redirect('parametres')
        from django.core.management import call_command
        call_command('seed_data')
        messages.success(request, "Données de démonstration réinitialisées.")
        return redirect('parametres')
    return render(request, 'core/parametres.html')
