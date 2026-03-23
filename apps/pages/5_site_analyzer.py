"""Site Analyzer — Analyze development site potential (UC-3)."""

import streamlit as st

st.set_page_config(page_title="Site Analyzer", layout="wide")

st.title("Site Analyzer")
st.caption("UC-3 | Sprint 9")
st.info(
    "Click on a map to select a parcel, then see assemblable parcels, "
    "zoning parameters, constraints, ownership keys (NumeroMatriz), "
    "estimated GBA, and projected return."
)

with st.form("site_form"):
    municipality = st.text_input("Municipality")
    freguesia = st.text_input("Freguesia")
    submitted = st.form_submit_button("Analyze")
    if submitted:
        st.warning("Coming in Sprint 9 — parcel assembly + development economics model required.")
