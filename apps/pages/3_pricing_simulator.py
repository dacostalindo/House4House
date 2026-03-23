"""Pricing Simulator — Recommend unit pricing for developments (UC-2)."""

import streamlit as st

st.set_page_config(page_title="Pricing Simulator", layout="wide")

st.title("Pricing Simulator")
st.caption("UC-2 | Sprint 8")
st.info("Select a development project, adjust unit attributes, and see recommended price, margin, and absorption forecast.")

with st.form("pricing_form"):
    project = st.text_input("Development project name")
    typology = st.selectbox("Typology", ["T0", "T1", "T2", "T3", "T4+"])
    floor = st.number_input("Floor", min_value=0, max_value=30, value=1)
    area = st.number_input("Area (m2)", min_value=20.0, max_value=500.0, value=80.0)
    submitted = st.form_submit_button("Simulate")
    if submitted:
        st.warning("Coming in Sprint 8 — pricing model + competitive developments data required.")
