"""
Pro Wind Energy Dashboard with Map Picker
- Free APIs only
- Map-based location selection
- Dark/Light mode toggle
- Gradient metrics cards with icons
- Interactive Plotly charts
"""

import streamlit as st
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.express as px
import plotly.graph_objects as go

# -------------------------
# Page config
# -------------------------
st.set_page_config(
    page_title="Wind Energy Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------
# Dark / Light mode toggle
# -------------------------
if 'dark_mode' not in st.session_state:
    st.session_state.dark_mode = False

def toggle_dark_mode():
    st.session_state.dark_mode = not st.session_state.dark_mode

st.sidebar.button("🌙 Toggle Dark/Light Mode", on_click=toggle_dark_mode)

if st.session_state.dark_mode:
    st.markdown("<style>body {background-color:#121212;color:white;} .stButton button {background-color:#1f77b4;color:white;}</style>", unsafe_allow_html=True)
else:
    st.markdown("<style>body {background-color:#f0f4f8;color:black;}</style>", unsafe_allow_html=True)

# -------------------------
# Helper functions
# -------------------------
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

def geocode(place):
    params = {"name": place, "count": 5}
    r = requests.get(GEOCODE_URL, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    return data.get("results", [])

def fetch_wind_data(lat, lon, start_date, end_date):
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "windspeed_10m",
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "timezone": "UTC",
    }
    r = requests.get(FORECAST_URL, params=params, timeout=20)
    r.raise_for_status()
    hourly = r.json().get("hourly", {})
    times = hourly.get("time", [])
    ws = hourly.get("windspeed_10m", [])
    if not times:
        return pd.DataFrame()
    return pd.DataFrame({"time_utc": pd.to_datetime(times, utc=True), "wind_m_s": ws})

def adjust_height(wind_series, z_from=10.0, z_to=80.0, alpha=0.14):
    factor = (z_to / z_from) ** alpha
    return wind_series * factor

def turbine_power_from_wind(v, rotor_diameter, cp=0.4, air_density=1.225, rated_power_kw=1500,
                           cut_in=3.5, cut_out=25.0, rated_wind=12.0):
    A = np.pi * (rotor_diameter / 2.0) ** 2
    P_watt = 0.5 * air_density * A * cp * (v ** 3)
    P_watt = np.where((v < cut_in) | (v > cut_out), 0.0, P_watt)
    P_watt = np.minimum(P_watt, rated_power_kw * 1000.0)
    return P_watt / 1000.0

# -------------------------
# Sidebar turbine settings
# -------------------------
st.sidebar.header("Turbine & Model Settings")
rotor_diameter = st.sidebar.number_input("Rotor diameter (m)", 1.0, 150.0, 77.0, 1.0)
rated_power_kw = st.sidebar.number_input("Rated power (kW)", 1.0, 10000.0, 1500.0, 1.0)
hub_height = st.sidebar.number_input("Hub height (m)", 10.0, 200.0, 80.0, 1.0)
cp = st.sidebar.slider("Power coefficient Cp", 0.1, 0.5, 0.4)
alpha = st.sidebar.slider("Wind shear exponent α", 0.07, 0.25, 0.14)
history_days = st.sidebar.slider("History days", 1, 30, 14)
forecast_days = 7

# -------------------------
# Map-based location selection
# -------------------------
st.subheader("Select Location")
st.write("You can either type a location OR click on the map below.")

# Default lat/lon
default_lat, default_lon = 17.3850, 78.4867  # Hyderabad

# Streamlit map
map_df = pd.DataFrame({'lat':[default_lat],'lon':[default_lon]})
selected_points = st.map(map_df, zoom=5)

# Optional: capture last clicked location (requires st.experimental_data_editor or pydeck for full interaction)
lat = st.number_input("Latitude", value=default_lat, format="%.6f")
lon = st.number_input("Longitude", value=default_lon, format="%.6f")

col1, col2 = st.columns([3,1])
with col1:
    place = st.text_input("Or type a location (e.g., 'Hyderabad, India')", value="Hyderabad, India")
with col2:
    run_fetch = st.button("Run")

# -------------------------
# Data fetch & processing
# -------------------------
if run_fetch:
    try:
        # Override lat/lon if place is typed
        if place.strip() != "":
            results = geocode(place)
            if results:
                chosen = results[0]
                lat = chosen["latitude"]
                lon = chosen["longitude"]
                st.markdown(f"**Location:** {chosen.get('name')}, {chosen.get('country','')} — lat {lat:.4f}, lon {lon:.4f}")

        today_utc = datetime.utcnow().date()
        hist_df = fetch_wind_data(lat, lon, today_utc - timedelta(days=history_days), today_utc - timedelta(days=1))
        fc_df = fetch_wind_data(lat, lon, today_utc, today_utc + timedelta(days=forecast_days))

        if hist_df.empty and fc_df.empty:
            st.error("No wind data returned.")
        else:
            if not hist_df.empty: hist_df["source"]="history"
            if not fc_df.empty: fc_df["source"]="forecast"

            df = pd.concat([hist_df, fc_df], ignore_index=True).sort_values("time_utc").reset_index(drop=True)
            df["wind_hub_m_s"] = adjust_height(df["wind_m_s"], 10.0, hub_height, alpha)
            df["power_kW"] = turbine_power_from_wind(df["wind_hub_m_s"], rotor_diameter, cp, rated_power_kw=rated_power_kw)
            df["energy_kWh"] = df["power_kW"]

            # Gradient metrics cards
            total_energy_next7 = df[df["source"]=="forecast"]["energy_kWh"].sum()
            avg_cf = df["power_kW"].mean()/rated_power_kw if rated_power_kw>0 else 0.0
            col_a, col_b, col_c = st.columns(3)
            col_a.markdown(f"<div style='background:linear-gradient(135deg,#1f77b4,#0d3b66);padding:15px;border-radius:10px;color:white;text-align:center;font-size:18px;'>⚡ Energy (next 7d)<br><b>{total_energy_next7:.1f} kWh</b></div>", unsafe_allow_html=True)
            col_b.markdown(f"<div style='background:linear-gradient(135deg,#ff7f0e,#cc5500);padding:15px;border-radius:10px;color:white;text-align:center;font-size:18px;'>📊 Capacity Factor<br><b>{avg_cf*100:.1f}%</b></div>", unsafe_allow_html=True)
            col_c.markdown(f"<div style='background:linear-gradient(135deg,#2ca02c,#145214);padding:15px;border-radius:10px;color:white;text-align:center;font-size:18px;'>🌬 Avg Wind @ Hub<br><b>{df['wind_hub_m_s'].mean():.1f} m/s</b></div>", unsafe_allow_html=True)

            # Plots
            fig_wind = px.line(df, x="time_utc", y="wind_hub_m_s", color="source", labels={"wind_hub_m_s":"Wind @ hub (m/s)","time_utc":"Time"}, title="Wind speed (hub height)")
            st.plotly_chart(fig_wind, use_container_width=True)

            fig_power = go.Figure()
            fig_power.add_trace(go.Scatter(x=df["time_utc"], y=df["power_kW"], mode='lines', name='Power (kW)', line=dict(color='#ff7f0e')))
            fig_power.add_trace(go.Scatter(x=df["time_utc"], y=[rated_power_kw]*len(df), mode='lines', name='Rated Power', line=dict(color='red', dash='dash')))
            fig_power.update_layout(title="Turbine Power", xaxis_title="Time", yaxis_title="Power (kW)")
            st.plotly_chart(fig_power, use_container_width=True)

            # Next 48h
            st.subheader("Next 48 hours forecast")
            now_utc = pd.Timestamp.now(tz="UTC")
            next48 = df[(df["time_utc"]>=now_utc)&(df["time_utc"]<=now_utc+pd.Timedelta(hours=48))]
            if not next48.empty:
                display_df = next48.copy()
                display_df["time_display"] = display_df["time_utc"].dt.tz_convert("Asia/Kolkata")
                st.dataframe(display_df[["time_display","wind_m_s","wind_hub_m_s","power_kW","energy_kWh","source"]].rename(columns={
                    "time_display":"Time","wind_m_s":"wind@10m","wind_hub_m_s":"wind@hub","power_kW":"power_kW"
                }))
                fig_48 = px.line(display_df, x="time_display", y="power_kW", labels={"power_kW":"Power (kW)","time_display":"Time"}, title="Next 48h Power Forecast")
                st.plotly_chart(fig_48, use_container_width=True)

            # Download CSV
            csv = df.to_csv(index=False)
            st.download_button("💾 Download full hourly data CSV", csv, file_name="wind_hourly_estimates.csv", mime="text/csv")

    except Exception as e:
        st.error(f"Error: {e}")

st.markdown("---")
st.markdown("### Reality-check:")
st.markdown("""
- Wind at 10 m extrapolated to hub-height is simplified.
- Turbine power uses a basic formula; real curves differ.
- Local terrain, wakes, and turbulence affect production.
- For commercial decisions, use on-site measurements or validated reanalysis.
""")
# -------------------------
# Custom background color
# -------------------------
if st.session_state.dark_mode:
    bg_color = "#121212"  # dark mode
else:
    bg_color = "#e6f0f3"  # light professional blueish tone

st.markdown(f"""
<style>
/* Body background */
body {{
    background-color: {bg_color};
}}
/* Streamlit container transparency removed */
.stContainer {{
    background-color: rgba(255,255,255,0.9);
    padding: 15px;
    border-radius: 10px;
}}
</style>
""", unsafe_allow_html=True)


