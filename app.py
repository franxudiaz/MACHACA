import io
import re
import pdfplumber
import streamlit as st

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(page_title="Consolidador M-704", layout="wide")
st.title("📋 Consolidador Oficial M-704 a PDF")
st.write("Extracción posicional por coordenadas exactas del formulario oficial.")

def parse_float(val_str):
    if not val_str:
        return 0.0
    val_clean = re.sub(r'[^\d,\.]', '', str(val_str).strip())
    if not val_clean:
        return 0.0
    if ',' in val_clean and '.' in val_clean:
        val_clean = val_clean.replace('.', '').replace(',', '.')
    elif ',' in val_clean:
        val_clean = val_clean.replace(',', '.')
    try:
        return float(val_clean)
    except ValueError:
        return 0.0

def extract_from_pdf(file_bytes, filename):
    extracted_items = []
    epigrafe = "GENERAL"

    # Epígrafe desde el nombre del archivo
    name_clean = filename.upper().replace(".PDF", "")
    match_name = re.search(r'([B|C]\d{1,3}[A-Z0-9]*[_\s\w\d]+)', name_clean)
    if match_name:
        epigrafe = match_name.group(1).replace("_", " ").strip()

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            words = page.extract_words()
            if not words:
                continue

            # Buscar la cabecera 'N. ORD' para fijar el límite vertical de la tabla
            header_y = None
            for w in words:
                if 'ORD' in w['text'].upper():
                    header_y = w['bottom']
                    break
            if not header_y:
                header_y = 190.0

            # Buscar el pie de la tabla ('VALORACIÓN' o 'VOBO')
            footer_y = None
            for w in words:
                if any(k in w['text'].upper() for k in ['VALORACIÓN', 'VALORACION', 'VOBO', 'VºBº']):
                    if w['top'] > header_y:
                        footer_y = w['top']
                        break
            if not footer_y:
                footer_y = 440.0

            # Filtrar las palabras pertenecientes exclusivamente a la zona de datos
            table_words = [w for w in words if (header_y + 12.0) <= w['top'] <= (footer_y - 2.0)]

            # Agrupar las palabras por renglones según su altura (eje Y)
            rows = []
            for w in sorted(table_words, key=lambda x: (x['top'], x['x0'])):
                matched_row = None
                for r in rows:
                    if abs(r['y'] - w['top']) < 7.0:
                        matched_row = r
                        break
                if matched_row:
                    matched_row['words'].append(w)
                else:
                    rows.append({'y': w['top'], 'words': [w]})

            # Clasificar las palabras en columnas según sus coordenadas X
            # Coordenadas calibradas para el ancho estándar del M-704 en horizontal (~842 pt)
            for r in sorted(rows, key=lambda x: x['y']):
                cols = {
                    'ord': [],
                    'codigo': [],
                    'referencia': [],
                    'nomenclatura': [],
                    'se_pide': [],
                    'imp_unit': [],
                    'imp_total': []
                }
                for w in sorted(r['words'], key=lambda x: x['x0']):
                    x = w['x0']
                    if x < 40:
                        cols['ord'].append(w['text'])
                    elif 40 <= x < 115:
                        cols['codigo'].append(w['text'])
                    elif 115 <= x < 210:
                        cols['referencia'].append(w['text'])
                    elif 210 <= x < 575:
                        cols['nomenclatura'].append(w['text'])
                    elif 575 <= x < 655:
                        cols['se_pide'].append(w['text'])
                    elif 655 <= x < 735:
                        cols['imp_unit'].append(w['text'])
                    elif x >= 735:
                        cols['imp_total'].append(w['text'])

                ord_str = " ".join(cols['ord']).strip()
                codigo_str = " ".join(cols['codigo']).strip().upper()
                ref_str = " ".join(cols['referencia']).strip()
                nom_str = " ".join(cols['nomenclatura']).strip()
                pide_str = " ".join(cols['se_pide']).strip()
                unit_str = " ".join(cols['imp_unit']).strip()
                tot_str = " ".join(cols['imp_total']).strip()

                # Ignorar la fila técnica de índices de columna [15, 16, 17, 18...]
                if codigo_str in ['16', 'CÓDIGO', 'CODIGO'] or 'SITUACIÓN' in ref_str.upper() or 'CATÁLOGO' in nom_str.upper():
                    continue

                tot_val = parse_float(tot_str)
                # Si el total viene a 0 o la fila está vacía, se descarta
                if tot_val <= 0.01 or not codigo_str or not nom_str:
                    continue

                se_pide_val = parse_float(pide_str)
                unit_val = parse_float(unit_str)

                extracted_items.append({
                    "empresa": codigo_str,
                    "referencia": ref_str,
                    "nomenclatura": nom_str,
                    "se_pide": se_pide_val,
                    "importe_unitario": unit_val,
                    "importe_total": tot_val,
                    "epigrafe": epigrafe
                })

    return extracted_items

