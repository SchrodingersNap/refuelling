import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta
import re
import time

# --- CONFIGURATION ---
# Paste your Google Script Web App URL here
SHEET_API_URL = 'https://script.google.com/macros/s/AKfycbxZ4c88cfqMzpm4nGUs5m4cEbp5QtGtNN9lQIIFVLFsMiDFJYb6MYhnN71oNaGUE9m4PQ/exec'
REFRESH_RATE = 5  # Seconds between auto-refresh

# --- PAGE SETUP ---
st.set_page_config(
    page_title="Flight Ops Dashboard",
    page_icon="✈️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- CUSTOM CSS FOR CREATIVE CARDS ---
st.markdown("""
<style>
    /* Main Background */
    .stApp { background-color: #f4f6f8; }
    
    /* Remove padding for cleaner look */
    .block-container { padding-top: 2rem; padding-bottom: 2rem; }

    /* CARD STYLES */
    .bay-card {
        background: white; border-radius: 12px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-left: 5px solid #263238;
        margin-bottom: 15px; font-family: sans-serif;
        overflow: hidden;
    }
    
    .card-header {
        padding: 10px 15px; display: flex; justify-content: space-between; align-items: center;
        border-bottom: 1px solid #f0f0f0; background: white;
    }
    
    .bay-badge { 
        font-size: 18px; font-weight: 900; color: #263238;
        background: #eceff1; padding: 4px 8px; border-radius: 6px;
    }
    
    .bowser-pill { 
        background: #e8f5e9; color: #2e7d32; padding: 5px 12px; 
        border-radius: 20px; font-weight: 800; font-size: 14px; 
        border: 1px solid #c8e6c9; display: flex; align-items: center; gap: 5px;
    }

    .card-body { padding: 15px; display: grid; grid-template-columns: 1.5fr 1fr; gap: 10px; }
    
    .label { font-size: 10px; color: #90a4ae; font-weight: 700; text-transform: uppercase; }
    .val { font-size: 15px; font-weight: 600; color: #37474f; }
    .flight-big { font-size: 24px; font-weight: 800; color: #263238; letter-spacing: -0.5px; line-height: 1; }
    
    /* 95% WIDGET */
    .stat-box {
        grid-column: 1 / -1; background: #e3f2fd; border: 1px solid #bbdefb;
        padding: 8px 12px; border-radius: 8px; display: flex; justify-content: space-between; align-items: center;
    }
    .stat-val { font-size: 18px; color: #1565c0; font-weight: 900; }
    
    /* URGENT STYLES */
    .card-urgent { 
        border-left-color: #d32f2f !important;
        box-shadow: 0 0 15px rgba(211, 47, 47, 0.3);
        animation: pulse-red 2s infinite;
    }
    .urgent-banner {
        background: #d32f2f; color: white; font-weight: 900; text-align: center;
        padding: 6px; font-size: 12px; animation: blink 1s infinite alternate;
    }
    .time-urgent { color: #d32f2f; font-weight: 900; font-size: 18px; }

    /* DIVERT STYLES */
    .card-divert { border-left-color: #ff8f00 !important; }
    .card-divert .card-header {
        background: repeating-linear-gradient(45deg, #ffb300, #ffb300 10px, #ffca28 10px, #ffca28 20px);
    }
    .divert-msg {
        grid-column: 1 / -1; background: #fff3e0; color: #e65100; padding: 10px;
        font-weight: bold; font-size: 13px; text-align: center; border-bottom: 1px solid #ffe0b2;
    }

    @keyframes pulse-red { 0% { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0.4); } 70% { box-shadow: 0 0 0 10px rgba(211, 47, 47, 0); } 100% { box-shadow: 0 0 0 0 rgba(211, 47, 47, 0); } }
    @keyframes blink { from { opacity: 1; } to { opacity: 0.7; } }

</style>
""", unsafe_allow_html=True)

# --- HELPER FUNCTIONS ---
def parse_time(time_str):
    """Converts 0815, 815, or ISO strings to datetime objects."""
    if not time_str: return None
    s = str(time_str).strip()
    now = datetime.now()
    try:
        if 'T' in s: return datetime.fromisoformat(s.replace('Z', ''))
        if ':' in s: 
            parts = s.split(':')
            return now.replace(hour=int(parts[0]), minute=int(parts[1]), second=0)
        # Handle 815 -> 0815
        s = s.zfill(4) 
        return now.replace(hour=int(s[:2]), minute=int(s[2:]), second=0)
    except:
        return None

def calculate_effective_time(row, now):
    """Logic: ETA+40 or Dep+Delay Logic"""
    dep = parse_time(row['Dep'])
    eta = parse_time(row['ETA'])
    
    eta_str = str(row['ETA']).upper().strip()
    if eta_str in ['BASE', 'LANDED']:
        return dep, False # Not calculated
    
    if eta:
        return eta + timedelta(minutes=40), True
    
    if dep:
        temp_time = dep
        diff_min = (temp_time - now).total_seconds() / 60
        is_calc = False
        
        while diff_min <= 60 and diff_min > -600:
            temp_time += timedelta(minutes=60)
            diff_min = (temp_time - now).total_seconds() / 60
            is_calc = True
            
        return temp_time, is_calc
        
    return None, False

@st.cache_data(ttl=5)
def fetch_data():
    try:
        response = requests.get(SHEET_API_URL)
        if response.status_code == 200:
            data = response.json()
            
            # --- FIX: Handle if data is List OR Dict ---
            if isinstance(data, dict):
                flight_list = data.get('flights', [])
            elif isinstance(data, list):
                flight_list = data
            else:
                flight_list = []
            
            rows = []
            for item in flight_list:
                # Ensure we handle the structure correctly
                if isinstance(item, dict) and 'data' in item:
                    d = item['data']
                else:
                    # Fallback if item is just a raw list
                    d = item

                # Safety: Ensure d is a list and has enough columns
                if not isinstance(d, list): continue
                
                # Pad with empty strings if missing columns
                while len(d) < 10:
                    d.append("")

               rows.append({'Flight': d[0], 
                    'Dep': d[1], 
                    'Sector': d[2], 
                    # FIX: Force a default value if empty
                    'Percentile': d[3] if str(d[3]).strip() != "" else "--",
                    'CallSign': d[4], 
                    'Bay': d[5], 
                    'ETA': d[6], 
                    'Crew': d[7],
                    'Bowser': d[8], 
                    'Comment': d[9],
                    'OriginalData': item })
            return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Connection Error: {e}")
    return pd.DataFrame()

# --- MAIN APP LOGIC ---

# 1. Load & Process Data
df = fetch_data()

if not df.empty:
    now = datetime.now()
    
    # Calculate Effective Times
    df[['EffectiveTime', 'IsCalculated']] = df.apply(
        lambda row: pd.Series(calculate_effective_time(row, now)), axis=1
    )
    
    # Sort by Effective Time
    df = df.sort_values(by='EffectiveTime', na_position='last').reset_index(drop=True)

    # 2. Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("✈️ Flight Operations")
    with col2:
        st.caption(f"Last Sync: {now.strftime('%H:%M:%S')}")
        if st.button("🔄 Refresh Now"):
            st.rerun()

    # 3. Tabs
    tab_master, tab_running, tab_crew = st.tabs(["📊 Master Board", "🚀 Running Bays", "👥 Crew"])

    # --- TAB 1: MASTER BOARD ---
    with tab_master:
        display_df = df[['Flight', 'Dep', 'Sector', 'Percentile', 'CallSign', 'Bay', 'ETA', 'Crew', 'Bowser', 'Comment']].copy()
        st.dataframe(
            display_df, 
            use_container_width=True,
            hide_index=True,
            height=600
        )

    # --- TAB 2: RUNNING BAYS ---
    with tab_running:
        running_df = df[df['Bowser'].str.strip() != ""]
        
        if running_df.empty:
            st.info("🚛 No Active Bowsers. Assign a Bowser in Excel to see cards here.")
        else:
            cols = st.columns(3)
            
            for index, row in running_df.iterrows():
                with cols[index % 3]:
                    # --- Urgency Logic ---
                    is_urgent = False
                    mins_to_dep = 999
                    if pd.notnull(row['EffectiveTime']):
                        mins_to_dep = (row['EffectiveTime'] - now).total_seconds() / 60
                        if -15 < mins_to_dep <= 20:
                            is_urgent = True
                    
                    time_display = row['EffectiveTime'].strftime("%H:%M") if pd.notnull(row['EffectiveTime']) else row['Dep']
                    
                    # --- Divert Smart Parser ---
                    is_divert = "DIVERT" in str(row['Comment']).upper()
                    divert_html = ""
                    
                    if is_divert:
                        msg_text = "⚠️ DIVERT INSTRUCTION"
                        match = re.search(r"DIVERT TO[:\s]+([A-Z0-9]+)", str(row['Comment']), re.IGNORECASE)
                        if match:
                            target_bay = match.group(1).upper()
                            # Search for NEXT flight
                            next_flights = df[
                                (df['Bay'].astype(str).str.upper() == target_bay) & 
                                (df['Flight'] != row['Flight']) &
                                (df['EffectiveTime'] >= row['EffectiveTime']) 
                            ]
                            
                            if not next_flights.empty:
                                target = next_flights.iloc[0]
                                msg_text = f"⚠️ DIVERT BOWSER TO: {target['Flight']} / {target['Sector']} / {target['Bay']}"
                            else:
                                msg_text = f"⚠️ DIVERT BOWSER TO: BAY {target_bay} (No Flight Found)"
                                
                        divert_html = f'<div class="divert-msg">{msg_text}</div>'

                    # --- HTML CONSTRUCTION ---
                    card_class = "bay-card"
                    if is_divert: card_class += " card-divert"
                    if is_urgent and not is_divert: card_class += " card-urgent"
                    
                    urgent_banner = ""
                    time_class = ""
                    if is_urgent:
                        time_left = "NOW" if mins_to_dep < 1 else f"{int(mins_to_dep)} MIN"
                        urgent_banner = f'<div class="urgent-banner">🔥 EXPEDITE: DEP IN {time_left}</div>'
                        time_class = "time-urgent"

                    html = f"""
                    <div class="{card_class}">
                        <div class="card-header">
                            <span class="bay-badge">BAY {row['Bay']}</span>
                            <span class="bowser-pill">🚛 {row['Bowser']}</span>
                        </div>
                        {urgent_banner}
                        {divert_html}
                        <div class="card-body">
                            <div>
                                <div class="label">FLIGHT</div>
                                <div class="flight-big">{row['Flight']}</div>
                            </div>
                            <div style="text-align:right;">
                                <div class="label">CALL SIGN</div>
                                <div class="val">{row['CallSign']}</div>
                            </div>
                            
                            <div class="stat-box">
                                <div>
                                    <div class="label" style="color:#1565c0">95th %</div>
                                    <div class="stat-val">{row['Percentile']}</div>
                                </div>
                                <div style="text-align:right;">
                                    <div class="label" style="color:#1565c0">DEPARTURE</div>
                                    <div class="val {time_class}">{time_display}</div>
                                </div>
                            </div>

                            <div>
                                <div class="label">SECTOR</div>
                                <div class="val">📍 {row['Sector']}</div>
                            </div>
                             <div style="text-align:right;">
                                <div class="label">CREW</div>
                                <div class="val">{row['Crew']}</div>
                            </div>
                        </div>
                    </div>
                    """
                    st.markdown(html, unsafe_allow_html=True)

    # --- TAB 3: CREW SUMMARY ---
    with tab_crew:
        crew_df = df[df['Crew'].str.len() > 1].copy()
        if not crew_df.empty:
            crew_summary = crew_df.groupby('Crew')['Flight'].apply(lambda x: ', '.join(x)).reset_index()
            st.table(crew_summary)
        else:
            st.info("No Crew Assigned")

    # --- AUTO REFRESH LOOP ---
    time.sleep(REFRESH_RATE)
    st.rerun()

else:
    st.warning("Loading data... (If this persists, check your Internet or Sheet URL)")
