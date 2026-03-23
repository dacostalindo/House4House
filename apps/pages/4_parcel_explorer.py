"""Parcel Explorer — Kepler.gl map for exploring buildable parcels (UC-3)."""

import streamlit as st
from keplergl import KeplerGl

st.set_page_config(page_title="Parcel Explorer", layout="wide")

st.title("Parcel Explorer")
st.caption("UC-3 | Sprint 9")
st.info(
    "BUPI parcels colored by buildability, SRUP constraint polygons (toggle), "
    "COS land use (toggle), building footprints (toggle), CRUS zoning boundaries."
)

# Render an empty Kepler.gl map to verify the library works.
map_config = KeplerGl(height=600)
map_config.save_to_html(file_name="/tmp/kepler_parcels.html")

with open("/tmp/kepler_parcels.html", "r") as f:
    st.components.v1.html(f.read(), height=620, scrolling=False)
