import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime

# --- CONFIGURATION ---
# 🔴 PASTE YOUR NEW GOOGLE SCRIPT URL HERE
SHEET_API_URL = 'https://script.google.com/macros/s/AKfycbxZ4c88cfqMzpm4nGUs5m4cEbp5QtGtNN9lQIIFVLFsMiDFJYb6MYhnN71oNaGUE9m4PQ/exec'
REFRESH_RATE = 10 

# --- PAGE CONFIG ---
st.set_page_config(page_title="Field Ops", page_icon="⛽", layout="wide") 

# --- CSS ---
st.markdown("""
<style>
    .stApp { background-color: #f0f2f5; }
    .block-container { padding-top: 1rem; padding-bottom: 5rem; }
    .job-card { background: white; border-radius: 12px; box-shadow: 0 2px 5px rgba(0,0,0,0.08); margin-bottom: 16px; border-left: 8px solid #cfd8dc; overflow: hidden; }
    .priority-critical { border-left-color: #d32f2f !important; }
    .priority-warning { border-left-color: #fbc02d !important; }
    .priority-safe { border-left-color: #388e3c !important; }
    .arrow-badge { background: #d32f2f; color: white; width: 100%; text-align: center; font-weight: 900; padding: 6px; animation: pulse 1.5s infinite; }
    .warning-badge { background: #fbc02d; color: black; width: 100%; text-align: center; font-weight: 900; padding: 6px; }
    .card-top { padding: 12px 16px; display: flex; justify-content: space-between; border-bottom: 1px solid #eee; }
    .card-main { padding: 16px; display: flex; justify-content: space-between; align-items: center; }
    .card-footer { background: #f8f9fa; padding: 8px 16px; border-top: 1px solid #eee; display: flex; gap: 10px; }
    .bay-tag { font-size: 20px; font-weight: 900; color: #263238; background: #eceff1; padding: 4px 10px; border-radius: 6px; }
    .bowser-tag { font-size: 16px; font-weight: 700; color: #1b5e20; background: #e8f5e9; padding: 4px 12px; border-radius: 20px; border: 1px solid #c8e6c9; }
    .flight-id { font-size: 28px; font-weight: 800; color: #212121; }
    .dep-time { font-size: 22px; font-weight: 700; color: #424242; }
    .time-sub { font-size: 11px; font-weight: bold; text-align: right; }
    .status-red { color: #d32f2f; } .status-orange { color: #f57f17; } .status-green { color: #388e3c; }
    .percentile-box { color: #0277bd; font-weight: 800; font-size: 16px; }
    .divert-banner { background: #fff3e0; color: #e65100; padding: 10px; font-weight: bold; text-align: center; border-bottom: 1px solid #ffe0b2; }
    .stTextInput input { padding: 8px; } .stButton button { width: 100%; height: 42px; font-weight: bold; }
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

@st.cache_data(ttl=5)
def fetch_data():
    try:
        response = requests.get(SHEET_API_URL)
        if response.status_code == 200:
            data = response.json()
            rows = []
            list_data = data.get('flights', []) if isinstance(data, dict) else []
            
            for item in list_data:
                d = item['data']
                while len(d) < 11: d.append("") 
                
                # FORCE STRING & CLEANUP FOR 95%
                p_val = str(d[3]).strip()
                if p_val == "" or p_val.lower() == "nan": p_val = "--"
                
                rows.append({
                    'Flight': str(d[0]), 'Dep': str(d[1]), 'Sector': str(d[2]), 
                    '95th %': p_val, 'Call Sign': str(d[4]), 'Bay': str(d[5]), 
                    'ETA': str(d[6]), 'Crew': str(d[7]), 'Bowser': str(d[8]), 
                    'Comment': str(d[9]), 'Field Feedback': str(d[10])
                })
            return pd.DataFrame(rows)
    except: return pd.DataFrame()
    return pd.DataFrame()

def send_feedback(flight_no, comment):
    try:
        requests.post(SHEET_API_URL, json={"flight": flight_no, "comment": comment})
        st.toast(f"✅ Sent for {flight_no}")
        time.sleep(1)
        st.rerun()
    except: st.error("Failed")

# --- APP ---
tab_run, tab_master = st.tabs(["🚀 ACTIVE JOBS", "📊 MASTER BOARD"])
df = fetch_data()
now = datetime.now()

# --- FILTER LOGIC (Hide flights older than 4 hours) ---
if not df.empty:
    df['DepObj'] = df['Dep'].apply(parse_dep_time)
    # Only keep flights that are in the future OR less than 4 hours old (-240 mins)
    df['MinsLeft'] = df['DepObj'].apply(lambda x: (x - now).total_seconds() / 60 if x else 9999)
    df = df[df['MinsLeft'] > -240] # HIDES OLD FLIGHTS AUTOMATICALLY

with tab_run:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        if not df.empty:
            # Clean filtering for Bowsers (ignore empty spaces)
            running = df[df['Bowser'].str.strip().astype(bool)].copy()
            
            if running.empty:
                st.info("No active jobs (Check 'Bowser' column in Excel).")
            else:
                running = running.sort_values(by='MinsLeft')
                for i, row in running.iterrows():
                    mins = row['MinsLeft']
                    if mins < 20: cls, badge, col, msg = "priority-critical", '<div class="arrow-badge">⬆️ PRIORITY</div>', "status-red", f"DEP IN {int(mins)} MIN"
                    elif mins < 30: cls, badge, col, msg = "priority-warning", '<div class="warning-badge">⚠️ PREPARE</div>', "status-orange", f"{int(mins)} MIN LEFT"
                    else: cls, badge, col, msg = "priority-safe", "", "status-green", "ON TIME"
                    
                    div_html = f'<div class="divert-banner">⚠️ {row["Comment"]}</div>' if "DIVERT" in str(row['Comment']).upper() else ""
                    
                    st.markdown(f"""
                    <div class="job-card {cls}">{badge}<div class="card-top"><span class="bay-tag">BAY {row['Bay']}</span><span class="bowser-tag">🚛 {row['Bowser']}</span></div>{div_html}
                    <div class="card-main"><div><div style="font-size:10px; color:#999; font-weight:bold;">FLIGHT</div><div class="flight-id">{row['Flight']}</div></div>
                    <div style="text-align:right;"><div style="font-size:10px; color:#999; font-weight:bold;">DEPARTURE</div><div class="dep-time">{row['Dep']}</div><div class="time-sub {col}">{msg}</div></div></div>
                    <div class="card-footer"><div style="font-size:11px; color:#999; font-weight:bold;">95% QTY:</div><div class="percentile-box">{row['95th %']}</div></div></div>
                    """, unsafe_allow_html=True)
                    
                    ca, cb = st.columns([3,1])
                    with ca: val = st.text_input("Rpt", placeholder="Comment...", key=f"in_{row['Flight']}", label_visibility="collapsed")
                    with cb: 
                        if st.button("Send", key=f"btn_{row['Flight']}"): 
                            if val: send_feedback(row['Flight'], val)
                    st.markdown("---")
        else: st.info("Connection successful, but no flights found.")

with tab_master:
    if not df.empty:
        # Show specific columns
        cols = ['Flight', 'Dep', 'Sector', '95th %', 'Call Sign', 'Bay', 'ETA', 'Crew', 'Bowser', 'Comment', 'Field Feedback']
        st.dataframe(df[[c for c in cols if c in df.columns]], hide_index=True, use_container_width=True, height=700)

time.sleep(REFRESH_RATE)
st.rerun()
