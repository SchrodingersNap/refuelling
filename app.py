import streamlit as st
import pandas as pd
import requests
import time
import re
import os

# --- CONFIGURATION ---
# 1. LIVE DATA (Google Sheet API)
SHEET_API_URL = 'https://script.google.com/macros/s/AKfycbzbBOdm442zsjhvkiV6wuX-ZdSWtxaDtxrIRenROtaoYoBAz8ApbnNj916zIpRrnYWe/exec'

# 2. STATIC DATA (Local File)
FUEL_FILE = 'flight_fuel.csv'

REFRESH_RATE = 100 

st.set_page_config(page_title="Refuel Ops Dashboard", page_icon="⛽", layout="wide") 

# --- CSS FOR CLEAN LAYOUT ---
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    header {visibility: hidden;} 
    footer {visibility: hidden;}
    .block-container { padding-top: 2rem; }
</style>
""", unsafe_allow_html=True)

# --- FUNCTIONS ---
def normalize_flight_id(val):
    """Cleans up the flight ID for accurate merging."""
    if not isinstance(val, str): val = str(val)
    val = val.strip().upper()
    match = re.search(r'^(\d)\.?0*E\+?(\d+)$', val)
    if match: val = f"{match.group(1)}E{match.group(2)}"
    return val.replace(" ", "").replace("-", "")

@st.cache_data(ttl=600)
def fetch_and_calculate_fuel_stats():
    """Reads local CSV and calculates the Recommended Load (90th Percentile)"""
    if not os.path.exists(FUEL_FILE):
        return pd.DataFrame(columns=['JoinKey', 'Qty'])
        
    try:
        df_fuel = pd.read_csv(FUEL_FILE, dtype=str)
        df_fuel.columns = df_fuel.columns.str.strip().str.replace(" ", "_")
        
        # Standardize column names just in case
        if 'Flight_ID' not in df_fuel.columns: df_fuel.rename(columns={df_fuel.columns[0]: 'Flight_ID'}, inplace=True)
        if 'Qty' not in df_fuel.columns: df_fuel.rename(columns={df_fuel.columns[1]: 'Qty'}, inplace=True)
        
        df_fuel['JoinKey'] = df_fuel['Flight_ID'].apply(normalize_flight_id)
        df_fuel['Qty'] = pd.to_numeric(df_fuel['Qty'], errors='coerce')
        
        # Calculate Recommended Load (90th Percentile)
        # This reduces excess fuel weight (higher efficiency) while maintaining safety.
        df_agg = df_fuel.groupby('JoinKey')['Qty'].quantile(0.90).reset_index()
        df_agg['Qty'] = df_agg['Qty'].round(2)
        
        return df_agg
    except Exception as e: 
        st.error(f"Error processing fuel file: {e}")
        return pd.DataFrame(columns=['JoinKey', 'Qty'])

@st.cache_data(ttl=5)
def fetch_live_data():
    """Fetches live data from the Google Sheets API"""
    try:
        response = requests.get(SHEET_API_URL)
        if response.status_code == 200:
            data = response.json()
            rows = []
            list_data = data.get('flights', []) if isinstance(data, dict) else []
            
            for item in list_data:
                d = item['data']
                while len(d) < 11: d.append("") 
                
                rows.append({
                    'Flight': str(d[0]).strip().upper(), 
                    'Dep': str(d[1]), 
                    'Sector': str(d[2]), 
                    'Call Sign': str(d[3]), 
                    'Bay': str(d[4]), 
                    'ETA': str(d[5]), 
                    'Crew': str(d[6]), 
                    'Bowser': str(d[7]), 
                    'Comment': str(d[8]), 
                    'FieldFeedback': str(d[9]),
                    'Status': str(d[10]) 
                })
            return pd.DataFrame(rows)
    except Exception as e:
        pass
    return pd.DataFrame()

# --- MAIN APPLICATION ---
st.title("⛽ Refuel Operations Dashboard")

# 1. Fetch Data
df_live = fetch_live_data()
df_stats = fetch_and_calculate_fuel_stats()

if not df_live.empty:
    # 2. Merge Live Data with Recommended Load
    df_live['JoinKey'] = df_live['Flight'].apply(normalize_flight_id)
    df_merged = pd.merge(df_live, df_stats[['JoinKey', 'Qty']], on='JoinKey', how='left')
    df_merged.rename(columns={'Qty': 'Recommended Load'}, inplace=True)
    df_merged['Recommended Load'] = df_merged['Recommended Load'].fillna("--")
    
    # 3. Filter empty rows (where Flight is blank) to keep the table clean
    df_merged = df_merged[df_merged['Flight'] != ""]

    # 4. Separate "Done" flights from "Active" flights
    # We check if the 'FieldFeedback' column contains the word 'done' (case-insensitive)
    is_done = df_merged['FieldFeedback'].str.strip().str.lower() == 'done'
    
    df_refuelled = df_merged[is_done].copy()
    df_active = df_merged[~is_done].copy()

    # Columns we want to display to the user
    display_cols = ['Flight', 'Recommended Load', 'Dep', 'Sector', 'Bay', 'Bowser', 'Call Sign', 'ETA', 'Crew', 'Comment', 'FieldFeedback']

    # --- UI PRESENTATION ---
    tab_active, tab_refuelled = st.tabs(["✈️ ACTIVE FLIGHTS", "✅ REFUELLED"])

    with tab_active:
        if not df_active.empty:
            st.dataframe(
                df_active[display_cols],
                hide_index=True,
                use_container_width=True,
                height=600
            )
        else:
            st.info("No active flights at the moment.")

    with tab_refuelled:
        if not df_refuelled.empty:
            st.dataframe(
                df_refuelled[display_cols],
                hide_index=True,
                use_container_width=True,
                height=600
            )
        else:
            st.info("No flights have been marked as 'done' yet.")

else:
    st.warning("Waiting for data from Google Sheets...")

# Auto-refresh loop
time.sleep(REFRESH_RATE)
st.rerun()
