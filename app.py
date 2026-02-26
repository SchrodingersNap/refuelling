import streamlit as st
import pandas as pd
import requests
import re
import os

# --- CONFIGURATION ---
# 1. LIVE DATA (Google Sheet API)
SHEET_API_URL = 'https://script.google.com/macros/s/AKfycbzbBOdm442zsjhvkiV6wuX-ZdSWtxaDtxrIRenROtaoYoBAz8ApbnNj916zIpRrnYWe/exec'

# 2. STATIC DATA (Local File)
FUEL_FILE = 'flight_fuel.csv'

# Set layout to wide to use the full screen
st.set_page_config(page_title="Refuel Ops Dashboard", page_icon="⛽", layout="wide") 

# --- CSS FOR CLEAN FULL-SCREEN LAYOUT ---
st.markdown("""
<style>
    .stApp { background-color: #f8f9fa; }
    header {visibility: hidden;} 
    footer {visibility: hidden;}
    /* Pushes the content to the very edges of the screen */
    .block-container { 
        padding-top: 0rem; 
        padding-bottom: 0rem; 
        padding-left: 1rem; 
        padding-right: 1rem;
        max-width: 100%;
    }
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
        
        # Calculate Load (90th Percentile)
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
# (Title removed as requested)

# 1. Fetch Data
df_live = fetch_live_data()
df_stats = fetch_and_calculate_fuel_stats()

if not df_live.empty:
    # 2. Merge Live Data with Recommended Load
    df_live['JoinKey'] = df_live['Flight'].apply(normalize_flight_id)
    df_merged = pd.merge(df_live, df_stats[['JoinKey', 'Qty']], on='JoinKey', how='left')
    
    # 3. Rename columns to match your exact layout requests
    df_merged.rename(columns={
        'Qty': 'Load', 
        'Sector': 'Des', 
        'Call Sign': 'Sign'
    }, inplace=True)
    
    df_merged['Load'] = df_merged['Load'].fillna("--")
    
    # Filter empty rows (where Flight is blank)
    df_merged = df_merged[df_merged['Flight'] != ""]

    # 4. Separate "Done" flights from "Active" flights using FieldFeedback
    is_done = df_merged['FieldFeedback'].str.strip().str.lower() == 'done'
    
    df_refuelled = df_merged[is_done].copy()
    df_active = df_merged[~is_done].copy()

    # 5. Exact column order and visibility (ETA and FieldFeedback are hidden)
    display_cols = ['Flight', 'Load', 'Dep', 'Des', 'Sign', 'Bay', 'Crew', 'Bowser', 'Comment']

    # --- UI PRESENTATION ---
    tab_active, tab_refuelled = st.tabs(["✈️ ACTIVE FLIGHTS", "✅ REFUELLED"])

    with tab_active:
        if not df_active.empty:
            st.dataframe(
                df_active[display_cols],
                hide_index=True,
                use_container_width=True,
                height=700 # Increased height for full screen feel
            )
        else:
            st.info("No active flights at the moment.")

    with tab_refuelled:
        if not df_refuelled.empty:
            st.dataframe(
                df_refuelled[display_cols],
                hide_index=True,
                use_container_width=True,
                height=700
            )
        else:
            st.info("No flights have been marked as 'done' yet.")

else:
    st.warning("Waiting for data from Google Sheets...")

# --- SAFE REFRESH ---
st.markdown("---") # Adds a subtle line before the button
if st.button("🔄 Refresh Data"):
    st.rerun()
