"""Generation PDF officielle — Bons de Commande et Bilans budgétaires (ReportLab)."""

import os
from io import BytesIO
from decimal import Decimal
from datetime import date

from django.conf import settings
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable, Image,
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

from ..models import BonCommande


def _logo_pad(width_mm: float = 28):
    """Retourne le logo officiel PAD prêt à embarquer dans un Story ReportLab, ou None."""
    path = os.path.join(settings.BASE_DIR, 'static', 'img', 'logo_pad.png')
    if not os.path.exists(path):
        return None
    img = Image(path)
    # Conserve le ratio en fixant la largeur
    ratio = img.drawHeight / img.drawWidth
    img.drawWidth = width_mm * mm
    img.drawHeight = width_mm * mm * ratio
    return img


PAD_GREEN = colors.HexColor('#1A5632')
PAD_BLUE = colors.HexColor('#1B3A5C')


def _fmt_money(value):
    """Formate un Decimal en '1 234 567 FCFA'."""
    return f"{value:,.0f}".replace(',', ' ') + " FCFA"


def _styles():
    base = getSampleStyleSheet()
    return {
        'title': ParagraphStyle(
            'title', parent=base['Heading1'],
            fontSize=18, textColor=PAD_GREEN, alignment=TA_CENTER,
            spaceAfter=12, fontName='Helvetica-Bold',
        ),
        'subtitle': ParagraphStyle(
            'subtitle', parent=base['Normal'],
            fontSize=10, textColor=colors.grey, alignment=TA_CENTER, spaceAfter=18,
        ),
        'h2': ParagraphStyle(
            'h2', parent=base['Heading2'],
            fontSize=10, textColor=PAD_BLUE, fontName='Helvetica-Bold',
            spaceBefore=5, spaceAfter=3,
        ),
        'normal': ParagraphStyle(
            'normal', parent=base['Normal'], fontSize=9, leading=12,
        ),
        'small': ParagraphStyle(
            'small', parent=base['Normal'], fontSize=8,
            textColor=colors.grey, leading=10,
        ),
        'right_bold': ParagraphStyle(
            'right_bold', parent=base['Normal'],
            fontSize=10, alignment=TA_RIGHT, fontName='Helvetica-Bold',
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Conversion d'un entier en toutes lettres (français) — sans dépendance externe
# ─────────────────────────────────────────────────────────────────────────────

_UNITES = [
    'zéro', 'un', 'deux', 'trois', 'quatre', 'cinq', 'six', 'sept', 'huit', 'neuf',
    'dix', 'onze', 'douze', 'treize', 'quatorze', 'quinze', 'seize',
    'dix-sept', 'dix-huit', 'dix-neuf',
]


def _deux_chiffres(n: int) -> str:
    if n < 20:
        return _UNITES[n]
    d, u = divmod(n, 10)
    bases = {2: 'vingt', 3: 'trente', 4: 'quarante', 5: 'cinquante',
             6: 'soixante', 7: 'soixante', 8: 'quatre-vingt', 9: 'quatre-vingt'}
    base = bases[d]
    if d in (7, 9):
        reste = 10 + u  # 10..19
        if d == 7 and reste == 11:
            return 'soixante et onze'
        return f"{base}-{_UNITES[reste]}"
    if u == 0:
        return 'quatre-vingts' if d == 8 else base
    if u == 1 and d != 8:
        return f"{base} et un"
    return f"{base}-{_UNITES[u]}"


def _trois_chiffres(n: int, plural_ok: bool = True) -> str:
    if n < 100:
        return _deux_chiffres(n)
    h, r = divmod(n, 100)
    cent = 'cent' if h == 1 else f"{_UNITES[h]} cent"
    if r == 0:
        if h > 1 and plural_ok:
            cent += 's'
        return cent
    return f"{cent} {_deux_chiffres(r)}"


def montant_en_lettres(montant) -> str:
    """Convertit un entier en toutes lettres en français (jusqu'aux milliards)."""
    n = int(montant)
    if n == 0:
        return 'zéro'
    parts = []
    milliards, n = divmod(n, 1_000_000_000)
    millions, n = divmod(n, 1_000_000)
    milliers, unites = divmod(n, 1000)
    if milliards:
        parts.append(_trois_chiffres(milliards, False) + (' milliards' if milliards > 1 else ' milliard'))
    if millions:
        parts.append(_trois_chiffres(millions, False) + (' millions' if millions > 1 else ' million'))
    if milliers:
        parts.append('mille' if milliers == 1 else _trois_chiffres(milliers, False) + ' mille')
    if unites:
        parts.append(_trois_chiffres(unites, True))
    return ' '.join(parts)


def _fmt_fcfa(value) -> str:
    """Formate un montant en '1 234 567,00' (style document PAD)."""
    try:
        s = f"{Decimal(str(value)):,.2f}"
    except Exception:
        return str(value)
    return s.replace(',', ' ').replace('.', ',')


def _fmt_qte(value) -> str:
    try:
        return f"{Decimal(str(value)):.2f}".replace('.', ',')
    except Exception:
        return str(value)


def generer_pdf_bon_commande(bc: BonCommande) -> bytes:
    """Génère le PDF d'un bon de commande au format officiel réel du PAD (une page)."""
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=12 * mm,
        title=f"Bon de commande {bc.numero}",
        author='BudgetPAD — PAD/DRH',
    )
    base = getSampleStyleSheet()
    st_center = ParagraphStyle('pc', parent=base['Normal'], fontSize=11, alignment=TA_CENTER,
                               fontName='Helvetica-Bold', textColor=PAD_GREEN, leading=15)
    st_code = ParagraphStyle('pcode', parent=base['Normal'], fontSize=7.5, leading=11)
    st_cell = ParagraphStyle('pcell', parent=base['Normal'], fontSize=8, leading=11)
    st_cell_b = ParagraphStyle('pcellb', parent=base['Normal'], fontSize=8, leading=11, fontName='Helvetica-Bold')
    st_head = ParagraphStyle('phead', parent=base['Normal'], fontSize=8.5, alignment=TA_CENTER,
                             fontName='Helvetica-Bold', textColor=colors.white)
    st_objet = ParagraphStyle('pobj', parent=base['Normal'], fontSize=9, fontName='Helvetica-Bold',
                              textColor=PAD_BLUE, leading=12)
    st_num = ParagraphStyle('pnum', parent=base['Normal'], fontSize=8, alignment=TA_RIGHT, leading=11)
    st_sig = ParagraphStyle('psig', parent=base['Normal'], fontSize=8, alignment=TA_CENTER, leading=11)

    story = []
    da = bc.demande
    p = bc.prestataire
    lignes = list(bc.lignes.all())

    # ── En-tête : logo | titre | code document ──
    logo = _logo_pad(width_mm=24)
    titre = Paragraph(
        "SYSTEME DE MANAGEMENT DE LA QUALITE<br/>ENREGISTREMENT<br/>"
        "<font size='14'>BON DE COMMANDE</font>", st_center)
    code = Paragraph(
        "Code&nbsp;&nbsp;EN-QI A-41<br/>Version&nbsp;&nbsp;00<br/>"
        "Date de création&nbsp;&nbsp;30/09/2014<br/>Page 1 sur 1", st_code)
    header = Table([[logo or Paragraph('PAD', st_cell_b), titre, code]],
                   colWidths=[30 * mm, 110 * mm, 46 * mm])
    header.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (0, 0), (0, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(header)

    # ── 3 colonnes : Demande d'achat | Commande | Destinataire ──
    da_num = da.reference if da else '—'
    da_date = da.created_at.strftime('%d/%m/%Y') if da else '—'
    if da and da.ligne_budgetaire_id:
        tache_num = da.ligne_budgetaire.tache.numero
        nature = da.ligne_budgetaire.code_nature
    else:
        tache_num = bc.tache.numero if bc.tache_id else '—'
        nature = '—'
    da_txt = Paragraph(
        f"<b>N° D.A. :</b> {da_num}<br/><b>Date D.A. :</b> {da_date}<br/>"
        f"<b>Tâche :</b> {tache_num}<br/><b>Nature :</b> {nature}", st_cell)
    bc_date = bc.date_emission.strftime('%d/%m/%Y') if bc.date_emission else '—'
    cmd_txt = Paragraph(
        f"<b>{bc.numero}</b><br/><br/><b>Date :</b> {bc_date}<br/><b>Par :</b> —", st_cell)
    notif = bc.date_notification.strftime('%d/%m/%Y') if bc.date_notification else '—'
    dest_txt = Paragraph(
        f"<b>Code :</b> {p.code}<br/><b>Raison :</b> {p.nom}<br/>"
        f"<b>Adresse :</b> {p.adresse or '—'}<br/><b>Téléphone :</b> {p.telephone or '—'}<br/>"
        f"<b>Notifié le :</b> {notif}", st_cell)
    info = Table(
        [[Paragraph("<b>Demande d'achat</b>", st_cell_b),
          Paragraph("<b>Commande</b>", st_cell_b),
          Paragraph("<b>Destinataire</b>", st_cell_b)],
         [da_txt, cmd_txt, dest_txt]],
        colWidths=[55 * mm, 50 * mm, 81 * mm])
    info.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EAEFF3')),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(info)

    # ── OBJET ──
    objet_txt = (bc.objet or (da.objet if da else '') or '—').upper()
    objet = Table([[Paragraph(f"<b>OBJET :</b> {objet_txt}", st_objet)]], colWidths=[186 * mm])
    objet.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(objet)

    # ── Tableau des articles ──
    rows = [[
        Paragraph("Réf. Art", st_head), Paragraph("Désignation", st_head),
        Paragraph("Unité", st_head), Paragraph("Quantité", st_head),
        Paragraph("P.U.", st_head), Paragraph("MONTANT HT", st_head),
    ]]
    if lignes:
        for l in lignes:
            rows.append([
                Paragraph(l.reference_article or '—', st_cell),
                Paragraph(l.designation, st_cell),
                Paragraph(l.unite, st_cell),
                Paragraph(_fmt_qte(l.quantite), st_num),
                Paragraph(_fmt_fcfa(l.prix_unitaire_ht), st_num),
                Paragraph(_fmt_fcfa(l.montant_ht), st_num),
            ])
    else:
        rows.append([
            Paragraph('—', st_cell), Paragraph(objet_txt.title(), st_cell),
            Paragraph('FT', st_cell), Paragraph('1,00', st_num),
            Paragraph(_fmt_fcfa(bc.montant_ht), st_num), Paragraph(_fmt_fcfa(bc.montant_ht), st_num),
        ])
    for _ in range(max(0, 6 - len(lignes))):
        rows.append(['', '', '', '', '', ''])
    art = Table(rows, colWidths=[24 * mm, 70 * mm, 16 * mm, 22 * mm, 27 * mm, 27 * mm])
    art.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), PAD_BLUE),
        ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#999999')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('TOPPADDING', (0, 0), (-1, -1), 3), ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(art)

    # ── Montant en toutes lettres ──
    lettres = montant_en_lettres(bc.montant_ttc)
    somme = Table([[Paragraph(
        f"Le présent bon de commande est arrêté à la somme de "
        f"<b>{lettres} Francs CFA TTC</b>.", st_cell)]], colWidths=[186 * mm])
    somme.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
        ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(somme)

    # ── Bas : délai/condition/RIB | signature DG/DRH | montants ──
    gauche = Paragraph(
        f"<b>Délai d'exécution à compter de la date de notification :</b> {bc.delai_affichage}<br/><br/>"
        f"<b>Condition de Paiement :</b> {bc.get_condition_paiement_display()}<br/><br/>"
        f"<b>RIB Paiement :</b> {bc.rib_paiement or '—'}", st_cell)
    centre = Paragraph(
        "Pour le Directeur Général<br/>et par Délégation<br/><br/>"
        "<b>Le Directeur des Ressources Humaines</b>", st_sig)
    droite = Paragraph(
        f"<b>Montant Total HT :</b><br/>{_fmt_fcfa(bc.montant_ht)}<br/><br/>"
        f"<b>TVA {bc.taux_tva}% :</b><br/>{_fmt_fcfa(bc.montant_tva)}<br/><br/>"
        f"<b>Montant Total TTC :</b><br/>{_fmt_fcfa(bc.montant_ttc)}", st_num)
    bas = Table([[gauche, centre, droite]], colWidths=[78 * mm, 56 * mm, 52 * mm])
    bas.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 6), ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(bas)

    # ── Signataires ──
    sig = Table([[Paragraph("<b>SIGNATAIRE 1</b>", st_cell), '',
                  Paragraph("<b>SIGNATAIRE 2</b>", st_cell)]],
                colWidths=[78 * mm, 56 * mm, 52 * mm], rowHeights=[22 * mm])
    sig.setStyle(TableStyle([
        ('BOX', (0, 0), (-1, -1), 0.7, colors.black),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4), ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(sig)

    def _footer(canvas, doc_):
        canvas.saveState()
        canvas.setFont('Helvetica', 6.5)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(
            105 * mm, 8 * mm,
            "P.A.D — Siège au Centre des Affaires Maritimes — BP 4020 DOUALA — "
            "Tél: 33 43 35 00 / 33 42 01 33 — www.portdouala-cameroun.com")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _generer_pdf_bc_legacy(bc: BonCommande) -> bytes:
    """
    [LEGACY — conservé pour référence] Ancienne mise en page BC.
    Remplacé par generer_pdf_bon_commande (format réel PAD).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=10 * mm, bottomMargin=14 * mm,
        title=f"Bon de commande {bc.numero}",
        author='BudgetPAD - PAD/DRH',
    )
    styles = _styles()
    story = []

    # === En-tete avec logo officiel PAD ===
    logo = _logo_pad(width_mm=32)
    if logo is not None:
        header_row = Table(
            [[logo, Paragraph("PORT AUTONOME DE DOUALA<br/>"
                              f"<font size='10' color='grey'>{bc.direction}</font>",
                              styles['title'])]],
            colWidths=[40*mm, 140*mm],
        )
        header_row.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, 0), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 0),
            ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ]))
        story.append(header_row)
    else:
        story.append(Paragraph("PORT AUTONOME DE DOUALA", styles['title']))
        story.append(Paragraph(bc.direction, styles['subtitle']))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"<b>BON DE COMMANDE N° {bc.numero}</b>", styles['title']))

    # Bandeau info BC
    info_data = [
        ['Date d\'émission', bc.date_emission.strftime('%d/%m/%Y'),
         'Date de notification', bc.date_notification.strftime('%d/%m/%Y') if bc.date_notification else '—'],
        ['Statut', bc.get_statut_display(),
         'Exercice', str(bc.exercice.annee)],
    ]
    info_table = Table(info_data, colWidths=[35*mm, 50*mm, 35*mm, 50*mm])
    info_table.setStyle(TableStyle([
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('TEXTCOLOR', (2, 0), (2, -1), colors.grey),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('FONTNAME', (3, 0), (3, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('LINEBELOW', (0, 0), (-1, 0), 0.3, colors.lightgrey),
        ('LINEBELOW', (0, 1), (-1, 1), 0.3, colors.lightgrey),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 3 * mm))

    # === Tache et prestataire ===
    story.append(Paragraph("TÂCHE BUDGÉTAIRE", styles['h2']))
    # Imputations : code natures consommées par ce BC
    imputations = list(bc.imputations.select_related('ligne_budgetaire').all())
    natures_str = ' · '.join(
        f"{imp.ligne_budgetaire.code_nature} ({imp.ligne_budgetaire.libelle_nature})"
        for imp in imputations
    ) or '—'
    tache_data = [
        ['Numéro', bc.tache.numero],
        ['Intitulé', bc.tache.titre],
        ['Lignes imputées', natures_str],
    ]
    t = Table(tache_data, colWidths=[40*mm, 130*mm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(t)
    story.append(Spacer(1, 2 * mm))

    story.append(Paragraph("PRESTATAIRE", styles['h2']))
    p = bc.prestataire
    prest_data = [
        ['Code', p.code],
        ['Raison sociale', p.nom],
        ['Adresse', p.adresse or '—'],
        ['Contact', f"{p.telephone or '—'}    {p.email or ''}".strip()],
    ]
    pt = Table(prest_data, colWidths=[40*mm, 130*mm])
    pt.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))
    story.append(pt)
    story.append(Spacer(1, 3 * mm))

    # === Lignes ===
    story.append(Paragraph("DÉTAIL DES ARTICLES / PRESTATIONS", styles['h2']))
    lignes = list(bc.lignes.order_by('ordre'))
    if lignes:
        lignes_data = [['#', 'Désignation', 'Qté', 'P.U. HT', 'Montant HT']]
        for idx, ligne in enumerate(lignes, 1):
            montant = Decimal(ligne.quantite) * ligne.prix_unitaire_ht
            lignes_data.append([
                str(idx),
                Paragraph(ligne.designation, styles['normal']),
                str(ligne.quantite),
                _fmt_money(ligne.prix_unitaire_ht),
                _fmt_money(montant),
            ])
        lt = Table(lignes_data, colWidths=[10*mm, 80*mm, 18*mm, 32*mm, 34*mm])
        lt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), PAD_GREEN),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('ALIGN', (2, 1), (-1, -1), 'RIGHT'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('GRID', (0, 0), (-1, -1), 0.3, colors.lightgrey),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8F8F8')]),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(lt)
    else:
        story.append(Paragraph("<i>Aucune ligne de détail.</i>", styles['normal']))

    story.append(Spacer(1, 3 * mm))

    # === Totaux ===
    totaux_data = [
        ['', 'Total HT', _fmt_money(bc.montant_ht)],
        ['', f'TVA ({bc.taux_tva}%)', _fmt_money(bc.montant_tva)],
        ['', 'Total TTC', _fmt_money(bc.montant_ttc)],
    ]
    tt = Table(totaux_data, colWidths=[80*mm, 50*mm, 44*mm])
    tt.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (1, 0), (-1, 1), 'Helvetica'),
        ('FONTNAME', (1, 2), (-1, 2), 'Helvetica-Bold'),
        ('TEXTCOLOR', (1, 2), (-1, 2), PAD_GREEN),
        ('FONTSIZE', (1, 2), (-1, 2), 12),
        ('LINEABOVE', (1, 2), (-1, 2), 1, PAD_GREEN),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(tt)
    story.append(Spacer(1, 5 * mm))

    # === Signatures ===
    story.append(KeepTogether([
        Paragraph("SIGNATURES", styles['h2']),
        Spacer(1, 2 * mm),
        Table(
            [
                ['Visa Assistante DRH', 'Visa Directeur DRH', 'Visa DAG'],
                ['', '', ''],
                ['Date : ____________', 'Date : ____________', 'Date : ____________'],
            ],
            colWidths=[58*mm, 58*mm, 58*mm], rowHeights=[7*mm, 20*mm, 7*mm],
            style=TableStyle([
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, -1), (-1, -1), 8),
                ('TEXTCOLOR', (0, -1), (-1, -1), colors.grey),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('BOX', (0, 0), (0, -1), 0.5, colors.grey),
                ('BOX', (1, 0), (1, -1), 0.5, colors.grey),
                ('BOX', (2, 0), (2, -1), 0.5, colors.grey),
                ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
            ]),
        ),
    ]))

    # === Pied de page ===
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(18 * mm, 10 * mm,
                          f"BC {bc.numero} - genere par BudgetPAD - Port Autonome de Douala / DRH")
        canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# PDF BILAN BUDGÉTAIRE
# ─────────────────────────────────────────────────────────────────────────────

PAD_ORANGE  = colors.HexColor('#F39C12')
PAD_RED     = colors.HexColor('#E74C3C')
PAD_LGREY   = colors.HexColor('#F4F6F8')
PAD_MGREY   = colors.HexColor('#DEE2E6')


def _bilan_styles():
    base = getSampleStyleSheet()
    return {
        'org': ParagraphStyle(
            'org', parent=base['Normal'],
            fontSize=11, textColor=PAD_BLUE, fontName='Helvetica-Bold',
            alignment=TA_CENTER, spaceAfter=2,
        ),
        'title': ParagraphStyle(
            'btitle', parent=base['Heading1'],
            fontSize=16, textColor=PAD_GREEN, fontName='Helvetica-Bold',
            alignment=TA_CENTER, spaceAfter=4,
        ),
        'subtitle': ParagraphStyle(
            'bsub', parent=base['Normal'],
            fontSize=9, textColor=colors.grey,
            alignment=TA_CENTER, spaceAfter=16,
        ),
        'section': ParagraphStyle(
            'bsect', parent=base['Normal'],
            fontSize=10, textColor=PAD_BLUE, fontName='Helvetica-Bold',
            spaceBefore=12, spaceAfter=6,
        ),
        'normal': ParagraphStyle(
            'bnorm', parent=base['Normal'], fontSize=9, leading=12,
        ),
        'small': ParagraphStyle(
            'bsmall', parent=base['Normal'],
            fontSize=8, textColor=colors.grey, leading=10,
        ),
        'footer': ParagraphStyle(
            'bfoot', parent=base['Normal'],
            fontSize=7, textColor=colors.grey,
        ),
        # ── styles format PAD ──
        'header_left': ParagraphStyle(
            'header_left', parent=base['Normal'],
            fontSize=8, textColor=PAD_BLUE, alignment=TA_LEFT, leading=11,
        ),
        'header_center': ParagraphStyle(
            'header_center', parent=base['Normal'],
            fontSize=13, textColor=PAD_GREEN, alignment=TA_CENTER,
            fontName='Helvetica-Bold', leading=18,
        ),
        'header_right': ParagraphStyle(
            'header_right', parent=base['Normal'],
            fontSize=8, textColor=PAD_BLUE, alignment=TA_RIGHT, leading=11,
        ),
        'banner': ParagraphStyle(
            'banner', parent=base['Normal'],
            fontSize=12, textColor=PAD_BLUE, alignment=TA_CENTER,
            fontName='Helvetica-Bold', leading=16,
        ),
        'tache_title': ParagraphStyle(
            'tache_title', parent=base['Normal'],
            fontSize=9, textColor=PAD_BLUE, fontName='Helvetica-Bold',
            leading=12, spaceAfter=2,
        ),
        'table_head': ParagraphStyle(
            'table_head', parent=base['Normal'],
            fontSize=7, alignment=TA_CENTER, leading=9,
        ),
        'table_cell': ParagraphStyle(
            'table_cell', parent=base['Normal'],
            fontSize=7, alignment=TA_LEFT, leading=9,
        ),
        'table_num': ParagraphStyle(
            'table_num', parent=base['Normal'],
            fontSize=7, alignment=TA_RIGHT, leading=9, fontName='Helvetica',
        ),
        'table_num_bold': ParagraphStyle(
            'table_num_bold', parent=base['Normal'],
            fontSize=7, alignment=TA_RIGHT, leading=9, fontName='Helvetica-Bold',
        ),
        'table_total': ParagraphStyle(
            'table_total', parent=base['Normal'],
            fontSize=7, alignment=TA_LEFT, leading=9, fontName='Helvetica-Bold',
        ),
    }


def _taux_bar(pct: float, width_mm: float = 40) -> Table:
    """Retourne un mini graphe de progression sous forme de table ReportLab."""
    pct = min(max(pct, 0), 100)
    if pct >= 90:
        fill = PAD_RED
    elif pct >= 70:
        fill = PAD_ORANGE
    else:
        fill = PAD_GREEN

    filled = pct / 100 * width_mm * mm
    empty  = (width_mm * mm) - filled

    bar = Table(
        [['', '']],
        colWidths=[filled or 0.01, empty or 0.01],
        rowHeights=[4 * mm],
    )
    bar.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), fill),
        ('BACKGROUND', (1, 0), (1, 0), PAD_MGREY),
        ('TOPPADDING',    (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
        ('LEFTPADDING',   (0, 0), (-1, -1), 0),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 0),
    ]))
    return bar


def generer_pdf_bilan(exercice, taches, consommation, budget_total, solde, taux,
                      bc_statuts, periode: str = 'annuel',
                      date_debut=None, date_fin=None, lignes_par_tache=None) -> bytes:
    """
    Génère le rapport PDF du bilan budgétaire — format officiel PAD.
    A4 paysage, en-tête bilingue, lignes budgétaires détaillées par tâche.

    Args:
        exercice: ExerciceBudgetaire
        taches: liste de Tache (annotées avec with_aggregates)
        lignes_par_tache: dict {tache_pk: [lignes annotées]} ou None
    """
    from reportlab.lib.pagesizes import landscape
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        leftMargin=12 * mm, rightMargin=12 * mm,
        topMargin=10 * mm, bottomMargin=14 * mm,
        title=f"Bilan budgétaire {exercice.annee}",
        author='BudgetPAD — PAD/DRH',
    )
    styles = _bilan_styles()
    story  = []
    lignes_par_tache = lignes_par_tache or {}

    # ── En-tête bilingue avec logo officiel PAD au centre ─────────────────
    logo_center = _logo_pad(width_mm=32) or Paragraph(
        f"<b>BILAN BUDGÉTAIRE</b><br/>"
        f"<font size='10'>Exercice {exercice.annee} — DRH</font>",
        styles['header_center'],
    )
    header_data = [[
        Paragraph(
            "<b>REPUBLIQUE DU CAMEROUN</b><br/>"
            "Paix - Travail - Patrie<br/>"
            "----------<br/>"
            "<b>PORT AUTONOME DE DOUALA</b><br/>(P.A.D.)",
            styles['header_left'],
        ),
        logo_center,
        Paragraph(
            "<b>REPUBLIC OF CAMEROON</b><br/>"
            "Peace - Work - Fatherland<br/>"
            "----------<br/>"
            "<b>PORT AUTHORITY OF DOUALA</b><br/>(P.A.D.)",
            styles['header_right'],
        ),
    ]]
    header_table = Table(header_data, colWidths=[80*mm, 110*mm, 80*mm])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),   # logo centré horizontalement
        ('LEFTPADDING', (1, 0), (1, 0), 0),
        ('RIGHTPADDING', (1, 0), (1, 0), 0),
        ('BOX', (0, 0), (-1, -1), 0, colors.white),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 4 * mm))

    # Titre principal en bandeau bleu pâle
    periode_label = {
        'annuel': 'Annuel', 'trimestriel': 'Trimestriel',
        'mensuel': 'Mensuel', 'personnalise': 'Période personnalisée',
    }.get(periode, periode)
    debut_str = date_debut.strftime('%d/%m/%Y') if date_debut else '—'
    fin_str = date_fin.strftime('%d/%m/%Y') if date_fin else '—'
    titre_data = [[
        Paragraph(
            f"<b>SUIVI DETAILLE DES TACHES — EXERCICE {exercice.annee} — DRH</b><br/>"
            f"<font size='9'>{periode_label} · du {debut_str} au {fin_str}</font>",
            styles['banner'],
        ),
    ]]
    titre_table = Table(titre_data, colWidths=[270*mm])
    titre_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#D5E8F0')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#999999')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    story.append(titre_table)
    story.append(Spacer(1, 4 * mm))

    # ── Détail par tâche : tableau de lignes ──────────────────────────────
    # En-têtes pour le tableau par tâche (8 colonnes)
    header_row = [
        Paragraph("<b>Code nature</b>", styles['table_head']),
        Paragraph("<b>Libellé nature</b>", styles['table_head']),
        Paragraph(f"<b>Budget {exercice.annee}</b>", styles['table_head']),
        Paragraph("<b>Transfert +</b>", styles['table_head']),
        Paragraph("<b>Transfert -</b>", styles['table_head']),
        Paragraph("<b>Consommation</b>", styles['table_head']),
        Paragraph("<b>Solde</b>", styles['table_head']),
        Paragraph("<b>Taux</b>", styles['table_head']),
    ]
    # Largeur totale ~270mm en paysage A4 - marges
    col_widths = [22*mm, 60*mm, 32*mm, 28*mm, 28*mm, 32*mm, 32*mm, 18*mm]

    # Totaux globaux DRH
    total_budget = total_tplus = total_tmoins = total_conso = total_solde = 0.0

    for t in taches:
        # Titre de la tâche
        story.append(Spacer(1, 3 * mm))
        story.append(Paragraph(
            f"<b>TACHE&nbsp;&nbsp;{t.numero}&nbsp;&nbsp;-&nbsp;&nbsp;{t.titre}</b>",
            styles['tache_title'],
        ))

        # Récupère les lignes annotées (depuis le dict ou via with_aggregates())
        lignes = lignes_par_tache.get(t.pk)
        if lignes is None:
            from ..models import LigneBudgetaire
            lignes = list(
                LigneBudgetaire.objects.filter(tache=t, actif=True).with_aggregates()
            )

        # Construction des lignes du tableau
        rows = [header_row]
        sub_budget = sub_tplus = sub_tmoins = sub_conso = sub_solde = 0.0
        for ligne in lignes:
            mi = float(ligne.montant_initial or 0)
            tp = float(getattr(ligne, 'transfert_plus', 0) or 0)
            tm = float(getattr(ligne, 'transfert_moins', 0) or 0)
            co = float(getattr(ligne, 'consommation', 0) or 0)
            so = float(getattr(ligne, 'solde', mi + tp - tm - co) or 0)
            tx = float(getattr(ligne, 'taux_consommation', 0) or 0)
            sub_budget += mi; sub_tplus += tp; sub_tmoins += tm
            sub_conso += co; sub_solde += so
            rows.append([
                Paragraph(ligne.code_nature, styles['table_cell']),
                Paragraph(ligne.libelle_nature, styles['table_cell']),
                Paragraph(_fmt_amount(mi), styles['table_num']),
                Paragraph(_fmt_amount(tp), styles['table_num']),
                Paragraph(_fmt_amount(tm), styles['table_num']),
                Paragraph(_fmt_amount(co), styles['table_num']),
                Paragraph(_fmt_amount(so), styles['table_num']),
                Paragraph(f"{tx:.1f}%", styles['table_num']),
            ])

        # Ligne de total par tâche
        sub_tx = (sub_conso / sub_budget * 100) if sub_budget else 0
        rows.append([
            Paragraph(f"<b>TOTAL TACHE {t.numero}</b>", styles['table_total']),
            '',
            Paragraph(f"<b>{_fmt_amount(sub_budget)}</b>", styles['table_num_bold']),
            Paragraph(f"<b>{_fmt_amount(sub_tplus)}</b>", styles['table_num_bold']),
            Paragraph(f"<b>{_fmt_amount(sub_tmoins)}</b>", styles['table_num_bold']),
            Paragraph(f"<b>{_fmt_amount(sub_conso)}</b>", styles['table_num_bold']),
            Paragraph(f"<b>{_fmt_amount(sub_solde)}</b>", styles['table_num_bold']),
            Paragraph(f"<b>{sub_tx:.1f}%</b>", styles['table_num_bold']),
        ])
        total_budget += sub_budget; total_tplus += sub_tplus
        total_tmoins += sub_tmoins; total_conso += sub_conso; total_solde += sub_solde

        tbl = Table(rows, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#D5E8F0')),
            ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#F0F0F0')),
            ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#999999')),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('SPAN', (0, -1), (1, -1)),  # fusionne les 2 premières colonnes de la ligne TOTAL
        ]))
        story.append(KeepTogether(tbl))

    # ── Total DRH (grand total) ────────────────────────────────────────────
    story.append(Spacer(1, 6 * mm))
    total_tx = (total_conso / total_budget * 100) if total_budget else 0
    grand_total = Table([[
        Paragraph("<b>TOTAL POUR DRH</b>", styles['table_total']),
        '',
        Paragraph(f"<b>{_fmt_amount(total_budget)}</b>", styles['table_num_bold']),
        Paragraph(f"<b>{_fmt_amount(total_tplus)}</b>", styles['table_num_bold']),
        Paragraph(f"<b>{_fmt_amount(total_tmoins)}</b>", styles['table_num_bold']),
        Paragraph(f"<b>{_fmt_amount(total_conso)}</b>", styles['table_num_bold']),
        Paragraph(f"<b>{_fmt_amount(total_solde)}</b>", styles['table_num_bold']),
        Paragraph(f"<b>{total_tx:.1f}%</b>", styles['table_num_bold']),
    ]], colWidths=col_widths)
    grand_total.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#D5E8F0')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#1B3A5C')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('SPAN', (0, 0), (1, 0)),
    ]))
    story.append(grand_total)

    # ── Pied de page ──────────────────────────────────────────────────────
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(12 * mm, 8 * mm,
                          f"Bilan {exercice.annee} ({periode_label}) — généré par BudgetPAD · PAD/DRH")
        canvas.drawRightString(285 * mm, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


def _fmt_amount(value):
    """Formate un montant : 1234567 → 1 234 567 (sans 'FCFA' pour les colonnes serrées)."""
    if value is None:
        return '0'
    try:
        return f"{float(value):,.0f}".replace(',', ' ')
    except (ValueError, TypeError):
        return str(value)
