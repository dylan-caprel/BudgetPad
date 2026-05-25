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
            fontSize=11, textColor=PAD_BLUE, fontName='Helvetica-Bold',
            spaceBefore=10, spaceAfter=6,
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
    Genere le PDF officiel d'un bon de commande et renvoie les octets.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=20 * mm,
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
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('LINEBELOW', (0, 0), (-1, 0), 0.3, colors.lightgrey),
        ('LINEBELOW', (0, 1), (-1, 1), 0.3, colors.lightgrey),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 6 * mm))

    # === Tache et prestataire ===
    story.append(Paragraph("TÂCHE BUDGÉTAIRE", styles['h2']))
    tache_data = [
        ['Numéro', bc.tache.numero],
        ['Intitulé', bc.tache.titre],
        ['Nature', f"{bc.tache.code_nature} — {bc.tache.libelle_nature}"],
    ]
    t = Table(tache_data, colWidths=[40*mm, 130*mm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.grey),
        ('FONTNAME', (1, 0), (1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(t)
    story.append(Spacer(1, 4 * mm))

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
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    story.append(pt)
    story.append(Spacer(1, 6 * mm))

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
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(lt)
    else:
        story.append(Paragraph("<i>Aucune ligne de détail.</i>", styles['normal']))

    story.append(Spacer(1, 4 * mm))

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
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    story.append(tt)
    story.append(Spacer(1, 10 * mm))

    # === Signatures ===
    story.append(KeepTogether([
        Paragraph("SIGNATURES", styles['h2']),
        Spacer(1, 4 * mm),
        Table(
            [
                ['Visa Assistante DRH', 'Visa Directeur DRH', 'Visa DAG'],
                ['', '', ''],
                ['Date : ____________', 'Date : ____________', 'Date : ____________'],
            ],
            colWidths=[58*mm, 58*mm, 58*mm], rowHeights=[8*mm, 25*mm, 8*mm],
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
                      bc_statuts, periode: str = 'annuel') -> bytes:
    """
    Génère le rapport PDF du bilan budgétaire pour un exercice donné.
    Retourne les octets du PDF.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=15 * mm, bottomMargin=20 * mm,
        title=f"Bilan budgétaire {exercice.annee}",
        author='BudgetPAD — PAD/DRH',
    )
    styles = _bilan_styles()
    story  = []

    # ── En-tête ────────────────────────────────────────────────────────────
    story.append(Paragraph("PORT AUTONOME DE DOUALA", styles['org']))
    story.append(Paragraph("Direction des Ressources Humaines", styles['subtitle']))
    story.append(HRFlowable(width='100%', thickness=1, color=PAD_GREEN, spaceAfter=8))
    story.append(Paragraph(f"BILAN BUDGÉTAIRE — EXERCICE {exercice.annee}", styles['title']))
    periode_label = {'annuel': 'Annuel', 'trimestriel': 'Trimestriel', 'mensuel': 'Mensuel'}.get(periode, periode)
    story.append(Paragraph(
        f"Période : {periode_label}  ·  Édité le {date.today().strftime('%d/%m/%Y')}",
        styles['subtitle'],
    ))
    story.append(Spacer(1, 4 * mm))

    # ── KPIs ───────────────────────────────────────────────────────────────
    story.append(Paragraph("SYNTHÈSE GLOBALE", styles['section']))

    def _kpi_cell(label, value, color=PAD_BLUE):
        return [
            Paragraph(f"<font color='grey' size='8'>{label}</font><br/>"
                      f"<font color='{color.hexval()}' size='13'><b>{value}</b></font>",
                      styles['normal']),
        ]

    kpi_data = [[
        _kpi_cell("BUDGET GLOBAL",  _fmt_money(budget_total), PAD_BLUE),
        _kpi_cell("CONSOMMATION",   _fmt_money(consommation), PAD_RED if taux >= 90 else PAD_ORANGE if taux >= 70 else PAD_GREEN),
        _kpi_cell("SOLDE DISPONIBLE", _fmt_money(solde),      PAD_GREEN),
        _kpi_cell("TAUX GLOBAL",    f"{taux} %",              PAD_RED if taux >= 90 else PAD_ORANGE if taux >= 70 else PAD_GREEN),
    ]]
    kpi_table = Table(kpi_data, colWidths=[42*mm, 42*mm, 42*mm, 42*mm])
    kpi_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), PAD_LGREY),
        ('BOX',           (0, 0), (-1, -1), 0.5, PAD_MGREY),
        ('INNERGRID',     (0, 0), (-1, -1), 0.3, PAD_MGREY),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
    ]))
    story.append(kpi_table)
    story.append(Spacer(1, 6 * mm))

    # ── BC par statut ──────────────────────────────────────────────────────
    story.append(Paragraph("BONS DE COMMANDE PAR STATUT", styles['section']))
    bc_meta = [
        ('cree',     'Créé',     '#6c757d'),
        ('notifie',  'Notifié',  '#0dcaf0'),
        ('en_cours', 'En cours', '#0d6efd'),
        ('execute',  'Exécuté',  '#198754'),
        ('annule',   'Annulé',   '#dc3545'),
    ]
    bc_row_data = [['Statut', 'Nombre', 'Proportion']]
    total_bc = sum(bc_statuts.get(k, 0) for k, _, _ in bc_meta)
    for key, lbl, col in bc_meta:
        nb  = bc_statuts.get(key, 0)
        pct = round(nb / total_bc * 100) if total_bc else 0
        bc_row_data.append([
            Paragraph(f"<font color='{col}'>■</font>  {lbl}", styles['normal']),
            str(nb),
            f"{pct} %",
        ])
    bc_row_data.append(['TOTAL', str(total_bc), '100 %'])

    bc_table = Table(bc_row_data, colWidths=[80*mm, 30*mm, 60*mm])
    bc_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0),  (-1, 0),  PAD_BLUE),
        ('TEXTCOLOR',     (0, 0),  (-1, 0),  colors.white),
        ('FONTNAME',      (0, 0),  (-1, 0),  'Helvetica-Bold'),
        ('BACKGROUND',    (0, -1), (-1, -1), PAD_LGREY),
        ('FONTNAME',      (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('ALIGN',         (1, 0),  (-1, -1), 'CENTER'),
        ('FONTSIZE',      (0, 0),  (-1, -1), 9),
        ('GRID',          (0, 0),  (-1, -1), 0.3, PAD_MGREY),
        ('TOPPADDING',    (0, 0),  (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0),  (-1, -1), 5),
        ('LEFTPADDING',   (0, 0),  (0, -1),  8),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, PAD_LGREY]),
    ]))
    story.append(bc_table)
    story.append(Spacer(1, 8 * mm))

    # ── Détail par tâche ───────────────────────────────────────────────────
    story.append(Paragraph("DÉTAIL PAR TÂCHE BUDGÉTAIRE", styles['section']))

    tache_header = [['N°', 'Titre', 'Nature', 'Budget (FCFA)', 'Conso (FCFA)', 'Solde (FCFA)', 'Taux', '']]
    tache_rows   = []
    for t in taches:
        pct  = float(t.taux_consommation)
        flag = '🔴' if pct >= 90 else ('🟠' if pct >= 70 else '🟢')
        tache_rows.append([
            t.numero,
            Paragraph(t.titre[:45] + ('…' if len(t.titre) > 45 else ''), styles['normal']),
            Paragraph(f"<font size='7' color='grey'>{t.libelle_nature or t.code_nature}</font>", styles['normal']),
            _fmt_money(t.budget_ajuste),
            _fmt_money(t.consommation),
            _fmt_money(t.solde),
            f"{pct:.1f} %",
            _taux_bar(pct),
        ])

    tache_data  = tache_header + tache_rows
    col_widths  = [16*mm, 48*mm, 22*mm, 28*mm, 28*mm, 28*mm, 14*mm, 42*mm]
    tache_table = Table(tache_data, colWidths=col_widths, repeatRows=1)
    tache_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0),  (-1, 0),  PAD_GREEN),
        ('TEXTCOLOR',     (0, 0),  (-1, 0),  colors.white),
        ('FONTNAME',      (0, 0),  (-1, 0),  'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0),  (-1, -1), 8),
        ('ALIGN',         (3, 0),  (-1, -1), 'RIGHT'),
        ('ALIGN',         (0, 0),  (0, -1),  'CENTER'),
        ('VALIGN',        (0, 0),  (-1, -1), 'MIDDLE'),
        ('GRID',          (0, 0),  (-1, -1), 0.25, PAD_MGREY),
        ('TOPPADDING',    (0, 0),  (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0),  (-1, -1), 4),
        ('LEFTPADDING',   (0, 0),  (1, -1),  4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PAD_LGREY]),
    ]))
    story.append(tache_table)

    # ── Pied de page ──────────────────────────────────────────────────────
    def _footer(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.grey)
        canvas.drawString(18 * mm, 10 * mm,
                          f"Bilan {exercice.annee} ({periode_label}) — généré par BudgetPAD · PAD/DRH")
        canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
