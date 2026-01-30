import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- CONFIGURATION ---
# 🔴 PASTE YOUR GOOGLE SCRIPT URL HERE (The one ending in /exec)
SHEET_API_URL = 'https://script.google.com/macros/s/AKfycbxZ4c88cfqMzpm4nGUs5m4cEbp5QtGtNN9lQIIFVLFsMiDFJYb6MYhnN71oNaGUE9m4PQ/exec'
REFRESH_RATE = 10 

# --- PAGE CONFIG ---
st.set_page_config(page_title="Field Ops", page_icon="⛽", layout="wide") 

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .stApp { background-color: #f0f2f5; }
    .block-container { padding-top: 1rem; padding-bottom: 5rem; }
    
    /* CARD STYLES */
    .job-card {
        background: white; border-radius: 12px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.08);
        padding: 0; margin-bottom: 16px;
        border-left: 8px solid #cfd8dc;
        position: relative; overflow: hidden;
    }
    
    /* PRIORITY COLORS */
    .priority-critical { border-left-color: #d32f2f !important; }
    .priority-warning { border-left-color: #fbc02d !important; }
    .priority-safe { border-left-color: #388e3c !important; }
    
    /* BADGES */
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

    /* CARD SECTIONS */
    .card-top { background: #ffffff; padding: 12px 16px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #f5f5f5; }
    .card-main { padding: 16px; display: flex; justify-content: space-between; align-items: center; }
    .card-footer { background: #f8f9fa; padding: 8px 16px; border-top: 1px solid #eee; display: flex; align-items: center; gap: 10px; }

    /* TAGS */
    .bay-tag { font-size: 20px; font-weight: 900; color: #263238; background: #eceff1; padding: 4px 10px; border-radius: 6px; }
    .bowser-tag { font-size: 16px; font-weight: 700; color: #1b5e20; background: #e8f5e9; padding: 4px 12px; border-radius: 20px; border: 1px solid #c8e6c9; }

    /* TEXT */
    .flight-id { font-size: 28px; font-weight: 800; color: #212121; letter-spacing: -1px; }
    .dep-time { font-size: 22px; font-weight: 700; color: #424242; }
    .time-sub { font-size: 11px; font-weight: bold; text-align: right; margin-top: -4px;}
    .percentile-box { color: #0277bd; font-weight: 800; font-size: 16px; }

    /* STATUS COLORS */
    .status-red { color: #d32f2f; }
    .status-orange { color: #f57f17; }
    .status-green { color: #388e3c; }

    /* DIVERT BANNER */
    .divert-banner { background: #fff3e0; color: #e65100; padding: 10px; font-weight: bold; font-size: 14px; text-align: center; border-bottom: 1px solid #ffe0b2; }

    /* INPUTS */
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
        if len(s) == 4 and s.isdigit():
            h, m = int(s[:2]), int(s[2:])
        elif ':' in s:
            parts = s.split(':')
            h, m = int(parts[0]), int(parts[1])
        else:
            return None
        dep_time = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if (dep_time - now).total_seconds() < -43200:
             dep_time = dep_time.replace(day=now.day + 1)
        return dep_time
    except:
        return None

@st.cache_data(ttl=5)
def fetch_data():
    try:
        response = requests.get(SHEET_API_URL)
        if response.status_code == 200:
            data = response.json()
            rows = []
            if isinstance(data, dict): list_data = data.get('flights', [])
            else: list_data = []
            
            for item in list_data:
                d = item['data'] if isinstance(item, dict) else item
                if not isinstance(d, list): continue
                while len(d) < 11: d.append("") 
                
                # 95% Logic
                p_val = str(d[3]).strip()
                if p_val == "": p_val = "--"
                
                rows.append({
                    'Flight': d[0], 'Dep': d[1], 'Sector': d[2], 
                    '95th %': p_val, 
                    'Call Sign': d[4], 'Bay': d[5], 'ETA': d[6], 
                    'Crew': d[7], 'Bowser': d[8], 'Comment': d[9],
                    'Field Feedback': d[10]
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
    except:
        st.error("Failed")

# --- APP START ---
tab_run, tab_master = st.tabs(["🚀 ACTIVE JOBS", "📊 MASTER BOARD"])

# --- TAB 1: RUNNING BAYS ---
with tab_run:
    df = fetch_data()
    now = datetime.now()
    
    # Constrain width for mobile feel
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if not df.empty:
            running = df[df['Bowser'].str.strip() != ""].copy()
            
            if running.empty:
                st.info("No active jobs.")
            else:
                running['DepObj'] = running['Dep'].apply(parse_dep_time)
                running['MinsLeft'] = running['DepObj'].apply(
                    lambda x: (x - now).total_seconds() / 60 if x else 9999
                )
                running = running.sort_values(by='MinsLeft')
                
                for i, row in running.iterrows():
                    mins = row['MinsLeft']
                    
                    # Priority Logic
                    if mins < 20:
                        priority_class = "priority-critical"
                        badge_html = '<div class="arrow-badge">⬆️ PRIORITY</div>'
                        time_color = "status-red"
                        time_msg = f"DEP IN {int(mins)} MIN" if mins > 0 else "DEPARTING NOW"
                    elif mins < 30:
                        priority_class = "priority-warning"
                        badge_html = '<div class="warning-badge">⚠️ PREPARE</div>'
                        time_color = "status-orange"
                        time_msg = f"{int(mins)} MIN LEFT"
                    else:
                        priority_class = "priority-safe"
                        badge_html = ""
                        time_color = "status-green"
                        time_msg = "ON TIME"

                    # Divert
                    is_divert = "DIVERT" in str(row['Comment']).upper()
                    divert_html = ""
                    if is_divert:
                        msg = str(row['Comment'])
                        divert_html = f'<div class="divert-banner">⚠️ {msg}</div>'
                        priority_class = "priority-critical"

                    st.markdown(f"""
                    <div class="job-card {priority_class}">
                        {badge_html}
                        <div class="card-top">
                            <span class="bay-tag">BAY {row['Bay']}</span>
                            <span class="bowser-tag">🚛 {row['Bowser']}</span>
                        </div>
                        {divert_html}
                        <div class="card-main">
                            <div><div style="font-size:10px; color:#999; font-weight:bold;">FLIGHT</div><div class="flight-id">{row['Flight']}</div></div>
                            <div style="text-align:right;">
                                <div style="font-size:10px; color:#999; font-weight:bold;">DEPARTURE</div>
                                <div class="dep-time">{row['Dep']}</div>
                                <div class="time-sub {time_color}">{time_msg}</div>
                            </div>
                        </div>
                        <div class="card-footer">
                             <div style="font-size:11px; color:#999; font-weight:bold;">95% QTY:</div>
                             <div class="percentile-box">{row['95th %']}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        val = st.text_input("Report", placeholder="Comment...", key=f"in_{row['Flight']}", label_visibility="collapsed")
                    with col_b:
                        if st.button("Send", key=f"btn_{row['Flight']}"):
                            if val: send_feedback(row['Flight'], val)
                    st.markdown("---")

# --- TAB 2: MASTER BOARD ---
with tab_master:
    if not df.empty:
        # Full Columns
        display_cols = ['Flight', 'Dep', 'Sector', '95th %', 'Call Sign', 'Bay', 'ETA', 'Crew', 'Bowser', 'Comment', 'Field Feedback']
        valid_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[valid_cols], hide_index=True, use_container_width=True, height=700)

time.sleep(REFRESH_RATE)
st.rerun()
