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
st.write("Procesamiento por extracción de texto estructurado directo (sin APIs).")

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

    # 1. Epígrafe desde el nombre del archivo
    name_clean = filename.upper().replace(".PDF", "")
    match_name = re.search(r'([B|C]\d{1,3}[A-Z0-9]*[_\s\w\d]+)', name_clean)
    if match_name:
        epigrafe = match_name.group(1).replace("_", " ").strip()

    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        full_text = ""
        for page in pdf.pages:
            t = page.extract_text(layout=False) or ""
            full_text += "\n" + t

        # 2. Epígrafe alternativo desde el texto
        if "Justificación" in full_text or "B." in full_text or "C." in full_text:
            match_ep = re.search(r'([B|C]\.\d+[^;\n\r]+)', full_text)
            if match_ep:
                ep_candidato = match_ep.group(1).split("Forma de")[0].strip()
                if len(ep_candidato) > 4:
                    epigrafe = ep_candidato

        # 3. Extracción línea por línea analizando importes finales en €
        # Patrón típico de una fila: N_ORD EMPRESA REFERENCIA NOMENCLATURA CANTIDAD IMP_UNIT IMP_TOTAL
        lines = full_text.split('\n')
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue

            # Detecta filas que comiencen por número (1-15) y terminen con importe en € o dígitos
            # Ej: "1 TTECH 88378040BLUE PANTALON DE TRABAJO 2,00 45,60 € 91,20 €"
            m = re.match(r'^([1-9]|1[0-5])\s+([A-Z0-9_-]+)\s+(.+?)\s+([\d,\.]+)\s+([\d,\.]+\s*€?)\s+([\d,\.]+\s*€?)$', line_str)
            if m:
                n_ord = m.group(1)
                empresa = m.group(2).upper()
                resto_texto = m.group(3).strip()
                se_pide = parse_float(m.group(4))
                imp_unit = parse_float(m.group(5))
                imp_total = parse_float(m.group(6))

                # Separar referencia (primera palabra/código) de la nomenclatura
                partes = resto_texto.split(" ", 1)
                referencia = partes[0] if len(partes) > 1 else "-"
                nomenclatura = partes[1] if len(partes) > 1 else resto_texto

                if imp_total > 0:
                    extracted_items.append({
                        "empresa": empresa,
                        "referencia": referencia,
                        "nomenclatura": nomenclatura,
                        "se_pide": se_pide,
                        "importe_unitario": imp_unit,
                        "importe_total": imp_total,
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
                    Paragraph(it["referencia"], cell_style),
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
            st.error("No se han detectado líneas de pedido válidas en los PDF subidos. Comprueba si los PDF son texto seleccionable o imágenes escaneadas.")
