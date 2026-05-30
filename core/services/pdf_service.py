"""Generation PDF officielle — Bons de Commande et Bilans budgétaires (ReportLab)."""

from io import BytesIO
from decimal import Decimal
from datetime import date

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, KeepTogether, HRFlowable,
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER

from ..models import BonCommande


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


def generer_pdf_bon_commande(bc: BonCommande) -> bytes:
    """
    Genere le PDF officiel d'un bon de commande sur UNE SEULE PAGE et renvoie les octets.
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

    # === En-tete ===
    story.append(Paragraph("PORT AUTONOME DE DOUALA", styles['title']))
    story.append(Paragraph(bc.direction, styles['subtitle']))
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

    # ── En-tête bilingue ──────────────────────────────────────────────────
    header_data = [[
        Paragraph(
            "<b>REPUBLIQUE DU CAMEROUN</b><br/>"
            "Paix - Travail - Patrie<br/>"
            "----------<br/>"
            "<b>PORT AUTONOME DE DOUALA</b><br/>(P.A.D.)",
            styles['header_left'],
        ),
        Paragraph(
            f"<b>BILAN BUDGÉTAIRE</b><br/>"
            f"<font size='10'>Exercice {exercice.annee} — DRH</font>",
            styles['header_center'],
        ),
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
