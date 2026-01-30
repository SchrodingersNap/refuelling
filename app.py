import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- CONFIGURATION ---
# 1. YOUR LIVE GOOGLE SCRIPT URL
SHEET_API_URL = 'https://script.google.com/macros/s/AKfycbxZ4c88cfqMzpm4nGUs5m4cEbp5QtGtNN9lQIIFVLFsMiDFJYb6MYhnN71oNaGUE9m4PQ/exec'

# 2. YOUR GITHUB RAW CSV URL (Replace this with your actual Raw Link)
# Example: 'https://raw.githubusercontent.com/username/repo/main/flight_fuel.csv'
FUEL_DATA_URL = 'https://raw.githubusercontent.com/YOUR_USERNAME/YOUR_REPO/main/flight_fuel.csv' 

REFRESH_RATE = 10 

# --- PAGE CONFIG ---
st.set_page_config(page_title="Refuel Ops", page_icon="⛽", layout="wide") 

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .stApp { background-color: #f0f2f5; }
    .block-container { padding-top: 1rem; padding-bottom: 5rem; }
    
    /* JOB CARD DESIGN */
    .job-card {
        background: white; border-radius: 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.08);
        padding: 0; margin-bottom: 16px;
        border-left: 8px solid #cfd8dc;
        position: relative; overflow: hidden;
    }
    
    /* PRIORITY INDICATORS */
    .priority-critical { border-left-color: #d32f2f !important; }
    .priority-warning { border-left-color: #fbc02d !important; }
    .priority-safe { border-left-color: #388e3c !important; }
    
    .arrow-badge {
        background: #d32f2f; color: white; width: 100%;
        text-align: center; font-weight: 900; font-size: 14px;
        padding: 6px; letter-spacing: 1px;
        animation: pulse 1.5s infinite;
    }
    .warning-badge {
        background: #fbc02d; color: #212121; width: 100%;
        text-align: center; font-weight: 900; font-size: 14px;
        padding: 6px; letter-spacing: 1px;
    }

    /* CARD LAYOUT */
    .card-top {
        background: #ffffff; padding: 12px 16px;
        display: flex; justify-content: space-between; align-items: center;
        border-bottom: 1px solid #f5f5f5;
    }
    .card-main {
        padding: 16px; display: flex; justify-content: space-between; align-items: center;
    }

    /* TAGS */
    .bay-tag { 
        font-size: 20px; font-weight: 900; color: #263238; 
        background: #eceff1; padding: 4px 10px; border-radius: 6px;
    }
    .bowser-tag { 
        font-size: 16px; font-weight: 700; color: #1b5e20; 
        background: #e8f5e9; padding: 4px 12px; border-radius: 20px; 
        border: 1px solid #c8e6c9;
    }

    /* TEXT STYLES */
    .flight-id { font-size: 28px; font-weight: 800; color: #212121; letter-spacing: -1px; }
    .sector-lbl { font-size: 14px; font-weight: 700; color: #546e7a; margin-top: 4px; display: flex; align-items: center; gap: 5px;}
    .dep-time { font-size: 22px; font-weight: 700; color: #424242; }
    .time-sub { font-size: 11px; font-weight: bold; text-align: right; margin-top: -4px;}
    
    .status-red { color: #d32f2f; }
    .status-orange { color: #f57f17; }
    .status-green { color: #388e3c; }

    /* DIVERT */
    .divert-banner {
        background: #fff3e0; color: #e65100; padding: 10px;
        font-weight: bold; font-size: 14px; text-align: center;
        border-bottom: 1px solid #ffe0b2; display: flex; align-items: center; justify-content: center; gap: 8px;
    }

    .stTextInput input { padding: 8px; font-size: 14px; }
    .stButton button { width: 100%; border-radius: 4px; height: 42px; font-weight: bold;}
    
    @keyframes pulse { 0% { opacity: 1; } 50% { opacity: 0.8; } 100% { opacity: 1; } }
    header {visibility: hidden;} footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# --- FUNCTIONS ---
def parse_dep_time(time_str):
    if not time_str: return None
    s = str(time_str).strip()
    now = datetime.now()
    try:
        if len(s) == 3: s = "0" + s
        if len(s) == 4 and s.isdigit(): h, m = int(s[:2]), int(s[2:])
        elif ':' in s: parts = s.split(':'); h, m = int(parts[0]), int(parts[1])
        else: return None
        dep_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if (dep_time - now).total_seconds() < -43200: dep_time = dep_time.replace(day=now.day + 1)
        return dep_time
    except: return None

@st.cache_data(ttl=600) # Cache GitHub CSV for 10 mins (it changes rarely)
def fetch_static_fuel_data():
    try:
        # Load from GitHub
        # If testing locally without internet, uncomment the next line and comment the read_csv line:
        # return pd.DataFrame({'Flight_ID': ['6E 695'], 'Qty': ['8.5']}) 
        df_fuel = pd.read_csv(FUEL_DATA_URL)
        # Ensure Flight_ID is string and stripped
        df_fuel['Flight_ID'] = df_fuel['Flight_ID'].astype(str).str.strip().str.upper()
        return df_fuel
    except:
        return pd.DataFrame(columns=['Flight_ID', 'Qty'])

@st.cache_data(ttl=5)
def fetch_live_data():
    try:
        response = requests.get(SHEET_API_URL)
        if response.status_code == 200:
            data = response.json()
            rows = []
            list_data = data.get('flights', []) if isinstance(data, dict) else []
            
            for item in list_data:
                d = item['data']
                while len(d) < 11: d.append("") 
                
                # Live Data from Google (No 95% column here, we merge it later)
                # Cols: 0=Flight, 1=Dep, 2=Sector, 3=CallSign, 4=Bay, 5=ETA, 6=Crew, 7=Bowser, 8=Comments, 9=Feedback
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
                    'Field Feedback': str(d[9])
                })
            return pd.DataFrame(rows)
    except:
        return pd.DataFrame()
    return pd.DataFrame()

def send_feedback(flight_no, comment):
    try:
        requests.post(SHEET_API_URL, json={"flight": flight_no, "comment": comment})
        st.toast(f"✅ Sent for {flight_no}")
        time.sleep(1)
        st.rerun()
    except: st.error("Failed")

# --- DATA MERGING ---
df_live = fetch_live_data()
df_fuel = fetch_static_fuel_data()

if not df_live.empty:
    # MERGE: Join Live Data with Static Fuel Data on Flight ID
    # Left join ensures we keep all live flights even if they don't have fuel data
    df_merged = pd.merge(df_live, df_fuel, left_on='Flight', right_on='Flight_ID', how='left')
    
    # Fill NaN Qty with "--"
    df_merged['Qty'] = df_merged['Qty'].fillna("--")
else:
    df_merged = pd.DataFrame()

now = datetime.now()

# --- APP TABS ---
tab_run, tab_master = st.tabs(["🚀 ACTIVE JOBS", "📊 MASTER BOARD"])

# --- TAB 1: MINIMALIST RUNNING BAYS ---
with tab_run:
    # Mobile Layout
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if not df_merged.empty:
            running = df_merged[df_merged['Bowser'].str.strip() != ""].copy()
            
            if running.empty:
                st.info("No active jobs.")
            else:
                running['DepObj'] = running['Dep'].apply(parse_dep_time)
                running['MinsLeft'] = running['DepObj'].apply(lambda x: (x - now).total_seconds() / 60 if x else 9999)
                running = running.sort_values(by='MinsLeft')
                
                for i, row in running.iterrows():
                    mins = row['MinsLeft']
                    
                    # Priority
                    if mins < 20:
                        cls, badge, col, msg = "priority-critical", '<div class="arrow-badge">⬆️ PRIORITY</div>', "status-red", f"DEP IN {int(mins)} MIN"
                    elif mins < 30:
                        cls, badge, col, msg = "priority-warning", '<div class="warning-badge">⚠️ PREPARE</div>', "status-orange", f"{int(mins)} MIN LEFT"
                    else:
                        cls, badge, col, msg = "priority-safe", "", "status-green", "ON TIME"

                    # Divert
                    is_divert = "DIVERT" in str(row['Comment']).upper()
                    div_html = f'<div class="divert-banner">⚠️ {row["Comment"]}</div>' if is_divert else ""
                    if is_divert: cls = "priority-critical"

                    # CARD (Flight, Bay, Sector, Dep, Divert - NO 95%, NO Crew)
                    st.markdown(f"""
                    <div class="job-card {cls}">
                        {badge}
                        <div class="card-top">
                            <span class="bay-tag">BAY {row['Bay']}</span>
                            <span class="bowser-tag">🚛 {row['Bowser']}</span>
                        </div>
                        {div_html}
                        <div class="card-main">
                            <div>
                                <div style="font-size:10px; color:#999; font-weight:bold;">FLIGHT</div>
                                <div class="flight-id">{row['Flight']}</div>
                                <div class="sector-lbl">📍 {row['Sector']}</div>
                            </div>
                            <div style="text-align:right;">
                                <div style="font-size:10px; color:#999; font-weight:bold;">DEPARTURE</div>
                                <div class="dep-time">{row['Dep']}</div>
                                <div class="time-sub {col}">{msg}</div>
                            </div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Feedback Input
                    ca, cb = st.columns([3, 1])
                    with ca: val = st.text_input("Report", placeholder="Issue...", key=f"in_{row['Flight']}", label_visibility="collapsed")
                    with cb: 
                        if st.button("Send", key=f"btn_{row['Flight']}"): 
                            if val: send_feedback(row['Flight'], val)
                    st.markdown("---")

# --- TAB 2: MASTER BOARD (FULL DATA) ---
with tab_master:
    if not df_merged.empty:
        # Reorder columns to show Qty near Flight
        cols_order = ['Flight', 'Qty', 'Dep', 'Sector', 'Bay', 'Bowser', 'Call Sign', 'ETA', 'Crew', 'Comment', 'Field Feedback']
        
        # Rename Qty to 95% for display
        df_display = df_merged.rename(columns={'Qty': '95th %'})
        
        # Select valid columns
        final_cols = [c for c in cols_order if c in df_display.columns or c == '95th %']
        
        st.dataframe(df_display[final_cols], hide_index=True, use_container_width=True, height=700)

time.sleep(REFRESH_RATE)
st.rerun()
