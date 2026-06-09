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
from django.db.models import Count, Q, Sum, Max
from django.http import HttpResponse
from django.utils import timezone
from django.utils.http import urlencode, url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST, require_http_methods
from functools import wraps
from decimal import Decimal
from .models import (
    Utilisateur, ExerciceBudgetaire, Tache, LigneBudgetaire,
    VirementBudgetaire, Prestataire, DemandeAchat, Offre, BonCommande,
    LigneBC, ImputationBC, ProlongationBC, JournalActivite, Notification,
    Alerte, HistoriqueStatut, PieceJointe, ConsommationDirecte,
    RepertoireTache, RepertoireLigne, LogAnnulation, PrestationProgrammee,
)
from .forms import (
    VirementForm, PrestataireForm, TacheForm, LigneBudgetaireForm,
    DemandeAchatForm, DemandeAchatEditForm, BonCommandeForm, BonCommandeEditForm,
    ProlongationBCForm, OffreSolliciterForm, OffreSaisirForm, OffreRefuserForm,
    ConsommationDirecteForm, LigneBCFormSet,
)
from django.http import JsonResponse
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

def _check_exercice_non_verrouille(exercice, redirect_url='dashboard'):
    """Retourne un redirect d'erreur si l'exercice est verrouillé, sinon None."""
    if exercice and exercice.is_locked:
        return (True, f"L'exercice {exercice.annee} est clôturé et en lecture seule.")
    return (False, None)


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
            next_url = request.POST.get('next', request.GET.get('next', '')).strip()
            if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
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
    """
    Filtre un queryset de BC selon le paramètre GET 'periode'.
    Utilise date_emission (date métier) plutôt que created_at (date SQL).
    """
    from datetime import date as _date, timedelta as _td
    periode = request.GET.get('periode', 'annuel')
    today = _date.today()

    if periode == 'mensuel':
        start = _date(today.year, today.month, 1)
        if today.month == 12:
            end = _date(today.year, 12, 31)
        else:
            end = _date(today.year, today.month + 1, 1) - _td(days=1)
        bcs_qs = bcs_qs.filter(date_emission__gte=start, date_emission__lte=end)
    elif periode == 'trimestriel':
        quarter = ((today.month - 1) // 3) + 1
        start_month = (quarter - 1) * 3 + 1
        start = _date(today.year, start_month, 1)
        if quarter == 4:
            end = _date(today.year, 12, 31)
        else:
            end = _date(today.year, quarter * 3 + 1, 1) - _td(days=1)
        bcs_qs = bcs_qs.filter(date_emission__gte=start, date_emission__lte=end)
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
    total_bc = bcs.exclude(statut='annule').aggregate(t=Sum('montant_ttc'))['t'] or 0
    # COHE-3 : inclure les consommations directes non annulées dans le total engagé
    total_conso_directe = (
        ConsommationDirecte.objects
        .filter(ligne_budgetaire__tache__exercice=exercice, est_annule=False)
        .aggregate(t=Sum('montant'))['t']
        or 0
    )
    total_engage = total_bc + total_conso_directe
    solde = budget_total - total_engage
    taux_global = round((float(total_engage) / float(budget_total)) * 100, 1) if budget_total > 0 else 0
    taux_disponible = round(100 - taux_global, 1)

    taches_top = sorted(taches, key=lambda t: float(t.taux_consommation), reverse=True)[:5]
    top_labels = [t.numero for t in taches_top]
    top_data = [float(t.taux_consommation) for t in taches_top]
    top_colors = ['#E74C3C' if d >= 90 else '#F39C12' if d >= 70 else '#1A5632' for d in top_data]

    derniers_bc = bcs.select_related('tache', 'prestataire').order_by('-created_at')[:5]
    alertes = Alerte.objects.filter(lu=False).order_by('-created_at')[:5]

    from datetime import date as _date, timedelta as _td
    _today = _date.today()
    _bcs_actifs_echeance = bcs_base.exclude(statut__in=['annule', 'execute']).filter(date_echeance__isnull=False).select_related('tache', 'prestataire')
    bc_en_retard = list(_bcs_actifs_echeance.filter(date_echeance__lt=_today)[:5])
    bc_echeance_proche = list(_bcs_actifs_echeance.filter(date_echeance__gte=_today, date_echeance__lte=_today + _td(days=7))[:5])

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
        'bc_en_retard': bc_en_retard,
        'bc_echeance_proche': bc_echeance_proche,
    }
    return render(request, 'core/dashboard.html', context)


# ============ TACHES ============

@login_required
def taches_list(request):
    from django.db.models import Prefetch
    exercice = _exercice_courant(request)
    if exercice:
        lignes_annotees = LigneBudgetaire.objects.with_aggregates()
        taches = list(
            Tache.objects.filter(exercice=exercice)
            .with_aggregates()
            .prefetch_related(Prefetch('lignes', queryset=lignes_annotees))
        )
        # Détecter si l'exercice a au moins UN virement (sur n'importe quelle tâche)
        # afin de masquer entièrement la colonne "Ajusté" sinon (UX épuré).
        has_any_transfer = any(
            (t.total_transfert_plus or 0) > 0 or (t.total_transfert_moins or 0) > 0
            for t in taches
        )
    else:
        taches = []
        has_any_transfer = False
    return render(request, 'core/taches_list.html', {
        'exercice': exercice,
        'taches': taches,
        'has_any_transfer': has_any_transfer,
    })

@login_required
def tache_detail(request, pk):
    tache = get_object_or_404(Tache.objects.with_aggregates(), pk=pk)
    bcs = tache.bons_commande.select_related('prestataire').order_by('-created_at')
    return render(request, 'partials/_tache_detail.html', {'tache': tache, 'bcs': bcs})


@login_required
@role_required('admin', 'assistante_drh')
@require_POST
@transaction.atomic
def tache_create(request):
    """Crée une tâche + ses lignes budgétaires (formulaire multi-lignes)."""
    exercice = ExerciceBudgetaire.get_actif()
    if exercice is None:
        messages.error(request, "Aucun exercice budgétaire actif.")
        return redirect('taches_list')
    locked, msg = _check_exercice_non_verrouille(exercice)
    if locked:
        messages.error(request, msg)
        return redirect('taches_list')

    numero = request.POST.get('numero', '').strip()
    titre = request.POST.get('titre', '').strip()
    if not numero or not titre:
        messages.error(request, "Numéro et titre obligatoires.")
        return redirect('taches_list')

    # Unicité (exercice, numero)
    if Tache.objects.filter(exercice=exercice, numero=numero).exists():
        messages.error(request, f"La tâche {numero} existe déjà pour l'exercice {exercice.annee}.")
        return redirect('taches_list')

    tache = Tache.objects.create(
        exercice=exercice, numero=numero, titre=titre, actif=True,
    )

    # Lignes budgétaires inline (POST arrays : ligne_code_0, ligne_libelle_0, ligne_montant_0, ...)
    from decimal import Decimal as _D
    nb_lignes = 0
    idx = 0
    while True:
        code = request.POST.get(f'ligne_code_{idx}', '').strip()
        libelle = request.POST.get(f'ligne_libelle_{idx}', '').strip()
        montant_raw = request.POST.get(f'ligne_montant_{idx}', '').strip()
        if not code and not libelle and not montant_raw:
            # Stop dès qu'on a une ligne entièrement vide après les premières
            if idx >= 3:
                break
            idx += 1
            continue
        if code and libelle:
            try:
                montant = _D(montant_raw or '0')
                if montant < 0:
                    raise ValueError
                LigneBudgetaire.objects.create(
                    tache=tache, code_nature=code, libelle_nature=libelle,
                    montant_initial=montant, actif=True,
                )
                nb_lignes += 1
            except Exception:
                pass
        idx += 1
        if idx > 100:  # garde-fou
            break

    log_action(
        request.user, 'Tache.create',
        f"Création de la tâche {tache.numero} — {tache.titre} ({nb_lignes} lignes)",
        'tache', tache.id,
    )
    messages.success(
        request,
        f"Tâche {tache.numero} créée avec {nb_lignes} ligne(s) budgétaire(s)."
    )
    return redirect('taches_list')

@login_required
@role_required('admin', 'assistante_drh')
@require_POST
def tache_delete(request, pk):
    tache = get_object_or_404(Tache, pk=pk)
    lignes = list(tache.lignes.all())
    has_virements = any(
        l.virements_sortants.exists() or l.virements_entrants.exists()
        for l in lignes
    )
    # MED-4 : bloquer aussi si consommations directes non annulées
    has_conso_directes = any(
        l.consommations_directes.filter(est_annule=False).exists()
        for l in lignes
    )
    has_linked = (
        tache.bons_commande.exists()
        or tache.demandes_achat.exists()
        or has_virements
        or has_conso_directes
    )
    if has_linked:
        messages.error(
            request,
            "Impossible de supprimer une tâche avec des BC, DA, virements "
            "ou consommations directes associés."
        )
    else:
        log_action(request.user, 'Tache.delete', f"Suppression de la tâche {tache.numero} — {tache.titre}", 'tache', tache.id)
        tache.delete()
        messages.success(request, "Tâche supprimée.")
    return redirect('taches_list')


# ============ TRANSFERTS ============

@login_required
def virements_list(request):
    exercice = _exercice_courant(request)
    qs = VirementBudgetaire.objects.select_related(
        'ligne_source', 'ligne_destination',
        'ligne_source__tache', 'ligne_destination__tache',
        'created_by',
    ).all()
    if exercice:
        qs = qs.filter(exercice=exercice)
    page_obj, querystring = _paginate(request, qs)
    lignes = (
        LigneBudgetaire.objects.filter(tache__exercice=exercice, actif=True)
        .select_related('tache').order_by('tache__numero', 'code_nature')
        if exercice else []
    )
    return render(request, 'core/virements_list.html', {
        'virements': page_obj.object_list,
        'page_obj': page_obj,
        'querystring': querystring,
        'lignes': lignes,
        'exercice': exercice,
    })

@login_required
@role_required('admin', 'directeur_drh')
@require_POST
def virement_create(request):
    exercice = ExerciceBudgetaire.get_actif()
    if exercice is None:
        messages.error(request, "Aucun exercice budgétaire actif. Activez ou créez un exercice avant de saisir un virement.")
        return redirect('virements_list')
    locked, msg = _check_exercice_non_verrouille(exercice)
    if locked:
        messages.error(request, msg)
        return redirect('virements_list')
    form = VirementForm(request.POST, exercice=exercice)
    if form.is_valid():
        try:
            virement = VirementService.creer_virement(
                ligne_source=form.cleaned_data['ligne_source'],
                ligne_destination=form.cleaned_data['ligne_destination'],
                montant=form.cleaned_data['montant'],
                motif=form.cleaned_data['motif'],
                utilisateur=request.user,
                exercice=exercice,
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
        VirementBudgetaire.objects.select_related(
            'ligne_source', 'ligne_destination',
            'ligne_source__tache', 'ligne_destination__tache',
            'created_by',
        ),
        pk=pk,
    )
    # Recharger les lignes avec leurs agrégats (transfert_plus/moins/budget_ajuste/conso/solde)
    src = LigneBudgetaire.objects.with_aggregates().select_related('tache').get(pk=v.ligne_source_id)
    dst = LigneBudgetaire.objects.with_aggregates().select_related('tache').get(pk=v.ligne_destination_id)
    # Source : transfert_moins inclut ce virement -> solde actuel = solde "après"
    src_solde_apres = src.solde
    src_solde_avant = src_solde_apres + v.montant
    # Destination : transfert_plus inclut ce virement -> solde actuel = solde "après"
    dst_solde_apres = dst.solde
    dst_solde_avant = dst_solde_apres - v.montant
    return render(request, 'partials/_virement_detail.html', {
        'v': v,
        'src': src, 'dst': dst,
        'src_solde_avant': src_solde_avant, 'src_solde_apres': src_solde_apres,
        'dst_solde_avant': dst_solde_avant, 'dst_solde_apres': dst_solde_apres,
    })


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
@role_required('admin', 'assistante_drh')
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
@role_required('admin', 'assistante_drh')
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
    base_qs = DemandeAchat.objects.select_related(
        'ligne_budgetaire__tache', 'created_by',
    )
    if exercice:
        base_qs = base_qs.filter(exercice=exercice)
    f = DemandeAchatFilter(request.GET, queryset=base_qs)
    page_obj, querystring = _paginate(request, f.qs)
    # Lignes actives de l'exercice pour le modal de création
    lignes = (
        LigneBudgetaire.objects
        .filter(tache__exercice=exercice, actif=True)
        .select_related('tache')
        .order_by('tache__numero', 'code_nature')
        if exercice else []
    )
    return render(request, 'core/da_list.html', {
        'demandes': page_obj.object_list,
        'page_obj': page_obj,
        'querystring': querystring,
        'filter': f,
        'lignes': lignes,
        'exercice': exercice,
    })

