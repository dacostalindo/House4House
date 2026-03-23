"""Investment Map — Kepler.gl visualization of investment opportunities (UC-1)."""

import streamlit as st
from keplergl import KeplerGl

st.set_page_config(page_title="Investment Map", layout="wide")

st.title("Investment Map")
st.caption("UC-1 | Sprint 6")
st.info("Listing points colored by valuation gap, neighbourhood trajectory polygons, infrastructure catalysts.")

# Render an empty Kepler.gl map to verify the library works.
map_config = KeplerGl(height=600)
map_config.save_to_html(file_name="/tmp/kepler_investment.html")

with open("/tmp/kepler_investment.html", "r") as f:
    st.components.v1.html(f.read(), height=620, scrolling=False)
