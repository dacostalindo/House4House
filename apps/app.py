import streamlit as st

st.set_page_config(
    page_title="House4House",
    layout="wide",
)

st.title("House4House Analytics Platform")
st.markdown("Select a tool from the sidebar.")
st.markdown("""
### Available Tools

| Tool | Use Case | Status |
|------|----------|--------|
| **Investment Map** | Kepler.gl map of investment opportunities | Sprint 6 |
| **Property Valuator** | Predict fair value for any listing | Sprint 6 |
| **Pricing Simulator** | Recommend unit pricing for developments | Sprint 8 |
| **Parcel Explorer** | Explore buildable parcels on a map | Sprint 9 |
| **Site Analyzer** | Analyze development site potential | Sprint 9 |
""")