@login_required
@role_required('admin', 'directeur_drh', 'chef_service', 'assistante_drh')
@require_POST
def da_create(request):
    exercice = ExerciceBudgetaire.get_actif()
    locked, msg = _check_exercice_non_verrouille(exercice)
    if locked:
        messages.error(request, msg)
        return redirect('da_list')
    form = DemandeAchatForm(request.POST, exercice=exercice)
    if form.is_valid():
        try:
            da = DemandeAchatService.creer(
                ligne_budgetaire=form.cleaned_data['ligne_budgetaire'],
                objet=form.cleaned_data['objet'],
                montant_estime=form.cleaned_data['montant_estime'],
                reference=form.cleaned_data.get('reference', ''),
                nature_prestation=form.cleaned_data.get('nature_prestation', ''),
                periode_engagement=form.cleaned_data.get('periode_engagement', ''),
                priorite=form.cleaned_data.get('priorite', ''),
                utilisateur=request.user,
                exercice=exercice,
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
@role_required('directeur_drh')
@require_POST
@transaction.atomic
def da_en_etude(request, pk):
    """Passe une DA de « créée » à « en étude » (instruction Directeur DRH)."""
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
    log_action(request.user, 'DA.en_etude', f"Transmission à la DAG de {da.reference}", 'da', da.id)
    app_logger.info("DA transmise à la DAG : %s par %s", da.reference, request.user.username)
    messages.info(request, f"{da.reference} transmise à la DAG.")
    return redirect('da_list')


@login_required
@role_required('directeur_drh')
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
            message=f"Votre demande « {da.objet} » a été validée par le Directeur DRH.",
            entite_type='da', entite_id=da.id,
        )
    app_logger.info("DA validée : %s par %s", da.reference, request.user.username)
    messages.success(request, f"{da.reference} validée.")
    return redirect('da_list')


@login_required
@role_required('directeur_drh')
@require_POST
@transaction.atomic
def da_refuser(request, pk):
    """Annule une DA (motif obligatoire). Au PAD, une DA s'annule, elle ne se « refuse » pas."""
    da = get_object_or_404(DemandeAchat, pk=pk)
    motif = request.POST.get('motif', '').strip()
    if not motif:
        messages.error(request, "Motif d'annulation obligatoire.")
        return redirect('da_list')
    # Pré-remplir le champ pour que peut_transiter_vers() puisse le vérifier
    da.motif_refus = motif
    peut, msg = da.peut_transiter_vers('annulee')
    if not peut:
        messages.error(request, msg)
        return redirect('da_list')
    ancien = da.statut
    da.statut = 'annulee'
    da.save(update_fields=['statut', 'motif_refus'])
    HistoriqueStatut.objects.create(
        type_entite='DA', entite_id=da.id,
        ancien_statut=ancien, nouveau_statut='annulee',
        utilisateur=request.user, commentaire=motif,
    )
    log_action(request.user, 'DA.annuler', f"Annulation de {da.reference} : {motif}", 'da', da.id)
    if da.created_by_id and da.created_by_id != request.user.id:
        NotificationService.notifier(
            utilisateur=da.created_by,
            type_notif='da_annulee',
            titre=f"{da.reference} annulée",
            message=f"Votre demande a été annulée. Motif : {motif}",
            entite_type='da', entite_id=da.id,
        )
    app_logger.info("DA annulée : %s par %s (motif=%s)", da.reference, request.user.username, motif)
    messages.warning(request, f"{da.reference} annulée.")
    return redirect('da_list')


