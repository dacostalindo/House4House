"""Property Valuator — Predict fair value for any listing (UC-1)."""

import streamlit as st

st.set_page_config(page_title="Property Valuator", layout="wide")

st.title("Property Valuator")
st.caption("UC-1 | Sprint 6")
st.info("Enter an address or listing URL to get a predicted value, valuation gap, comparable sales, and neighbourhood stats.")

with st.form("valuator_form"):
    address = st.text_input("Address or listing URL")
    submitted = st.form_submit_button("Evaluate")
    if submitted:
        st.warning("Coming in Sprint 6 — hedonic model + valuation pipeline required.")