def build_pdf(data_tree: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=30,
        rightMargin=30,
        topMargin=30,
        bottomMargin=30
    )
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle('T1', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, leading=20, textColor=colors.HexColor('#1A365D'))
    epigrafe_style = ParagraphStyle('T2', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=11, leading=15, textColor=colors.HexColor('#2C5282'), spaceAfter=5)
    cell_style = ParagraphStyle('Cell', parent=styles['Normal'], fontName='Helvetica', fontSize=8, leading=10)
    cell_bold = ParagraphStyle('CellB', parent=cell_style, fontName='Helvetica-Bold')

    story = []
    companies = sorted(data_tree.keys())

    for idx_comp, empresa in enumerate(companies):
        story.append(Paragraph(f"EMPRESA: {empresa.upper()}", title_style))
        story.append(Spacer(1, 8))
        empresa_total = 0.0

        for epigrafe, items in data_tree[empresa].items():
            story.append(Paragraph(f"EPÍGRAFE: {epigrafe.upper()}", epigrafe_style))
            table_data = [[
                Paragraph("<b>N. ORD</b>", cell_bold),
                Paragraph("<b>CÓDIGO</b>", cell_bold),
                Paragraph("<b>REFERENCIA</b>", cell_bold),
                Paragraph("<b>NOMENCLATURA</b>", cell_bold),
                Paragraph("<b>SE PIDE</b>", cell_bold),
                Paragraph("<b>IMP. UNIT.</b>", cell_bold),
                Paragraph("<b>IMP. TOTAL</b>", cell_bold)
            ]]

            subtotal_epigrafe = 0.0
            for ord_num, it in enumerate(items, start=1):
                subtotal_epigrafe += it["importe_total"]
                table_data.append([
                    Paragraph(str(ord_num), cell_style),
                    Paragraph(it["empresa"], cell_style),
                    Paragraph(it["referencia"] or "-", cell_style),
                    Paragraph(it["nomenclatura"], cell_style),
                    Paragraph(f"{it['se_pide']:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_style),
                    Paragraph(f"{it['importe_unitario']:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_style),
                    Paragraph(f"{it['importe_total']:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.'), cell_style)
                ])

            empresa_total += subtotal_epigrafe
            subtotal_str = f"{subtotal_epigrafe:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')
            table_data.append([
                Paragraph("<b>SUBTOTAL EPÍGRAFE</b>", cell_bold), "", "", "", "", "",
                Paragraph(f"<b>{subtotal_str}</b>", cell_bold)
            ])

            col_widths = [45, 75, 95, 365, 55, 70, 75]
            t = Table(table_data, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#EDF2F7')),
                ('GRID', (0, 0), (-1, -2), 0.5, colors.HexColor('#CBD5E0')),
                ('SPAN', (0, -1), (5, -1)),
                ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#E2E8F0')),
                ('LINEABOVE', (0, -1), (-1, -1), 1, colors.HexColor('#4A5568')),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(t)
            story.append(Spacer(1, 12))

        total_str = f"{empresa_total:,.2f} €".replace(',', 'X').replace('.', ',').replace('X', '.')
        total_data = [[
            Paragraph(f"<b>TOTAL EMPRESA {empresa.upper()}</b>", cell_bold),
            Paragraph(f"<b>{total_str}</b>", cell_bold)
        ]]
        t_total = Table(total_data, colWidths=[705, 75])
        t_total.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#CBD5E0')),
            ('GRID', (0, 0), (-1, -1), 1, colors.HexColor('#2D3748')),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t_total)

        if idx_comp < len(companies) - 1:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()

uploaded_files = st.file_uploader("Arrastra aquí los archivos PDF del M-704", type=["pdf"], accept_multiple_files=True)

if st.button("Procesar y Compilar PDF", type="primary"):
    if not uploaded_files:
        st.warning("Selecciona al menos un archivo PDF.")
    else:
        data_tree = {}
        with st.spinner("Extrayendo pedidos..."):
            for f in uploaded_files:
                items = extract_from_pdf(f.read(), f.name)
                for it in items:
                    emp = it["empresa"]
                    ep = it["epigrafe"]
                    if emp not in data_tree:
                        data_tree[emp] = {}
                    if ep not in data_tree[emp]:
                        data_tree[emp][ep] = []
                    data_tree[emp][ep].append(it)

        if data_tree:
            pdf_bytes = build_pdf(data_tree)
            st.success("¡Documento compilado con éxito!")
            st.download_button(
                label="📥 Descargar PEDIDOS_CONSOLIDADOS_M704.pdf",
                data=pdf_bytes,
                file_name="PEDIDOS_CONSOLIDADOS_M704.pdf",
                mime="application/pdf"
            )
        else:
            st.error("No se han detectado líneas de pedido válidas en los PDF subidos.")