@login_required
def da_detail(request, pk):
    da = get_object_or_404(
        DemandeAchat.objects.select_related('ligne_budgetaire__tache', 'created_by')
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
    # BC lié (si la DA est passée à bc_cree)
    bc_lie = None
    if da.statut == 'bc_cree':
        bc_lie = (
            BonCommande.objects.filter(demande=da)
            .select_related('prestataire').order_by('-created_at').first()
        )
    return render(request, 'partials/_da_detail.html', {
        'da': da,
        'offres': offres,
        'nb_contactes': nb_contactes,
        'nb_recues': nb_recues,
        'nb_en_retard': nb_en_retard,
        'form_solliciter': form_solliciter,
        'can_manage': request.user.role in ('admin', 'directeur_drh'),
        'pieces_jointes': pieces_jointes,
        'bc_lie': bc_lie,
    })


@login_required
@role_required('admin', 'directeur_drh', 'assistante_drh', 'chef_service')
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
@role_required('admin', 'directeur_drh', 'assistante_drh', 'chef_service')
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
@role_required('admin', 'directeur_drh', 'assistante_drh')
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
@role_required('admin', 'directeur_drh', 'assistante_drh')
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
        .select_related('ligne_budgetaire__tache')
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
@role_required('directeur_drh')
@require_http_methods(['GET', 'POST'])
def bc_create(request):
    """
    Crée un BC au format réel PAD depuis une DA validée :
    n° manuel/auto, objet, condition/RIB, délai en semaines et tableau d'articles
    (Réf. Art saisie manuelle). L'imputation budgétaire porte sur la ligne de la DA.
    """
    exercice_actif = ExerciceBudgetaire.get_actif()
    locked, msg = _check_exercice_non_verrouille(exercice_actif)
    if locked:
        messages.error(request, msg)
        return redirect('bc_list')

    # DAs validées disposant d'une offre retenue
    das = (
        DemandeAchat.objects
        .filter(statut='validee', exercice=exercice_actif)
        .select_related('ligne_budgetaire__tache')
        .prefetch_related('offres__prestataire')
        if exercice_actif else DemandeAchat.objects.none()
    )
    das_validees = [d for d in das if d.offres.filter(statut='retenue').exists()]

    def _offre(da_obj):
        return da_obj.offres.filter(statut='retenue').select_related('prestataire').first()

    da_id = (request.GET.get('da') or request.POST.get('da_id') or '').strip()
    da = next((d for d in das_validees if str(d.pk) == da_id), None) if da_id else None

    if request.method == 'POST':
        formset = LigneBCFormSet(request.POST, prefix='lignes')
        if not da:
            messages.error(request, "Sélectionnez une demande d'achat validée.")
        elif not da.ligne_budgetaire_id:
            messages.error(request, "Cette DA n'a pas de ligne budgétaire assignée.")
        else:
            offre = _offre(da)
            peut, m = da.peut_transiter_vers('bc_cree')
            if not offre or not offre.montant or offre.montant <= 0:
                messages.error(request, f"Aucune offre retenue valide pour {da.reference}.")
            elif not peut:
                messages.error(request, m)
            elif not formset.is_valid():
                messages.error(request, "Vérifiez les lignes d'articles saisies.")
            else:
                # Construit la liste des articles non supprimés
                lignes = []
                for cd in formset.cleaned_data:
                    if not cd or cd.get('DELETE'):
                        continue
                    designation = (cd.get('designation') or '').strip()
                    qte = cd.get('quantite')
                    pu = cd.get('prix_unitaire_ht')
                    if not designation or qte is None or pu is None:
                        continue
                    lignes.append({
                        'reference_article': (cd.get('reference_article') or '').strip(),
                        'designation': designation,
                        'unite': cd.get('unite') or 'UN',
                        'quantite': qte,
                        'prix_unitaire_ht': pu,
                    })
                # Montant HT : somme des articles, sinon montant de l'offre retenue
                if lignes:
                    montant_ht = sum(
                        Decimal(str(l['quantite'])) * Decimal(str(l['prix_unitaire_ht']))
                        for l in lignes
                    )
                else:
                    montant_ht = offre.montant

                # Délai (semaines) + date de notification optionnels
                valide = True
                semaines = None
                raw_sem = request.POST.get('delai_execution_semaines', '').strip()
                if raw_sem:
                    try:
                        semaines = int(raw_sem)
                        if not (1 <= semaines <= 52):
                            raise ValueError
                    except ValueError:
                        messages.error(request, "Le délai en semaines doit être entre 1 et 52.")
                        valide = False
                date_notif = None
                raw_notif = request.POST.get('date_notification', '').strip()
                if valide and raw_notif:
                    from datetime import datetime as _dt
                    try:
                        date_notif = _dt.strptime(raw_notif, '%Y-%m-%d').date()
                    except ValueError:
                        messages.error(request, "Date de notification invalide.")
                        valide = False

                # Avis CAPRI obligatoire (Règle R11)
                numero_capri = request.POST.get('numero_capri', '').strip()
                raw_capri = request.POST.get('date_capri', '').strip()
                date_capri = None
                if valide:
                    if not numero_capri or not raw_capri:
                        messages.error(request, "Avis CAPRI obligatoire : numéro et date (Règle R11).")
                        valide = False
                    else:
                        from datetime import datetime as _dt
                        try:
                            date_capri = _dt.strptime(raw_capri, '%Y-%m-%d').date()
                        except ValueError:
                            messages.error(request, "Date CAPRI invalide.")
                            valide = False

                if valide:
                    try:
                        bc = BonCommandeService.creer(
                            tache=da.ligne_budgetaire.tache,
                            prestataire=offre.prestataire,
                            montant_ht=montant_ht,
                            utilisateur=request.user,
                            demande=da,
                            ligne_imputation=da.ligne_budgetaire,
                            numero=request.POST.get('numero', '').strip(),
                            objet=(request.POST.get('objet', '').strip() or da.objet),
                            numero_capri=numero_capri,
                            date_capri=date_capri,
                            condition_paiement=request.POST.get('condition_paiement', 'virement_60'),
                            rib_paiement=request.POST.get('rib_paiement', '').strip(),
                            delai_execution_semaines=semaines,
                            date_notification=date_notif,
                            lignes=lignes,
                        )
                        TacheService.verifier_alertes(bc.tache)
                        app_logger.info("BC %s créé depuis DA %s par %s",
                                        bc.numero, da.reference, request.user.username)
                        messages.success(request, f"Bon de commande {bc.numero} créé (DA : {da.reference}).")
                        return redirect('bc_list')
                    except ValueError as e:
                        messages.error(request, str(e))
    else:
        # GET : préremplir une ligne d'article depuis l'offre retenue
        initial = []
        if da:
            offre = _offre(da)
            if offre:
                initial = [{
                    'designation': da.objet,
                    'unite': 'UN',
                    'quantite': 1,
                    'prix_unitaire_ht': offre.montant,
                }]
        formset = LigneBCFormSet(prefix='lignes', initial=initial)

    return render(request, 'core/bc_create.html', {
        'das_validees': das_validees,
        'da': da,
        'formset': formset,
        'exercice': exercice_actif,
        'condition_choices': BonCommande._meta.get_field('condition_paiement').choices,
    })

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
@role_required('directeur_drh')
@require_POST
def bc_change_statut(request, pk, nouveau_statut):
    # Validation de la liste blanche avant toute logique métier
    _STATUTS_VALIDES = {'notifie', 'en_cours', 'execute', 'annule'}
    if nouveau_statut not in _STATUTS_VALIDES:
        messages.error(request, "Statut invalide.")
        return redirect('bc_list')

    bc = get_object_or_404(BonCommande, pk=pk)
    motif = request.POST.get('motif', '').strip()

    # Motif obligatoire pour annulation
    if nouveau_statut == 'annule' and not motif:
        messages.error(request, "Motif d'annulation obligatoire.")
        return redirect('bc_list')

    # Paramètres spécifiques à la notification
    date_notif = None
    delai_jours = None
    if nouveau_statut == 'notifie':
        from datetime import datetime as _dt
        raw_date = request.POST.get('date_notification', '').strip()
        raw_delai = request.POST.get('delai_execution_jours', '').strip()
        if raw_date:
            try:
                date_notif = _dt.strptime(raw_date, '%Y-%m-%d').date()
            except ValueError:
                messages.error(request, "Format de date de notification invalide.")
                return redirect('bc_list')
        if raw_delai:
            try:
                delai_jours = int(raw_delai)
                if not (1 <= delai_jours <= 365):
                    messages.error(request, "Le délai doit être entre 1 et 365 jours.")
                    return redirect('bc_list')
            except ValueError:
                messages.error(request, "Délai d'exécution invalide.")
                return redirect('bc_list')

    try:
        result = BonCommandeService.changer_statut(
            bc, nouveau_statut, request.user, motif=motif,
            date_notification=date_notif, delai_jours=delai_jours,
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
                           .prefetch_related('lignes', 'imputations__ligne_budgetaire__tache',
                                             'prolongations__created_by'),
        pk=pk,
    )
    historiques    = HistoriqueStatut.objects.filter(
        type_entite='BC', entite_id=pk,
    ).select_related('utilisateur').order_by('-created_at')
    pieces_jointes = PieceJointe.objects.filter(type_entite='bc', entite_id=pk).select_related('uploaded_by')
    can_prolong = (
        request.user.role in ('admin', 'directeur_drh')
        and bc.statut in ('notifie', 'en_cours')
        and bc.date_echeance is not None
    )
    from datetime import date as _date
    return render(request, 'partials/_bc_detail.html', {
        'bc': bc,
        'historiques': historiques,
        'pieces_jointes': pieces_jointes,
        'can_prolong': can_prolong,
        'form_prolong': ProlongationBCForm(),
        'today': _date.today(),
    })


# ============ BILANS ============

def _resolve_bilan_periode(request, exercice):
    """
    Récupère la période sélectionnée pour les bilans.

    Si l'utilisateur choisit Trimestriel/Mensuel/Personnalisé sans préciser de
    valeur (trimestre/mois/dates), on utilise un défaut sensé pour ne PAS
    retomber sur Annuel — sinon la sélection serait silencieusement annulée.
    """
    from datetime import date, datetime, timedelta
    filtre_type = request.GET.get('type_periode', 'annuel')
    filtre_trimestre = request.GET.get('trimestre')
    filtre_mois = request.GET.get('mois')
    filtre_date_debut = request.GET.get('date_debut')
    filtre_date_fin = request.GET.get('date_fin')

    annee = exercice.annee
    today = date.today()
    date_debut = None
    date_fin = None

    if filtre_type == 'trimestriel':
        # Défaut : trimestre courant si on est dans l'exercice, sinon T1
        if not filtre_trimestre:
            filtre_trimestre = str(((today.month - 1) // 3) + 1) if today.year == annee else '1'
        try:
            t = int(filtre_trimestre)
            if t in (1, 2, 3, 4):
                date_debut = date(annee, (t - 1) * 3 + 1, 1)
                date_fin = date(annee, 12, 31) if t == 4 else date(annee, t * 3 + 1, 1) - timedelta(days=1)
        except ValueError:
            pass
    elif filtre_type == 'mensuel':
        # Défaut : mois courant si on est dans l'exercice, sinon Janvier
        if not filtre_mois:
            filtre_mois = str(today.month) if today.year == annee else '1'
        try:
            m = int(filtre_mois)
            if 1 <= m <= 12:
                date_debut = date(annee, m, 1)
                date_fin = date(annee, 12, 31) if m == 12 else date(annee, m + 1, 1) - timedelta(days=1)
        except ValueError:
            pass
    elif filtre_type == 'personnalise':
        # Défaut : période complète de l'exercice
        if not filtre_date_debut:
            d_default = exercice.date_debut or date(annee, 1, 1)
            filtre_date_debut = d_default.strftime('%Y-%m-%d')
        if not filtre_date_fin:
            f_default = exercice.date_fin or date(annee, 12, 31)
            filtre_date_fin = f_default.strftime('%Y-%m-%d')
        try:
            date_debut = datetime.strptime(filtre_date_debut, '%Y-%m-%d').date()
            date_fin = datetime.strptime(filtre_date_fin, '%Y-%m-%d').date()
        except ValueError:
            date_debut = date_fin = None

    # Repli sur Annuel uniquement si tous les autres modes ont échoué (valeurs invalides)
    if date_debut is None or date_fin is None:
        filtre_type = 'annuel'
        date_debut = exercice.date_debut or date(annee, 1, 1)
        date_fin = exercice.date_fin or date(annee, 12, 31)

    return {
        'type': filtre_type,
        'trimestre': filtre_trimestre,
        'mois': filtre_mois,
        'date_debut': date_debut,
        'date_fin': date_fin,
    }


@login_required
def bilans_view(request):
    exercice = _exercice_courant(request)
    if not exercice:
        return render(request, 'core/bilans.html', {'exercice': None})

    periode = _resolve_bilan_periode(request, exercice)
    date_debut = periode['date_debut']
    date_fin = periode['date_fin']

    taches = Tache.objects.filter(exercice=exercice).with_aggregates()
    bcs_base = BonCommande.objects.filter(exercice=exercice)
    # Filtrage par date d'émission selon la période choisie
    bcs = bcs_base.filter(date_emission__gte=date_debut, date_emission__lte=date_fin)

    budget_total = exercice.montant_global
    # Consommation = BC (TTC, hors annulés) + consommations directes (hors annulées),
    # filtrées sur la période — cohérent avec le dashboard (COHE-3) et le suivi officiel.
    total_bc = bcs.exclude(statut='annule').aggregate(t=Sum('montant_ttc'))['t'] or 0
    total_conso_directe = (
        ConsommationDirecte.objects
        .filter(ligne_budgetaire__tache__exercice=exercice, est_annule=False,
                date_consommation__gte=date_debut, date_consommation__lte=date_fin)
        .aggregate(t=Sum('montant'))['t']
        or 0
    )
    consommation = total_bc + total_conso_directe
    solde = budget_total - consommation
    taux = round((float(consommation) / float(budget_total)) * 100, 1) if budget_total > 0 else 0

    # Top 10 tâches par taux de consommation
    taches_sorted = sorted(taches, key=lambda t: float(t.taux_consommation), reverse=True)
    top10 = taches_sorted[:10]
    chart_labels = [f"{t.numero} — {t.titre[:35]}" for t in top10]
    chart_data = [float(t.taux_consommation) for t in top10]
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

    # Donut budgétaire global
    budget_donut = [
        {'label': 'Consommé', 'value': float(consommation), 'color': '#E74C3C'},
        {'label': 'Disponible', 'value': max(0.0, float(solde)), 'color': '#1A5632'},
    ]

    # Détail des engagements par BC (pour la section "Imputations" en bas)
    bcs_avec_imputations = (
        bcs.select_related('tache', 'prestataire')
        .prefetch_related('imputations__ligne_budgetaire')
        .order_by('-date_emission')
    )

    mois_choices = [
        (1, 'Janvier'), (2, 'Février'), (3, 'Mars'), (4, 'Avril'),
        (5, 'Mai'), (6, 'Juin'), (7, 'Juillet'), (8, 'Août'),
        (9, 'Septembre'), (10, 'Octobre'), (11, 'Novembre'), (12, 'Décembre'),
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
        'budget_donut': budget_donut,
        'bcs_avec_imputations': bcs_avec_imputations,
        'mois_choices': mois_choices,
    }
    return render(request, 'core/bilans.html', context)


@login_required
@role_required('admin')
def bilan_csv_export(request):
    """Export CSV du bilan ligne par ligne, format Excel-FR."""
    exercice = _exercice_courant(request)
    if not exercice:
        messages.error(request, "Aucun exercice sélectionné.")
        return redirect('bilans')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = (
        f'attachment; filename="Suivi_Taches_DRH_{exercice.annee}.csv"'
    )
    # BOM pour Excel
    response.write('﻿')
    writer = csv.writer(response, delimiter=';')
    # En-tête identitaire PAD (visible à l'ouverture dans Excel)
    from datetime import date as _date
    writer.writerow(['PORT AUTONOME DE DOUALA - PORT AUTHORITY OF DOUALA'])
    writer.writerow(['Direction des Ressources Humaines'])
    writer.writerow([f'Suivi détaillé des tâches - Exercice {exercice.annee}'])
    writer.writerow([f'Édité le {_date.today().strftime("%d/%m/%Y")} par {request.user.nom_complet or request.user.username}'])
    writer.writerow([])  # ligne vide de séparation
    writer.writerow([
        'N° Tâche', 'Titre tâche',
        'Code nature', 'Libellé nature',
        'Budget initial', 'Transfert +', 'Transfert -',
        'Budget ajusté', 'Consommation', 'Solde', 'Taux (%)',
    ])

    taches = Tache.objects.filter(exercice=exercice, actif=True).order_by('numero')
    for tache in taches:
        lignes = LigneBudgetaire.objects.filter(
            tache=tache, actif=True
        ).with_aggregates().order_by('code_nature')
        for ligne in lignes:
            tp = getattr(ligne, 'transfert_plus', 0) or 0
            tm = getattr(ligne, 'transfert_moins', 0) or 0
            ba = getattr(ligne, 'budget_ajuste', ligne.montant_initial) or 0
            co = getattr(ligne, 'consommation', 0) or 0
            so = getattr(ligne, 'solde', ba - co) or 0
            tx = getattr(ligne, 'taux_consommation', 0) or 0
            writer.writerow([
                tache.numero, tache.titre,
                ligne.code_nature, ligne.libelle_nature,
                f"{float(ligne.montant_initial):.0f}",
                f"{float(tp):.0f}",
                f"{float(tm):.0f}",
                f"{float(ba):.0f}",
                f"{float(co):.0f}",
                f"{float(so):.0f}",
                f"{float(tx):.1f}",
            ])
    app_logger.info("Export CSV bilan %s par %s", exercice.annee, request.user.username)
    return response


@login_required
@role_required('admin')
def bilan_pdf_export(request):
    """Génère et télécharge le rapport PDF du bilan budgétaire — format PAD."""
    from .services.pdf_service import generer_pdf_bilan
    exercice = _exercice_courant(request)
    if not exercice:
        messages.error(request, "Aucun exercice sélectionné.")
        return redirect('bilans')

    periode = _resolve_bilan_periode(request, exercice)
    date_debut = periode['date_debut']
    date_fin = periode['date_fin']

    taches = list(
        Tache.objects.filter(exercice=exercice, actif=True)
        .with_aggregates().order_by('numero')
    )

    # Pré-charger les lignes annotées pour chaque tâche
    lignes_par_tache = {}
    for t in taches:
        lignes_par_tache[t.pk] = list(
            LigneBudgetaire.objects.filter(tache=t, actif=True).with_aggregates().order_by('code_nature')
        )

    bcs = BonCommande.objects.filter(
        exercice=exercice, date_emission__gte=date_debut, date_emission__lte=date_fin,
    )
    budget_total = exercice.montant_global
    # Consommation = BC (TTC, hors annulés) + consommations directes (hors annulées),
    # filtrées sur la période — cohérent avec le dashboard (COHE-3) et le suivi officiel.
    total_bc = bcs.exclude(statut='annule').aggregate(t=Sum('montant_ttc'))['t'] or 0
    total_conso_directe = (
        ConsommationDirecte.objects
        .filter(ligne_budgetaire__tache__exercice=exercice, est_annule=False,
                date_consommation__gte=date_debut, date_consommation__lte=date_fin)
        .aggregate(t=Sum('montant'))['t']
        or 0
    )
    consommation = total_bc + total_conso_directe
    solde = budget_total - consommation
    taux = round((float(consommation) / float(budget_total)) * 100, 1) if budget_total > 0 else 0

    bc_statuts = bcs.aggregate(
        cree=Count('id', filter=Q(statut='cree')),
        notifie=Count('id', filter=Q(statut='notifie')),
        en_cours=Count('id', filter=Q(statut='en_cours')),
        execute=Count('id', filter=Q(statut='execute')),
        annule=Count('id', filter=Q(statut='annule')),
    )

    pdf_bytes = generer_pdf_bilan(
        exercice=exercice,
        taches=taches,
        consommation=consommation,
        budget_total=budget_total,
        solde=solde,
        taux=taux,
        bc_statuts=bc_statuts,
        periode=periode['type'],
        date_debut=date_debut,
        date_fin=date_fin,
        lignes_par_tache=lignes_par_tache,
    )
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = (
        f'attachment; filename="Suivi_Taches_DRH_{exercice.annee}_{periode["type"]}.pdf"'
    )
    app_logger.info("Export PDF bilan %s (%s) par %s", exercice.annee, periode['type'], request.user.username)
    return response


# ============ PIÈCES JOINTES ============

_MAGIC_SIGNATURES = [
    (b'\x25\x50\x44\x46', 'pdf'),              # %PDF
    (b'\xff\xd8\xff', 'jpeg'),                  # JPEG
    (b'\x89\x50\x4e\x47\x0d\x0a\x1a\x0a', 'png'),  # PNG
    (b'\x47\x49\x46\x38', 'gif'),              # GIF87a / GIF89a
    (b'\xd0\xcf\x11\xe0', 'ole2'),             # DOC / XLS (OLE2)
    (b'\x50\x4b\x03\x04', 'zip'),              # DOCX / XLSX (ZIP)
    (b'\x50\x4b\x05\x06', 'zip'),              # ZIP vide
]


def _magic_bytes_ok(fichier):
    """Vérifie que le fichier correspond à un type MIME autorisé via ses magic bytes."""
    header = fichier.read(12)
    fichier.seek(0)
    if len(header) < 4:
        return False
    # WEBP : RIFF????WEBP
    if len(header) >= 12 and header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return True
    for sig, _ in _MAGIC_SIGNATURES:
        if header[:len(sig)] == sig:
            return True
    return False


_EXTENSIONS_PJ = ('pdf', 'jpg', 'jpeg', 'png', 'gif', 'webp', 'doc', 'docx', 'xls', 'xlsx')


def _valider_fichier_pj(fichier):
    """Valide un fichier uploadé (taille, extension, magic bytes).

    Retourne (ok: bool, message_erreur: str).
    """
    if fichier.size > PieceJointe.TAILLE_MAX:
        return False, "Fichier trop volumineux (max 10 Mo)."
    ext = fichier.name.lower().rsplit('.', 1)[-1] if '.' in fichier.name else ''
    if ext not in _EXTENSIONS_PJ:
        return False, "Type de fichier non autorisé (PDF, images, Word, Excel uniquement)."
    if not _magic_bytes_ok(fichier):
        return False, "Contenu du fichier non reconnu — upload refusé."
    return True, ""


@login_required
@role_required('admin')
@require_POST
def piece_jointe_upload(request):
    """Upload d'une pièce jointe sur une DA ou un BC (admin / directeur_drh / assistante_drh uniquement)."""
    type_entite   = request.POST.get('type_entite', '').strip()
    entite_id_raw = request.POST.get('entite_id', '').strip()
    fichier       = request.FILES.get('fichier')

    # ── 1. Valider type_entite contre une liste blanche (évite l'IDOR)
    _ENTITY_MODELS = {'da': DemandeAchat, 'bc': BonCommande}
    _REDIRECT_MAP  = {'da': 'da_list',    'bc': 'bc_list'}
    if type_entite not in _ENTITY_MODELS:
        messages.error(request, "Type d'entité invalide.")
        return redirect('da_list')
    redirect_url = _REDIRECT_MAP[type_entite]

    # ── 2. Valider entite_id (évite les 500 sur int())
    try:
        entite_id = int(entite_id_raw)
    except (ValueError, TypeError):
        messages.error(request, "Identifiant d'entité invalide.")
        return redirect(redirect_url)

    # ── 3. Vérifier que l'entité cible existe (404 si inconnue)
    get_object_or_404(_ENTITY_MODELS[type_entite], pk=entite_id)

    if not fichier:
        messages.error(request, "Aucun fichier sélectionné.")
        return redirect(redirect_url)

    # ── 4-5. Validation taille + extension + magic bytes (helper partagé)
    ok, err = _valider_fichier_pj(fichier)
    if not ok:
        messages.error(request, err)
        return redirect(redirect_url)

    type_piece = request.POST.get('type_piece', 'autre').strip()
    valid_types = {c[0] for c in PieceJointe.TYPE_PIECE_CHOICES}
    if type_piece not in valid_types:
        type_piece = 'autre'

    # Titre personnalisé : pertinent surtout pour le type « Autre »
    titre_perso = request.POST.get('titre_personnalise', '').strip()[:100]

    PieceJointe.objects.create(
        type_entite=type_entite,
        entite_id=entite_id,
        type_piece=type_piece,
        titre_personnalise=titre_perso,
        fichier=fichier,
        nom_original=fichier.name,
        taille=fichier.size,
        uploaded_by=request.user,
    )
    log_action(request.user, 'PJ.upload',
               f"Upload pièce jointe « {fichier.name} » sur {type_entite.upper()} #{entite_id}",
               type_entite, entite_id)
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
                Q(numero__icontains=q) | Q(titre__icontains=q)
            ).order_by('numero')[:8],
            'bcs': BonCommande.objects.select_related('tache', 'prestataire').filter(
                Q(numero__icontains=q) | Q(prestataire__nom__icontains=q) | Q(tache__titre__icontains=q)
            ).order_by('-created_at')[:8],
            'das': DemandeAchat.objects.select_related('ligne_budgetaire__tache', 'created_by').filter(
                Q(reference__icontains=q) | Q(objet__icontains=q)
            ).order_by('-created_at')[:8],
            'prestataires': Prestataire.objects.filter(
                Q(nom__icontains=q) | Q(code__icontains=q) | Q(email__icontains=q)
            ).order_by('nom')[:8],
            'virements': VirementBudgetaire.objects.select_related(
                'ligne_source', 'ligne_destination',
                'ligne_source__tache', 'ligne_destination__tache',
            ).filter(
                Q(ligne_source__code_nature__icontains=q)
                | Q(ligne_destination__code_nature__icontains=q)
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
@role_required('admin')
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
    # Récupère le mot de passe temporaire généré lors du reset (une seule fois, TTL 5 min)
    reset_pwd_info = request.session.pop('reset_pwd_info', None)
    if reset_pwd_info:
        try:
            from datetime import datetime as _dt
            expires = _dt.fromisoformat(reset_pwd_info['_expires'])
            if timezone.now() > timezone.make_aware(expires.replace(tzinfo=None)) if expires.tzinfo is None else timezone.now() > expires:
                reset_pwd_info = None  # Expiré
        except (KeyError, ValueError, TypeError):
            reset_pwd_info = None
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
    # Validation du rôle contre la liste blanche
    valid_roles = {r[0] for r in Utilisateur.ROLE_CHOICES}
    if role not in valid_roles:
        messages.error(request, f"Rôle invalide : « {role} ».")
        return redirect('utilisateurs_list')
    # Validation complète du mot de passe (AUTH_PASSWORD_VALIDATORS)
    from django.contrib.auth.password_validation import validate_password as _vp
    try:
        _vp(password)
    except ValidationError as ve:
        for msg in ve.messages:
            messages.error(request, msg)
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
    valid_roles = {r[0] for r in Utilisateur.ROLE_CHOICES}
    new_role = request.POST.get('role', u.role)
    if new_role not in valid_roles:
        messages.error(request, f"Rôle invalide : « {new_role} ».")
        return redirect('utilisateurs_list')
    u.nom_complet = request.POST.get('nom_complet', u.nom_complet).strip()
    u.email       = request.POST.get('email', u.email).strip()
    u.role        = new_role
    if 'is_active' in request.POST:
        u.is_active = request.POST.get('is_active') in ('on', 'true', '1')
    u.save()
    log_action(request.user, 'User.edit', f"Modification de {u.username} (rôle : {u.role})", 'user', u.pk)
    messages.success(request, f"Utilisateur « {u.username} » mis à jour.")
    return redirect('utilisateurs_list')


@login_required
@role_required('admin')
def utilisateur_detail(request, pk):
    """Fragment HTML — détail d'un utilisateur (pour l'offcanvas)."""
    utilisateur = get_object_or_404(Utilisateur, pk=pk)
    return render(request, 'partials/_utilisateur_detail.html', {
        'utilisateur': utilisateur,
    })


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
    # Stocke le mot de passe en session avec TTL 5 min (affiché une seule fois)
    request.session['reset_pwd_info'] = {
        'username': u.username,
        'password': new_pwd,
        '_expires': (timezone.now() + timezone.timedelta(minutes=5)).isoformat(),
    }
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
                'tache_numero': d.tache.numero if d.tache else None,
            }
            for d in DemandeAchat.objects.filter(created_by=user).select_related('ligne_budgetaire__tache')
        ],
        'virements_crees': [
            {
                'ligne_source': v.ligne_source.code_nature,
                'ligne_destination': v.ligne_destination.code_nature,
                'montant': float(v.montant),
                'motif': v.motif,
                'created_at': v.created_at.isoformat(),
            }
            for v in VirementBudgetaire.objects.filter(created_by=user).select_related(
                'ligne_source', 'ligne_destination',
            )
        ],
        'journal_actions': [
            {
                'type_action': j.type_action,
                'description': j.description,
                'entite_type': j.entite_type,
                'entite_id': j.entite_id,
                'created_at': j.created_at.isoformat(),
                # hash_chain exclu intentionnellement (métadonnée interne d'audit)
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
def exercice_detail(request, pk):
    """Fragment HTML — détail d'un exercice (pour l'offcanvas)."""
    from django.db.models import Sum as _Sum
    exercice = get_object_or_404(ExerciceBudgetaire, pk=pk)
    taches_qs = list(Tache.objects.filter(exercice=exercice, actif=True).with_aggregates())
    nb_taches = len(taches_qs)
    nb_lignes = LigneBudgetaire.objects.filter(tache__exercice=exercice, actif=True).count()
    nb_das = DemandeAchat.objects.filter(exercice=exercice).count()
    nb_bcs = BonCommande.objects.filter(exercice=exercice).count()
    budget_total = sum((t.total_budget_ajuste or Decimal('0')) for t in taches_qs)
    consommation = sum((t.total_consommation or Decimal('0')) for t in taches_qs)
    solde = budget_total - consommation
    taux = round(float(consommation) / float(budget_total) * 100, 1) if budget_total > 0 else 0
    return render(request, 'partials/_exercice_detail.html', {
        'exercice': exercice,
        'nb_taches': nb_taches,
        'nb_lignes': nb_lignes,
        'nb_das': nb_das,
        'nb_bcs': nb_bcs,
        'budget_total': budget_total,
        'consommation': consommation,
        'solde': solde,
        'taux': taux,
    })


@login_required
def exercices_list(request):
    exercices = ExerciceBudgetaire.objects.order_by('-annee')
    stats = {}
    for ex in exercices:
        taches = list(Tache.objects.filter(exercice=ex, actif=True).with_aggregates())
        budget = sum((t.total_budget_ajuste or Decimal('0')) for t in taches)
        conso = sum((t.total_consommation or Decimal('0')) for t in taches)
        solde = budget - conso
        stats[ex.pk] = {
            'budget': budget,
            'conso': conso,
            'solde': solde,
            'taux': round(float(conso) / float(budget) * 100, 1) if budget else 0,
            'nb_taches': len(taches),
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
        # Règle R7 : désactiver tous les exercices existants (atomic + lock)
        with transaction.atomic():
            list(ExerciceBudgetaire.objects.select_for_update().all())
            ExerciceBudgetaire.objects.all().update(is_active=False)
            ex = ExerciceBudgetaire.objects.create(
                annee=annee,
                date_debut=d_debut,
                date_fin=d_fin,
                montant_global=montant,
                statut='actif',
                is_active=True,
                exercice_precedent=ExerciceBudgetaire.objects.filter(
                    is_locked=True,
                ).order_by('-annee').first(),
            )
        log_action(request.user, 'Exercice.create', f"Création de l'exercice {annee} (R7 appliquée)", 'exercice', ex.pk)
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
    ex.is_locked = True
    ex.is_active = False
    ex.save(update_fields=['statut', 'is_locked', 'is_active'])
    log_action(request.user, 'Exercice.cloture', f"Clôture de l'exercice {ex.annee}", 'exercice', ex.pk)
    messages.success(request, f"Exercice {ex.annee} clôturé et verrouillé en lecture seule.")
    return redirect('exercices_list')


@login_required
@role_required('admin')
@require_POST
@transaction.atomic
def exercice_reconduire(request, pk):
    """
    Reconduit un exercice : crée un nouvel exercice (année+1) avec les MÊMES tâches
    et lignes budgétaires copiées, mais avec montants à 0.
    L'utilisateur ajuste ensuite les budgets via les modals d'édition.
    """
    from datetime import date as _date
    from decimal import Decimal as _D
    src = get_object_or_404(ExerciceBudgetaire, pk=pk)
    nouvelle_annee = src.annee + 1
    # Option : copier aussi les budgets (sinon montants à 0, comportement par défaut)
    garder_montants = bool(request.POST.get('garder_montants'))

    if ExerciceBudgetaire.objects.filter(annee=nouvelle_annee).exists():
        messages.error(request, f"L'exercice {nouvelle_annee} existe déjà.")
        return redirect('exercices_list')

    # Règle R7 : désactiver tous les exercices existants (lock pour empêcher race)
    list(ExerciceBudgetaire.objects.select_for_update().all())
    ExerciceBudgetaire.objects.all().update(is_active=False)
    nouveau = ExerciceBudgetaire.objects.create(
        annee=nouvelle_annee,
        date_debut=_date(nouvelle_annee, 1, 1),
        date_fin=_date(nouvelle_annee, 12, 31),
        montant_global=_D('0'),
        statut='actif',
        is_active=True,
        exercice_precedent=src,
    )

    # Copie des tâches actives
    nb_taches = nb_lignes = 0
    for tache_src in Tache.objects.filter(exercice=src, actif=True).order_by('numero'):
        tache_new = Tache.objects.create(
            exercice=nouveau,
            numero=tache_src.numero,
            titre=tache_src.titre,
            actif=True,
        )
        nb_taches += 1
        # Copie des lignes budgétaires avec montant à 0
        for ligne_src in LigneBudgetaire.objects.filter(tache=tache_src, actif=True).order_by('code_nature'):
            LigneBudgetaire.objects.create(
                tache=tache_new,
                code_nature=ligne_src.code_nature,
                libelle_nature=ligne_src.libelle_nature,
                montant_initial=(ligne_src.montant_initial if garder_montants else _D('0')),
                actif=True,
            )
            nb_lignes += 1

    if garder_montants:
        nouveau.montant_global = (
            LigneBudgetaire.objects.filter(tache__exercice=nouveau)
            .aggregate(t=Sum('montant_initial'))['t'] or _D('0')
        )
        nouveau.save(update_fields=['montant_global'])

    detail_montants = 'budgets repris' if garder_montants else 'montants à 0 — à ajuster'
    log_action(
        request.user, 'Exercice.reconduit',
        f"Reconduction {src.annee} → {nouvelle_annee} ({nb_taches} tâches, {nb_lignes} lignes, {detail_montants})",
        'exercice', nouveau.pk,
    )
    messages.success(
        request,
        f"Exercice {nouvelle_annee} reconduit : {nb_taches} tâches et {nb_lignes} lignes "
        f"copiées ({detail_montants})."
    )
    return redirect('exercices_list')


@login_required
@role_required('admin')
@require_POST
def repertoire_sync(request, pk):
    """Verse les tâches/lignes d'un exercice dans le répertoire réutilisable (wizard)."""
    from core.services.repertoire_service import sync_repertoire_from_exercice
    exercice = get_object_or_404(ExerciceBudgetaire, pk=pk)
    nb_taches, nb_lignes = sync_repertoire_from_exercice(exercice)
    log_action(
        request.user, 'Repertoire.sync',
        f"Répertoire alimenté depuis l'exercice {exercice.annee} ({nb_taches} tâches, {nb_lignes} lignes)",
        'exercice', exercice.pk,
    )
    messages.success(
        request,
        f"Répertoire alimenté depuis l'exercice {exercice.annee} : {nb_taches} tâches et "
        f"{nb_lignes} lignes disponibles pour la création de futurs exercices (wizard)."
    )
    return redirect('exercices_list')


@login_required
@role_required('admin')
def exercice_template_excel(request):
    """Stub : template Excel pour import de budgets (à venir)."""
    messages.info(
        request,
        "L'import Excel sera disponible prochainement. "
        "Pour l'instant, utilisez la reconduction d'exercice ou le seed de données."
    )
    return redirect('exercices_list')


@login_required
@role_required('admin')
def exercice_import_excel(request):
    """Stub : import Excel des budgets (à venir, requires openpyxl)."""
    messages.info(
        request,
        "L'import Excel sera disponible prochainement (nécessite openpyxl). "
        "Pour l'instant, utilisez la reconduction d'exercice ou le seed de données."
    )
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
    exercice = _exercice_courant(request)
    if request.method == 'POST':
        # Reset seed (DEV uniquement)
        if 'reset_seed' in request.POST:
            from django.conf import settings
            if not settings.DEBUG:
                messages.error(
                    request,
                    "La réinitialisation des données de démonstration est interdite en production."
                )
                return redirect('parametres')
            from django.core.management import call_command
            try:
                call_command('seed_real_data')
                messages.success(request, "Données de démonstration réinitialisées.")
            except Exception as e:
                messages.error(request, f"Erreur lors du seed : {e}")
            return redirect('parametres')

        # Seuil d'alerte
        if 'seuil_alerte' in request.POST and exercice is not None:
            raw = request.POST.get('seuil_alerte', '').strip()
            try:
                seuil = int(raw)
                if 50 <= seuil <= 100:
                    exercice.seuil_alerte = seuil
                    exercice.save(update_fields=['seuil_alerte'])
                    log_action(
                        request.user, 'Parametres.seuil',
                        f"Seuil d'alerte porté à {seuil}% sur l'exercice {exercice.annee}",
                        'exercice', exercice.pk,
                    )
                    messages.success(request, f"Seuil d'alerte mis à jour : {seuil}%.")
                else:
                    messages.error(request, "Le seuil doit être entre 50% et 100%.")
            except ValueError:
                messages.error(request, "Valeur de seuil invalide.")
            return redirect('parametres')

    return render(request, 'core/parametres.html', {'exercice': exercice})


# ============ PROLONGATION BC ============

@login_required
@role_required('directeur_drh')
@require_POST
@transaction.atomic
def bc_prolong(request, pk):
    """Prolonge l'échéance d'un BC (crée un enregistrement ProlongationBC)."""
    bc = get_object_or_404(BonCommande, pk=pk)
    if bc.statut not in ('notifie', 'en_cours'):
        messages.error(request, "Seul un BC notifié ou en cours peut être prolongé.")
        return redirect('bc_list')
    if not bc.date_echeance:
        messages.error(request, "Ce BC n'a pas de date d'échéance à prolonger.")
        return redirect('bc_list')
    form = ProlongationBCForm(request.POST)
    if form.is_valid():
        prolong = form.save(commit=False)
        prolong.bon_commande = bc
        prolong.ancienne_echeance = bc.date_echeance
        prolong.created_by = request.user
        prolong.save()
        log_action(
            request.user, 'BC.prolong',
            f"Prolongation {bc.numero} : {prolong.ancienne_echeance} → {prolong.nouvelle_echeance} "
            f"({prolong.duree_prolongation_jours} j) — {prolong.motif}",
            'bc', bc.pk,
        )
        messages.success(
            request,
            f"Échéance prolongée : {prolong.ancienne_echeance} → {prolong.nouvelle_echeance}.",
        )
    else:
        for field, errs in form.errors.items():
            for e in errs:
                messages.error(request, f"{field}: {e}")
    return redirect('bc_list')


# ============ LIGNES BUDGÉTAIRES ============

@login_required
@role_required('admin', 'assistante_drh')
@require_POST
def ligne_budgetaire_create(request, tache_pk):
    tache = get_object_or_404(Tache, pk=tache_pk)
    form = LigneBudgetaireForm(request.POST)
    if form.is_valid():
        ligne = form.save(commit=False)
        ligne.tache = tache
        ligne.save()
        log_action(
            request.user, 'Tache.edit',
            f"Ajout ligne {ligne.code_nature} à la tâche {tache.numero}",
            'tache', tache.pk,
        )
        messages.success(request, f"Ligne {ligne.code_nature} ajoutée à la tâche {tache.numero}.")
    else:
        for field, errs in form.errors.items():
            for e in errs:
                messages.error(request, f"{field}: {e}")
    return redirect('taches_list')


@login_required
@role_required('admin', 'assistante_drh')
@require_POST
def ligne_budgetaire_edit(request, pk):
    ligne = get_object_or_404(LigneBudgetaire, pk=pk)

    # Exercice clôturé = lecture seule
    locked, msg = _check_exercice_non_verrouille(ligne.tache.exercice)
    if locked:
        messages.error(request, msg)
        return redirect('taches_list')

    montant_raw = request.POST.get('montant_initial', '')

    # Parsing tolérant au format français : « 500 000,00 », « 500000,00 »,
    # espaces (normaux/insécables) comme séparateurs de milliers, virgule décimale.
    from decimal import Decimal as D, InvalidOperation
    nettoye = (
        montant_raw.strip()
        .replace(' ', '').replace('\xa0', '').replace(' ', '')
        .replace(',', '.')
    )
    if not nettoye:
        messages.error(request, "Veuillez saisir un montant.")
        return redirect('taches_list')
    try:
        montant = D(nettoye)
    except (InvalidOperation, ValueError):
        messages.error(request, f"Montant invalide : « {montant_raw} ».")
        return redirect('taches_list')
    if montant < 0:
        messages.error(request, "Le montant ne peut pas être négatif.")
        return redirect('taches_list')

    ligne.montant_initial = montant
    update_fields = ['montant_initial']

    # Code nature + libellé : réservés à l'admin
    if request.user.role == 'admin':
        code = request.POST.get('code_nature', '').strip()
        libelle = request.POST.get('libelle_nature', '').strip()
        if code:
            if len(code) > 10:
                messages.error(request, "Le code nature ne doit pas dépasser 10 caractères.")
                return redirect('taches_list')
            ligne.code_nature = code
            update_fields.append('code_nature')
        if libelle:
            ligne.libelle_nature = libelle[:255]
            update_fields.append('libelle_nature')

    ligne.save(update_fields=update_fields)
    log_action(
        request.user, 'Tache.edit',
        f"Ligne {ligne.code_nature} (tâche {ligne.tache.numero}) modifiée — "
        f"montant {montant:,.0f} FCFA",
        'ligne', ligne.pk,
    )
    messages.success(request, f"Ligne {ligne.code_nature} mise à jour.")
    return redirect('taches_list')


@login_required
def ligne_detail(request, pk):
    """Fragment HTML — détail d'une ligne budgétaire (pour l'offcanvas)."""
    ligne = get_object_or_404(
        LigneBudgetaire.objects.with_aggregates().select_related('tache'), pk=pk
    )
    imputations = (
        ImputationBC.objects.filter(ligne_budgetaire=ligne)
        .select_related('bon_commande', 'bon_commande__prestataire')
        .order_by('-bon_commande__date_emission')
    )
    virements_entrants = (
        VirementBudgetaire.objects.filter(ligne_destination=ligne)
        .select_related('ligne_source', 'ligne_source__tache', 'created_by')
        .order_by('-created_at')
    )
    virements_sortants = (
        VirementBudgetaire.objects.filter(ligne_source=ligne)
        .select_related('ligne_destination', 'ligne_destination__tache', 'created_by')
        .order_by('-created_at')
    )
    consommations_directes = list(
        ConsommationDirecte.objects.filter(ligne_budgetaire=ligne)
        .select_related('created_by')
        .order_by('-date_consommation', '-created_at')
    )
    # Associe la pièce jointe éventuelle à chaque consommation (1 requête)
    if consommations_directes:
        conso_ids = [c.pk for c in consommations_directes]
        pj_par_conso = {
            pj.entite_id: pj
            for pj in PieceJointe.objects.filter(
                type_entite='conso', entite_id__in=conso_ids,
            )
        }
        for c in consommations_directes:
            c.piece_jointe = pj_par_conso.get(c.pk)
    exercice = ligne.tache.exercice
    can_consommer = (
        request.user.role in ('admin', 'directeur_drh', 'assistante_drh')
        and not exercice.is_locked
    )
    return render(request, 'partials/_ligne_detail.html', {
        'ligne': ligne,
        'imputations': imputations,
        'virements_entrants': virements_entrants,
        'virements_sortants': virements_sortants,
        'consommations_directes': consommations_directes,
        'can_consommer': can_consommer,
    })


# ============ CONSOMMATIONS DIRECTES ============

@login_required
@role_required('admin', 'directeur_drh', 'assistante_drh')
@require_http_methods(['GET', 'POST'])
def consommation_create(request, ligne_pk):
    """Enregistre une consommation directe (sans BC) sur une ligne budgétaire."""
    ligne = get_object_or_404(LigneBudgetaire.objects.select_related('tache__exercice'), pk=ligne_pk)
    exercice = ligne.tache.exercice

    locked, msg = _check_exercice_non_verrouille(exercice)
    if locked:
        messages.error(request, msg)
        return redirect('taches_list')
    # MED-2 : interdire les consommations sur un exercice inactif (ni actif, ni clôturé)
    if not exercice.is_active:
        messages.error(
            request,
            f"L'exercice {exercice.annee} n'est pas actif — impossible d'enregistrer une consommation."
        )
        return redirect('taches_list')

    if request.method == 'POST':
        form = ConsommationDirecteForm(request.POST)
        fichier = request.FILES.get('piece_jointe')
        if form.is_valid():
            ligne_annotee = LigneBudgetaire.objects.with_aggregates().get(pk=ligne.pk)
            montant = form.cleaned_data['montant']
            file_ok, file_err = (True, "")
            if fichier:
                file_ok, file_err = _valider_fichier_pj(fichier)
            if montant > ligne_annotee.solde:
                messages.error(
                    request,
                    f"Solde insuffisant. Disponible : {ligne_annotee.solde:,.0f} FCFA",
                )
            elif not file_ok:
                messages.error(request, file_err)
            else:
                conso = form.save(commit=False)
                conso.ligne_budgetaire = ligne
                conso.created_by = request.user
                conso.save()
                if fichier:
                    PieceJointe.objects.create(
                        type_entite='conso', entite_id=conso.pk,
                        type_piece='autre', fichier=fichier, nom_original=fichier.name,
                        taille=fichier.size, uploaded_by=request.user,
                    )
                log_action(
                    request.user, 'Consommation.create',
                    f"Consommation directe de {montant:,.0f} FCFA sur {ligne.code_nature} "
                    f"— Motif : {conso.get_motif_display()}"
                    + (f" (pièce jointe : {fichier.name})" if fichier else ""),
                    'ConsommationDirecte', conso.pk,
                )
                messages.success(request, f"Consommation de {montant:,.0f} FCFA enregistrée.")
                return redirect('taches_list')
    else:
        from django.utils import timezone as _tz
        form = ConsommationDirecteForm(initial={'date_consommation': _tz.now().date()})

    ligne_annotee = LigneBudgetaire.objects.with_aggregates().get(pk=ligne.pk)
    return render(request, 'core/consommation_form.html', {
        'form': form,
        'ligne': ligne,
        'tache': ligne.tache,
        'exercice': exercice,
        'solde': ligne_annotee.solde,
    })


# ============ JOURNAL DE PROGRAMMATION PAR BC ============

@login_required
def journal_bc_view(request):
    """Journal des imputations budgétaires par BC."""
    exercice = _exercice_courant(request)
    bcs = (
        BonCommande.objects
        .filter(exercice=exercice)
        .prefetch_related('imputations__ligne_budgetaire__tache')
        .select_related('tache', 'prestataire')
        .exclude(statut='annule')
        .order_by('-date_emission', '-created_at')
        if exercice else BonCommande.objects.none()
    )
    return render(request, 'core/journal_bc.html', {
        'bcs': bcs,
        'exercice': exercice,
    })


# ============ RÈGLE R7 — ACTIVATION EXERCICE ============

@login_required
@role_required('admin')
@require_POST
def exercice_activer(request, pk):
    """Active un exercice. RÈGLE R7 : désactive automatiquement tous les autres."""
    exercice = get_object_or_404(ExerciceBudgetaire, pk=pk)
    try:
        exercice.activer(user=request.user)
        messages.success(
            request,
            f"Exercice {exercice.annee} activé. "
            f"Les autres exercices ont été automatiquement désactivés (Règle R7)."
        )
    except ValueError as e:
        messages.error(request, str(e))
    return redirect('exercices_list')


# ============ WIZARD — CRÉATION EXERCICE (4 ÉTAPES) ============

WIZARD_TTL_SECONDS = 30 * 60  # 30 minutes


def _wizard_get_session(request):
    """Récupère la session wizard ou None si absente/expirée."""
    wizard = request.session.get('wizard_exercice')
    if not wizard:
        return None
    started = wizard.get('_started_at')
    if started:
        from datetime import datetime
        try:
            started_dt = datetime.fromisoformat(started)
            if (timezone.now() - started_dt).total_seconds() > WIZARD_TTL_SECONDS:
                request.session.pop('wizard_exercice', None)
                return None
        except ValueError:
            pass
    return wizard


@login_required
@role_required('admin')
@require_POST
def wizard_exercice_cancel(request):
    """Abandonne le wizard et nettoie la session (HIGH-4)."""
    request.session.pop('wizard_exercice', None)
    messages.info(request, "Création d'exercice annulée.")
    return redirect('exercices_list')


@login_required
@role_required('admin')
def wizard_exercice_step1(request):
    """Étape 1 — Informations de base du nouvel exercice."""
    exercice_actif = ExerciceBudgetaire.get_actif()

    if request.method == 'POST':
        annee_raw      = request.POST.get('annee', '').strip()
        date_debut_raw = request.POST.get('date_debut', '').strip()
        date_fin_raw   = request.POST.get('date_fin', '').strip()
        seuil_raw      = request.POST.get('seuil_alerte', '80').strip()

        try:
            annee = int(annee_raw)
        except ValueError:
            messages.error(request, "Année invalide.")
            return redirect('wizard_exercice_step1')

        if ExerciceBudgetaire.objects.filter(annee=annee).exists():
            messages.error(request, f"Un exercice {annee} existe déjà.")
            return redirect('wizard_exercice_step1')

        from datetime import datetime as _dt
        try:
            d_debut = _dt.strptime(date_debut_raw, '%Y-%m-%d').date()
            d_fin   = _dt.strptime(date_fin_raw,   '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Dates invalides.")
            return redirect('wizard_exercice_step1')

        if d_fin <= d_debut:
            messages.error(request, "La date de fin doit être postérieure à la date de début.")
            return redirect('wizard_exercice_step1')

        request.session['wizard_exercice'] = {
            'annee':        annee,
            'date_debut':   date_debut_raw,
            'date_fin':     date_fin_raw,
            'seuil_alerte': int(seuil_raw) if seuil_raw.isdigit() else 80,
            'taches_selectionnees': [],
            'lignes_par_tache':     {},
            'budgets':              {},
            '_started_at':  timezone.now().isoformat(),
        }
        return redirect('wizard_exercice_step2')

    annee_prop = (exercice_actif.annee + 1) if exercice_actif else 2026
    # Pré-remplissage si l'utilisateur revient en arrière (données déjà en session)
    wizard = request.session.get('wizard_exercice', {})
    return render(request, 'core/wizard/step1_infos.html', {
        'exercice_actif': exercice_actif,
        'annee_proposee': annee_prop,
        'annee_saved':      wizard.get('annee', ''),
        'date_debut_saved': wizard.get('date_debut', ''),
        'date_fin_saved':   wizard.get('date_fin', ''),
        'seuil_saved':      wizard.get('seuil_alerte', 80),
        'etape': 1,
    })


@login_required
@role_required('admin')
def wizard_exercice_step2(request):
    """Étape 2 — Sélection des tâches depuis le répertoire."""
    wizard = _wizard_get_session(request)
    if wizard is None:
        messages.warning(request, "Session du wizard expirée ou inexistante. Recommencer.")
        return redirect('wizard_exercice_step1')

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'ajouter_tache':
            numero = request.POST.get('nouveau_numero', '').strip()
            titre  = request.POST.get('nouveau_titre', '').strip()
            if numero and titre:
                _, created = RepertoireTache.objects.get_or_create(
                    numero=numero, defaults={'titre': titre}
                )
                if created:
                    messages.success(request, f"Tâche {numero} ajoutée au répertoire.")
                else:
                    messages.warning(request, f"La tâche {numero} existe déjà dans le répertoire.")

        elif action == 'suivant':
            taches_ids = request.POST.getlist('taches_selectionnees')
            if not taches_ids:
                messages.error(request, "Sélectionnez au moins une tâche.")
            else:
                wizard['taches_selectionnees'] = taches_ids
                request.session['wizard_exercice'] = wizard
                return redirect('wizard_exercice_step3')

    taches_repertoire = RepertoireTache.objects.filter(actif=True)
    return render(request, 'core/wizard/step2_taches.html', {
        'wizard': wizard,
        'taches_repertoire': taches_repertoire,
        'taches_selectionnees': [str(x) for x in wizard.get('taches_selectionnees', [])],
        'etape': 2,
    })


@login_required
@role_required('admin')
def wizard_exercice_step3(request):
    """Étape 3 — Lignes et budgets par tâche."""
    wizard = _wizard_get_session(request)
    if wizard is None:
        messages.warning(request, "Session du wizard expirée ou inexistante. Recommencer.")
        return redirect('wizard_exercice_step1')
    taches_ids = wizard.get('taches_selectionnees', [])
    if not taches_ids:
        return redirect('wizard_exercice_step2')

    taches_selectionnees = list(
        RepertoireTache.objects.filter(pk__in=taches_ids).prefetch_related('lignes_repertoire')
    )

    if request.method == 'POST':
        action = request.POST.get('action', '')

        if action == 'ajouter_ligne':
            tache_id = request.POST.get('tache_id', '').strip()
            code     = request.POST.get('nouveau_code', '').strip()
            libelle  = request.POST.get('nouveau_libelle', '').strip()
            if tache_id and code and libelle:
                tache_rep = get_object_or_404(RepertoireTache, pk=tache_id)
                _, created = RepertoireLigne.objects.get_or_create(
                    tache_repertoire=tache_rep,
                    code_nature=code,
                    defaults={'libelle_nature': libelle},
                )
                if created:
                    messages.success(request, f"Ligne {code} ajoutée au répertoire.")
                else:
                    messages.warning(request, f"La ligne {code} existe déjà pour cette tâche.")

        elif action == 'suivant':
            lignes_par_tache = {}
            budgets          = {}
            erreur           = False
            for tache in taches_selectionnees:
                lignes_ids = request.POST.getlist(f'lignes_{tache.pk}')
                lignes_par_tache[str(tache.pk)] = lignes_ids
                for lid in lignes_ids:
                    raw = request.POST.get(f'budget_{tache.pk}_{lid}', '0').replace(' ', '').replace(',', '.')
                    try:
                        budgets[f'{tache.pk}_{lid}'] = float(raw)
                    except ValueError:
                        messages.error(request, "Montant invalide détecté.")
                        erreur = True
            if not erreur:
                wizard['lignes_par_tache'] = lignes_par_tache
                wizard['budgets']          = budgets
                request.session['wizard_exercice'] = wizard
                return redirect('wizard_exercice_step4')

    return render(request, 'core/wizard/step3_lignes_budgets.html', {
        'wizard': wizard,
        'taches_selectionnees': taches_selectionnees,
        'lignes_par_tache': wizard.get('lignes_par_tache', {}),
        'budgets': wizard.get('budgets', {}),
        'etape': 3,
    })


@login_required
@role_required('admin')
def wizard_exercice_step4(request):
    """Étape 4 — Confirmation et création finale."""
    wizard = _wizard_get_session(request)
    if wizard is None:
        messages.warning(request, "Session du wizard expirée ou inexistante. Recommencer.")
        return redirect('wizard_exercice_step1')

    taches_ids       = wizard.get('taches_selectionnees', [])
    taches           = list(RepertoireTache.objects.filter(pk__in=taches_ids))
    lignes_par_tache = wizard.get('lignes_par_tache', {})
    budgets          = wizard.get('budgets', {})
    budget_total     = sum(float(v) for v in budgets.values())

    if request.method == 'POST' and request.POST.get('action') == 'creer':
        try:
            with transaction.atomic():
                # Règle R7 — lock pour empêcher race condition
                list(ExerciceBudgetaire.objects.select_for_update().all())
                ExerciceBudgetaire.objects.all().update(is_active=False)

                exercice = ExerciceBudgetaire.objects.create(
                    annee         = int(wizard['annee']),
                    date_debut    = wizard['date_debut'],
                    date_fin      = wizard['date_fin'],
                    montant_global = Decimal(str(budget_total)),  # HIGH-5
                    seuil_alerte  = int(wizard.get('seuil_alerte', 80)),
                    statut        = 'actif',
                    is_active     = True,
                    exercice_precedent = ExerciceBudgetaire.objects.filter(
                        is_locked=True
                    ).order_by('-annee').first(),
                )

                for tache_rep in taches:
                    tache = Tache.objects.create(
                        numero   = tache_rep.numero,
                        titre    = tache_rep.titre,
                        exercice = exercice,
                        actif    = True,
                    )
                    lignes_ids = lignes_par_tache.get(str(tache_rep.pk), [])
                    lignes_rep = RepertoireLigne.objects.filter(pk__in=lignes_ids)
                    for ligne_rep in lignes_rep:
                        montant = budgets.get(f'{tache_rep.pk}_{ligne_rep.pk}', 0)
                        LigneBudgetaire.objects.create(
                            tache          = tache,
                            code_nature    = ligne_rep.code_nature,
                            libelle_nature = ligne_rep.libelle_nature,
                            montant_initial = Decimal(str(montant)),
                            actif          = True,
                        )

                JournalActivite.objects.create(
                    type_action = 'Exercice.create_wizard',
                    description = (
                        f"Exercice {exercice.annee} créé via wizard. "
                        f"{len(taches)} tâche(s) — budget total {budget_total:,.0f} FCFA."
                    ),
                    entite_type = 'ExerciceBudgetaire',
                    entite_id   = exercice.pk,
                    utilisateur = request.user,
                )

                del request.session['wizard_exercice']
                messages.success(
                    request,
                    f"Exercice {exercice.annee} créé avec succès ! "
                    f"{len(taches)} tâche(s) — Budget : {budget_total:,.0f} FCFA"
                )
                return redirect('dashboard')

        except Exception as e:
            messages.error(request, f"Erreur lors de la création : {e}")

    return render(request, 'core/wizard/step4_confirmation.html', {
        'wizard':           wizard,
        'taches':           taches,
        'lignes_par_tache': lignes_par_tache,
        'budgets':          budgets,
        'budget_total':     budget_total,
        'etape':            4,
        'prog_labels':      ['Infos', 'Tâches', 'Budget', 'Confirmation'],
    })


# ============ ANNULATION ADMIN ============

@login_required
@role_required('admin')
@require_http_methods(['GET', 'POST'])
def annuler_consommation_directe(request, pk):
    """Admin — annule une consommation directe (soft-delete avec traçabilité)."""
    conso = get_object_or_404(ConsommationDirecte.objects.select_related(
        'ligne_budgetaire__tache__exercice', 'created_by'
    ), pk=pk)

    if conso.est_annule:
        messages.warning(request, "Cette consommation est déjà annulée.")
        return redirect('taches_list')
    if conso.ligne_budgetaire.tache.exercice.is_locked:
        messages.error(request, "Impossible : l'exercice est clôturé.")
        return redirect('taches_list')

    if request.method == 'POST':
        motif = request.POST.get('motif', '').strip()
        if len(motif) < 5:
            messages.error(request, "Le motif d'annulation est obligatoire (5 caractères minimum).")
        else:
            with transaction.atomic():
                # Soft-delete : on garde l'enregistrement pour préserver l'audit (MED-3)
                conso.est_annule       = True
                conso.annule_le        = timezone.now()
                conso.annule_par       = request.user
                conso.motif_annulation = motif
                conso.save(update_fields=[
                    'est_annule', 'annule_le', 'annule_par', 'motif_annulation',
                ])
                LogAnnulation.objects.create(
                    type_entite       = 'consommation_directe',
                    entite_id         = conso.pk,
                    description_avant = (
                        f"Consommation de {conso.montant:,.0f} FCFA sur "
                        f"{conso.ligne_budgetaire.code_nature} "
                        f"le {conso.date_consommation} — Motif initial : {conso.get_motif_display()}"
                    ),
                    motif_annulation  = motif,
                    annule_par        = request.user,
                )
                JournalActivite.objects.create(
                    type_action = 'Consommation.annuler',
                    description = (
                        f"Admin {request.user.username} a annulé la consommation de "
                        f"{conso.montant:,.0f} FCFA sur {conso.ligne_budgetaire.code_nature}. "
                        f"Motif : {motif}"
                    ),
                    entite_type = 'ConsommationDirecte',
                    entite_id   = conso.pk,
                    utilisateur = request.user,
                )
            messages.success(
                request,
                f"Consommation de {conso.montant:,.0f} FCFA annulée. "
                f"Budget restitué sur la ligne {conso.ligne_budgetaire.code_nature}."
            )
            return redirect('taches_list')

    return render(request, 'core/annulation/confirm_annulation.html', {
        'objet': conso,
        'type':  'consommation',
        'titre': f"Annuler la consommation de {conso.montant:,.0f} FCFA sur {conso.ligne_budgetaire.code_nature}",
    })


@login_required
@role_required('admin')
@require_http_methods(['GET', 'POST'])
def annuler_virement(request, pk):
    """Admin — annule un virement via un virement inverse."""
    virement = get_object_or_404(VirementBudgetaire.objects.select_related(
        'ligne_source__tache__exercice', 'ligne_destination__tache', 'created_by'
    ), pk=pk)

    if virement.ligne_source.tache.exercice.is_locked:
        messages.error(request, "Impossible : l'exercice est clôturé.")
        return redirect('virements_list')

    if request.method == 'POST':
        motif = request.POST.get('motif', '').strip()
        if len(motif) < 5:
            messages.error(request, "Le motif d'annulation est obligatoire (5 caractères minimum).")
        else:
            # Vérifier que la ligne destination a assez de solde pour le virement inverse
            dest_annot = LigneBudgetaire.objects.filter(
                pk=virement.ligne_destination.pk
            ).with_aggregates().first()
            if (dest_annot.solde or Decimal('0')) < virement.montant:
                messages.error(
                    request,
                    f"Solde insuffisant sur {virement.ligne_destination.code_nature} "
                    f"pour annuler ce virement."
                )
            else:
                VirementBudgetaire.objects.create(
                    exercice           = virement.exercice,
                    ligne_source       = virement.ligne_destination,
                    ligne_destination  = virement.ligne_source,
                    montant            = virement.montant,
                    motif              = f"ANNULATION virement #{virement.pk} — {motif}",
                    created_by         = request.user,
                )
                LogAnnulation.objects.create(
                    type_entite       = 'virement',
                    entite_id         = virement.pk,
                    description_avant = (
                        f"Virement de {virement.montant:,.0f} FCFA de "
                        f"{virement.ligne_source.code_nature} vers "
                        f"{virement.ligne_destination.code_nature}"
                    ),
                    motif_annulation  = motif,
                    annule_par        = request.user,
                )
                JournalActivite.objects.create(
                    type_action = 'Virement.annuler',
                    description = (
                        f"Admin {request.user.username} a annulé le virement #{virement.pk} "
                        f"({virement.montant:,.0f} FCFA) via virement inverse. Motif : {motif}"
                    ),
                    entite_type = 'VirementBudgetaire',
                    entite_id   = virement.pk,
                    utilisateur = request.user,
                )
                messages.success(
                    request,
                    f"Virement #{virement.pk} annulé via virement inverse de "
                    f"{virement.montant:,.0f} FCFA."
                )
                return redirect('virements_list')

    return render(request, 'core/annulation/confirm_annulation.html', {
        'objet': virement,
        'type':  'virement',
        'titre': f"Annuler le virement #{virement.pk} ({virement.montant:,.0f} FCFA)",
    })


# ============ API INTERNE ============

@login_required
def api_ligne_solde(request, pk):
    """Solde disponible réel d'une ligne en JSON : solde comptable − DA déjà engagées."""
    from decimal import Decimal as _D
    ligne_annot = LigneBudgetaire.objects.filter(pk=pk).with_aggregates().first()
    if not ligne_annot:
        return JsonResponse({'error': 'Ligne introuvable'}, status=404)
    engage = DemandeAchat.objects.filter(
        ligne_budgetaire_id=pk, statut__in=['cree', 'en_etude', 'validee'],
    ).aggregate(t=Sum('montant_estime'))['t'] or _D('0')
    solde_comptable = ligne_annot.solde or _D('0')
    return JsonResponse({
        'solde':            float(solde_comptable),
        'solde_comptable':  float(solde_comptable),
        'budget_ajuste':    float(ligne_annot.budget_ajuste or 0),
        'consommation':     float(ligne_annot.consommation or 0),
        'montant_engage':   float(engage),
        'solde_disponible': float(solde_comptable - engage),
        'taux':             float(ligne_annot.taux_consommation or 0),
        'code_nature':      ligne_annot.code_nature,
        'libelle':          ligne_annot.libelle_nature,
    })


# ============ ÉDITION — DA ============

@login_required
@role_required('admin', 'directeur_drh', 'assistante_drh')
@require_http_methods(['GET', 'POST'])
def da_edit(request, pk):
    da = get_object_or_404(DemandeAchat.objects.select_related(
        'exercice', 'ligne_budgetaire__tache',
    ), pk=pk)
    exercice = da.exercice

    locked, msg = _check_exercice_non_verrouille(exercice)
    if locked:
        messages.error(request, msg)
        return redirect('da_list')

    if da.statut in ('validee', 'bc_cree'):
        messages.warning(request, "DA validée — modifications limitées (numéro + ligne uniquement).")

    if request.method == 'POST':
        form = DemandeAchatEditForm(request.POST, instance=da, exercice=exercice)
        if form.is_valid():
            form.save()
            log_action(
                request.user, 'DA.edit',
                f"Modification de la DA {da.reference} par {request.user.username}",
                'da', da.pk,
            )
            messages.success(request, f"DA {da.reference} mise à jour.")
            return redirect('da_list')
    else:
        form = DemandeAchatEditForm(instance=da, exercice=exercice)

    return render(request, 'core/da_form.html', {
        'form': form, 'da': da, 'edit_mode': True, 'exercice': exercice,
    })


# ============ ÉDITION — BC ============

@login_required
@role_required('admin', 'directeur_drh', 'assistante_drh')
@require_http_methods(['GET', 'POST'])
def bc_edit(request, pk):
    bc = get_object_or_404(BonCommande, pk=pk)

    if bc.statut == 'execute':
        messages.error(request, "Un BC exécuté est immuable (Règle R3).")
        return redirect('bc_list')

    if request.method == 'POST':
        form = BonCommandeEditForm(request.POST, instance=bc)
        if form.is_valid():
            form.save()
            log_action(
                request.user, 'BC.edit',
                f"Modification du BC {bc.numero} par {request.user.username}",
                'bc', bc.pk,
            )
            messages.success(request, f"BC {bc.numero} mis à jour.")
            return redirect('bc_list')
    else:
        form = BonCommandeEditForm(instance=bc)

    return render(request, 'core/bc_form.html', {
        'form': form, 'bc': bc, 'edit_mode': True,
    })


# ============ ÉDITION — TÂCHE ============

@login_required
@role_required('admin', 'assistante_drh')
@require_http_methods(['GET', 'POST'])
def tache_edit(request, pk):
    tache = get_object_or_404(Tache, pk=pk)

    locked, msg = _check_exercice_non_verrouille(tache.exercice)
    if locked:
        messages.error(request, msg)
        return redirect('taches_list')

    if request.method == 'POST':
        form = TacheForm(request.POST, instance=tache)
        if form.is_valid():
            form.save()
            log_action(
                request.user, 'Tache.edit',
                f"Modification de la tâche {tache.numero} — {tache.titre}",
                'tache', tache.pk,
            )
            messages.success(request, f"Tâche {tache.numero} mise à jour.")
            return redirect('taches_list')
    else:
        form = TacheForm(instance=tache)

    return render(request, 'core/tache_form.html', {
        'form': form, 'tache': tache, 'edit_mode': True,
    })


# ============ ÉDITION — PRESTATAIRE ============

@login_required
@role_required('admin', 'assistante_drh')
@require_http_methods(['GET', 'POST'])
def prestataire_edit(request, pk):
    prestataire = get_object_or_404(Prestataire, pk=pk)

    if request.method == 'POST':
        form = PrestataireForm(request.POST, instance=prestataire)
        if form.is_valid():
            form.save()
            log_action(
                request.user, 'Prestataire.edit',
                f"Modification du prestataire {prestataire.nom}",
                'prestataire', prestataire.pk,
            )
            messages.success(request, f"Prestataire « {prestataire.nom} » mis à jour.")
            return redirect('prestataires_list')
    else:
        form = PrestataireForm(instance=prestataire)

    return render(request, 'core/prestataire_form.html', {
        'form': form, 'prestataire': prestataire, 'edit_mode': True,
    })


# ============ PROLONGATION BC — PAGE DÉDIÉE ============

@login_required
@role_required('admin', 'directeur_drh')
@require_http_methods(['GET', 'POST'])
def bc_prolonger_page(request, pk):
    """Page dédiée de prolongation d'un BC avec formulaire + historique."""
    bc = get_object_or_404(BonCommande.objects.select_related('prestataire', 'tache'), pk=pk)

    if bc.statut in ('execute', 'annule'):
        messages.error(request, f"Impossible de prolonger un BC {bc.get_statut_display()}.")
        return redirect('bc_list')
    if not bc.date_echeance:
        messages.error(request, "Ce BC n'a pas de date d'échéance à prolonger.")
        return redirect('bc_list')

    if request.method == 'POST':
        form = ProlongationBCForm(request.POST)
        if form.is_valid():
            nouvelle_ech = form.cleaned_data['nouvelle_echeance']
            if nouvelle_ech <= bc.date_echeance:
                form.add_error('nouvelle_echeance',
                               "La nouvelle échéance doit être postérieure à l'échéance actuelle.")
            else:
                prolong = form.save(commit=False)
                prolong.bon_commande = bc
                prolong.ancienne_echeance = bc.date_echeance
                prolong.created_by = request.user
                prolong.save()
                log_action(
                    request.user, 'BC.prolong',
                    f"Prolongation {bc.numero} : {prolong.ancienne_echeance} → "
                    f"{prolong.nouvelle_echeance} ({prolong.duree_prolongation_jours} j) — "
                    f"{prolong.motif}",
                    'bc', bc.pk,
                )
                messages.success(
                    request,
                    f"BC {bc.numero} prolongé jusqu'au "
                    f"{prolong.nouvelle_echeance.strftime('%d/%m/%Y')}.",
                )
                return redirect('bc_list')
    else:
        form = ProlongationBCForm()

    return render(request, 'core/bc_prolonger.html', {
        'form': form,
        'bc': bc,
        'prolongations': bc.prolongations.select_related('created_by').order_by('-created_at'),
    })


# ============ JOURNAL DE PROGRAMMATION (JP-BC) ============

# Correspondances entre la nomenclature du journal et celle de la DA
_JP_NATURE_VERS_DA = {'APPRO': 'APPRO', 'TRAVAUX': 'Trx', 'PRESTATION_INT': 'Prestat.Int'}
_JP_PERIODE_VERS_DA = {'quad': 'P1', 'penta': 'P2'}


@login_required
def journal_list(request):
    """Journal de programmation par bon de commande de l'exercice actif."""
    exercice = _exercice_courant(request)
    prestations = PrestationProgrammee.objects.none()
    stats = {'total': 0, 'programmees': 0, 'en_cours': 0, 'executees': 0,
             'annulees': 0, 'budget_total': 0, 'montant_total': 0}

    periode_f = request.GET.get('periode', '')
    priorite_f = request.GET.get('priorite', '')
    statut_f = request.GET.get('statut', '')

    if exercice:
        prestations = (
            PrestationProgrammee.objects
            .filter(exercice=exercice)
            .select_related('ligne_budgetaire__tache', 'demande_achat')
        )
        base = prestations
        stats = {
            'total':        base.count(),
            'programmees':  base.filter(statut='programmee').count(),
            'en_cours':     base.filter(statut='en_cours').count(),
            'executees':    base.filter(statut='executee').count(),
            'annulees':     base.filter(statut='annulee').count(),
            'budget_total': base.aggregate(t=Sum('budget_previsionnel'))['t'] or 0,
            'montant_total': base.aggregate(t=Sum('montant_ht'))['t'] or 0,
        }
        if periode_f:
            prestations = prestations.filter(periode=periode_f)
        if priorite_f:
            prestations = prestations.filter(priorite=priorite_f)
        if statut_f:
            prestations = prestations.filter(statut=statut_f)

    return render(request, 'core/journal_programmation.html', {
        'exercice': exercice,
        'prestations': prestations,
        'stats': stats,
        'periode_filtre': periode_f,
        'priorite_filtre': priorite_f,
        'statut_filtre': statut_f,
    })


@login_required
@role_required('admin', 'directeur_drh', 'chef_service', 'assistante_drh')
@require_POST
@transaction.atomic
def journal_creer_da(request, pk):
    """Génère une Demande d'Achat pré-remplie depuis une prestation du journal."""
    prestation = get_object_or_404(
        PrestationProgrammee.objects.select_related('ligne_budgetaire__tache', 'exercice'), pk=pk,
    )
    if not prestation.est_disponible:
        messages.error(
            request,
            f"Prestation « {prestation.get_statut_display()} » — elle ne peut plus générer de DA.",
        )
        return redirect('journal_list')
    if not prestation.ligne_budgetaire_id:
        messages.error(
            request,
            "Cette prestation n'est pas reliée à une ligne budgétaire. "
            "Importez l'exercice ou liez-la à une ligne avant de créer la DA.",
        )
        return redirect('journal_list')

    exercice = prestation.exercice
    locked, msg = _check_exercice_non_verrouille(exercice)
    if locked:
        messages.error(request, msg)
        return redirect('journal_list')

    try:
        da = DemandeAchatService.creer(
            ligne_budgetaire=prestation.ligne_budgetaire,
            objet=prestation.objet_prestation[:200],
            montant_estime=prestation.montant_ht,
            utilisateur=request.user,
            exercice=exercice,
            nature_prestation=_JP_NATURE_VERS_DA.get(prestation.nature_prestation, ''),
            periode_engagement=_JP_PERIODE_VERS_DA.get(prestation.periode, ''),
            priorite=prestation.priorite,
        )
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('journal_list')

    prestation.demande_achat = da
    prestation.statut = 'en_cours'
    prestation.save(update_fields=['demande_achat', 'statut', 'updated_at'])
    log_action(
        request.user, 'DA.create',
        f"DA {da.reference} créée depuis le journal de programmation (prestation #{prestation.pk})",
        'da', da.pk,
    )
    messages.success(request, f"DA {da.reference} créée depuis le journal de programmation.")
    return redirect('da_list')


# ─────────────────────────────────────────────────────────────
# Journal de programmation — CRUD admin des prestations
# ─────────────────────────────────────────────────────────────

_PP_NATURES = {'APPRO', 'TRAVAUX', 'PRESTATION_INT'}
_PP_PERIODES = {'quad', 'penta'}
_PP_PRIORITES = {'1', '2'}
_PP_STATUTS = {'programmee', 'en_cours', 'executee', 'annulee'}


def _parse_decimal_fr(raw):
    """Parse un montant tolérant au format FR (espaces, NBSP, virgule). Renvoie Decimal ou None."""
    if raw is None:
        return None
    s = str(raw).strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
    if s == '':
        return None
    try:
        return Decimal(s)
    except (ArithmeticError, ValueError):
        return None


def _prestation_payload(request, exercice):
    """Lit et valide les champs d'une prestation depuis le POST.
    Renvoie (data: dict | None, erreur: str | None)."""
    objet = (request.POST.get('objet_prestation') or '').strip()
    if not objet:
        return None, "L'objet de la prestation est obligatoire."
    montant = _parse_decimal_fr(request.POST.get('montant_ht'))
    if montant is None or montant < 0:
        return None, "Montant HT invalide."
    bp_raw = (request.POST.get('budget_previsionnel') or '').strip()
    budget_prev = _parse_decimal_fr(bp_raw) if bp_raw else None
    if bp_raw and budget_prev is None:
        return None, "Budget prévisionnel invalide."

    nature = request.POST.get('nature_prestation', 'APPRO')
    nature = nature if nature in _PP_NATURES else 'APPRO'
    periode = request.POST.get('periode', 'quad')
    periode = periode if periode in _PP_PERIODES else 'quad'
    priorite = request.POST.get('priorite', '1')
    priorite = priorite if priorite in _PP_PRIORITES else '1'
    statut = request.POST.get('statut', 'programmee')
    statut = statut if statut in _PP_STATUTS else 'programmee'

    code_tache = (request.POST.get('code_tache') or '').strip()
    code_nature = (request.POST.get('code_nature') or '').strip()
    # Lien automatique vers la ligne budgétaire correspondante (si elle existe)
    ligne = None
    if code_tache and code_nature:
        ligne = LigneBudgetaire.objects.filter(
            tache__exercice=exercice, tache__numero=code_tache, code_nature=code_nature,
        ).first()

    data = {
        'code_tache': code_tache,
        'libelle_tache': (request.POST.get('libelle_tache') or '').strip(),
        'code_nature': code_nature,
        'libelle_nature': (request.POST.get('libelle_nature') or '').strip(),
        'objet_prestation': objet,
        'nature_prestation': nature,
        'montant_ht': montant,
        'budget_previsionnel': budget_prev,
        'periode': periode,
        'priorite': priorite,
        'statut': statut,
        'ligne_budgetaire': ligne,
    }
    return data, None


@login_required
@role_required('admin')
@require_POST
def prestation_create(request):
    """Ajoute une prestation au journal de programmation (admin)."""
    exercice = _exercice_courant(request)
    if not exercice:
        messages.error(request, "Aucun exercice actif.")
        return redirect('journal_list')
    locked, msg = _check_exercice_non_verrouille(exercice)
    if locked:
        messages.error(request, msg)
        return redirect('journal_list')
    data, err = _prestation_payload(request, exercice)
    if err:
        messages.error(request, err)
        return redirect('journal_list')
    next_num = (PrestationProgrammee.objects.filter(exercice=exercice)
                .aggregate(m=Max('numero_ligne'))['m'] or 0) + 1
    p = PrestationProgrammee.objects.create(exercice=exercice, numero_ligne=next_num, **data)
    log_action(request.user, 'Journal.create',
               f"Prestation #{p.numero_ligne} ajoutée au journal ({p.objet_prestation[:60]})",
               'prestation', p.pk)
    messages.success(request, f"Prestation #{p.numero_ligne} ajoutée au journal de programmation.")
    return redirect('journal_list')


@login_required
@role_required('admin')
@require_POST
def prestation_edit(request, pk):
    """Modifie une prestation du journal (admin)."""
    prestation = get_object_or_404(PrestationProgrammee, pk=pk)
    locked, msg = _check_exercice_non_verrouille(prestation.exercice)
    if locked:
        messages.error(request, msg)
        return redirect('journal_list')
    data, err = _prestation_payload(request, prestation.exercice)
    if err:
        messages.error(request, err)
        return redirect('journal_list')
    for champ, valeur in data.items():
        setattr(prestation, champ, valeur)
    prestation.save()
    log_action(request.user, 'Journal.update',
               f"Prestation #{prestation.numero_ligne} modifiée",
               'prestation', prestation.pk)
    messages.success(request, f"Prestation #{prestation.numero_ligne} modifiée.")
    return redirect('journal_list')


@login_required
@role_required('admin')
@require_POST
def prestation_delete(request, pk):
    """Supprime une prestation du journal (admin)."""
    prestation = get_object_or_404(PrestationProgrammee, pk=pk)
    locked, msg = _check_exercice_non_verrouille(prestation.exercice)
    if locked:
        messages.error(request, msg)
        return redirect('journal_list')
    num = prestation.numero_ligne
    log_action(request.user, 'Journal.delete',
               f"Prestation #{num} supprimée du journal",
               'prestation', prestation.pk)
    prestation.delete()
    messages.success(request, f"Prestation #{num} supprimée du journal de programmation.")
    return redirect('journal_list')
