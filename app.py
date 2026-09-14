import io
import streamlit as st
import pdfplumber
from pypdf import PdfReader

st.set_page_config(page_title="Diagnóstico Campos M-704", layout="wide")
st.title("🔍 Diagnóstico de Campos de Formulario M-704")

uploaded_file = st.file_uploader("Sube el PDF 001C...", type=["pdf"])

if uploaded_file:
    file_bytes = uploaded_file.read()
    
    # 1. Inspeccionar Form Fields con pypdf
    reader = PdfReader(io.BytesIO(file_bytes))
    fields = reader.get_fields()
    
    st.subheader("1. Campos interactivos detectados (AcroForm / Form Fields)")
    if fields:
        st.success(f"¡Se han detectado {len(fields)} campos de formulario!")
        # Mostrar los campos que tienen valor
        filled_fields = {k: v.get('/V') for k, v in fields.items() if v.get('/V')}
        st.json(filled_fields)
    else:
        st.warning("No se detectaron campos AcroForm con pypdf.")

    # 2. Inspeccionar Anotaciones
    st.subheader("2. Anotaciones de página")
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        annots = pdf.pages[0].annots
        if annots:
            st.success(f"Detectadas {len(annots)} anotaciones.")
            st.json(annots[:10])
        else:
            st.info("No hay anotaciones.")
