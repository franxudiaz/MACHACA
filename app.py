import io
import re
import streamlit as st
from pypdf import PdfReader

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

st.set_page_config(page_title="Consolidador M-704", layout="wide")
st.title("📋 Consolidador Oficial M-704 a PDF")
st.write("Extracción directa desde campos oficiales de formulario interactivo.")

def parse_float(val):
    if val is None:
        return 0.0
    val_str = str(val).strip().replace('€', '').strip()
    if not val_str:
        return 0.0
    # Limpiar formato europeo
    if ',' in val_str and '.' in val_str:
        val_str = val_str.replace('.', '').replace(',', '.')
    elif ',' in val_str:
        val_str = val_str.replace(',', '.')
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def get_field_val(fields, key_patterns):
    """Busca un valor en el diccionario de campos coincidiendo con posibles nombres."""
    for key, val in fields.items():
        v = val.get('/V')
        if not v:
            continue
        for pattern in key_patterns:
            if pattern.upper() in key.upper():
                return str(v).strip()
    return ""

def extract_from_acroform(file_bytes, filename):
    extracted_items = []
    reader = PdfReader(io.BytesIO(file_bytes))
    fields = reader.get_fields() or {}

    # 1. Obtener Epígrafe
    epigrafe = get_field_val(fields, ["12.b Nombre", "Justificación", "Epigrafe"])
    if not epigrafe or len(epigrafe) < 3:
        # Respaldo con el nombre del archivo
        name_clean = filename.upper().replace(".PDF", "")
        match_name = re.search(r'([B|C]\d{1,3}[A-Z0-9]*[_\s\w\d]+)', name_clean)
        if match_name:
            epigrafe = match_name.group(1).replace("_", " ").strip()
        else:
            epigrafe = "GENERAL"

    # 2. Extraer filas (del 1 al 15)
    for i in range(1, 16):
        empresa = get_field_val(fields, [f"16 Vendedor{i}", f"Vendedor{i}", f"Codigo{i}", f"16 Codigo{i}"]).upper()
        referencia = get_field_val(fields, [f"17 Referencia{i}", f"Referencia{i}"])
        nomenclatura = get_field_val(fields, [f"18 Nombre{i}", f"Nombre{i}", f"Nomenclatura{i}"])
        
        se_pide_str = get_field_val(fields, [f"25 Se pide{i}", f"Se pide{i}", f"Cantidad{i}"])
        imp_unit_str = get_field_val(fields, [f"26 IMPORTE UNITARIO{i}", f"IMPORTE UNITARIO{i}", f"Unitario{i}"])
        imp_tot_str = get_field_val(fields, [f"27 IMPORTE TOTAL{i}", f"IMPORTE TOTAL{i}", f"Total{i}"])

        imp_tot = parse_float(imp_tot_str)
        se_pide = parse_float(se_pide_str)
        imp_unit = parse_float(imp_unit_str)

        # Si el importe total es mayor que 0 y hay empresa o producto, es una fila válida
        if imp_tot > 0 and (empresa or nomenclatura):
            # En caso de que no tenga empresa explícita en esa fila, usar un genérico
            empresa_final = empresa if empresa else "SIN EMPRESA"
            extracted_items.append({
                "empresa": empresa_final,
                "referencia": referencia if referencia else "-",
                "nomenclatura": nomenclatura,
                "se_pide": se_pide,
                "importe_unitario": imp_unit,
                "importe_total": imp_tot,
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
        with st.spinner("Consolidando pedidos por Empresa y Epígrafe..."):
            for f in uploaded_files:
                items = extract_from_acroform(f.read(), f.name)
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
            st.error("No se encontraron campos de pedido rellenados en los PDF subidos.")
