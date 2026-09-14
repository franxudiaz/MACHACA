import io
import pdfplumber
import streamlit as st

st.set_page_config(page_title="Diagnóstico M-704", layout="wide")
st.title("🔍 Diagnóstico de Lectura M-704")

uploaded_file = st.file_uploader("Sube un solo PDF para ver su texto interno", type=["pdf"])

if uploaded_file:
    with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
        st.subheader("1. Líneas de texto extraídas (extract_text)")
        page = pdf.pages[0]
        text = page.extract_text(layout=False) or ""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        
        st.write(f"Total líneas detectadas: {len(lines)}")
        st.text_area("Texto completo tal cual lo lee Python:", "\n".join(lines), height=300)

        st.subheader("2. Tablas detectadas (extract_tables)")
        tables = page.extract_tables()
        if tables:
            st.json(tables)
        else:
            st.warning("No se detectaron tablas nativas con extract_tables().")
