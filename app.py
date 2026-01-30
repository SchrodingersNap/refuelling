import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import re

# --- CONFIGURATION ---
# 🔴 PASTE NEW GOOGLE SCRIPT URL HERE
SHEET_API_URL = 'https://script.google.com/macros/s/AKfycbzsjUcBq4twKUI7Zd5xrbxhYmxITrWgFXehQ6scYCtdxW1QTOj46XEXzNVZLLK_asGjgA/exec'
FUEL_DATA_URL = 'https://raw.githubusercontent.com/SchrodingersNap/refuelling/refs/heads/main/flight_fuel.csv'
REFRESH_RATE = 100 

st.set_page_config(page_title="Refuel Ops", page_icon="⛽", layout="wide") 

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
    .bay-tag { font-size: 20px; font-weight: 900; color: #263238; background: #eceff1; padding: 4px 10px; border-radius: 6px; }
    .bowser-tag { font-size: 16px; font-weight: 700; color: #1b5e20; background: #e8f5e9; padding: 4px 12px; border-radius: 20px; border: 1px solid #c8e6c9; }
    .flight-id { font-size: 28px; font-weight: 800; color: #212121; }
    .sector-lbl { font-size: 14px; font-weight: 700; color: #546e7a; margin-top: 4px;}
    .dep-time { font-size: 22px; font-weight: 700; color: #424242; }
    .time-sub { font-size: 11px; font-weight: bold; text-align: right; }
    .status-red { color: #d32f2f; } .status-orange { color: #f57f17; } .status-green { color: #388e3c; }
    .divert-banner { background: #fff3e0; color: #e65100; padding: 10px; font-weight: bold; text-align: center; border-bottom: 1px solid #ffe0b2; }
    .stTextInput input { padding: 8px; } 
    /* Button Styles */
    .stButton button { width: 100%; height: 42px; font-weight: bold; }
    button[data-testid="baseButton-secondary"] { border-color: #4caf50; color: #4caf50; }
    button[data-testid="baseButton-secondary"]:hover { background-color: #e8f5e9; border-color: #4caf50; color: #4caf50; }
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

def normalize_flight_id(val):
    if not isinstance(val, str): val = str(val)
    val = val.strip().upper()
    match = re.search(r'^(\d)\.?0*E\+?(\d+)$', val)
    if match: val = f"{match.group(1)}E{match.group(2)}"
    return val.replace(" ", "").replace("-", "")

@st.cache_data(ttl=600)
def fetch_and_calculate_fuel_stats():
    try:
        df_fuel = pd.read_csv(FUEL_DATA_URL, dtype=str)
        df_fuel.columns = df_fuel.columns.str.strip().str.replace(" ", "_")
        if 'Flight_ID' not in df_fuel.columns: df_fuel.rename(columns={df_fuel.columns[0]: 'Flight_ID'}, inplace=True)
        if 'Qty' not in df_fuel.columns: df_fuel.rename(columns={df_fuel.columns[1]: 'Qty'}, inplace=True)
        df_fuel['JoinKey'] = df_fuel['Flight_ID'].apply(normalize_flight_id)
        df_fuel['Qty'] = pd.to_numeric(df_fuel['Qty'], errors='coerce')
        df_agg = df_fuel.groupby('JoinKey')['Qty'].quantile(0.95).reset_index()
        df_agg['Qty'] = df_agg['Qty'].round(2)
        return df_agg
    except: return pd.DataFrame(columns=['JoinKey', 'Qty'])

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
                while len(d) < 10: d.append("")
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
    except: return pd.DataFrame()
    return pd.DataFrame()

def send_update(flight_no, action, comment=""):
    try:
        payload = {"flight": flight_no, "action": action, "comment": comment}
        requests.post(SHEET_API_URL, json=payload)
        
        if action == 'close': st.toast(f"✅ Closed {flight_no}")
        else: st.toast(f"📨 Note added to {flight_no}")
        
        time.sleep(1)
        st.rerun()
    except: st.error("Failed")

# --- MAIN ---
df_live = fetch_live_data()
df_stats = fetch_and_calculate_fuel_stats()

if not df_live.empty:
    df_live['JoinKey'] = df_live['Flight'].apply(normalize_flight_id)
    df_merged = pd.merge(df_live, df_stats[['JoinKey', 'Qty']], on='JoinKey', how='left')
    df_merged['Qty'] = df_merged['Qty'].fillna("--")
else:
    df_merged = pd.DataFrame()

now = datetime.now()
tab_run, tab_master = st.tabs(["🚀 ACTIVE JOBS", "📊 MASTER BOARD"])

with tab_run:
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
                
                for idx, (index, row) in enumerate(running.iterrows()):
                    mins = row['MinsLeft']
                    if mins < 20: cls, badge, col, msg = "priority-critical", '<div class="arrow-badge">⬆️ PRIORITY</div>', "status-red", f"DEP IN {int(mins)} MIN"
                    elif mins < 30: cls, badge, col, msg = "priority-warning", '<div class="warning-badge">⚠️ PREPARE</div>', "status-orange", f"{int(mins)} MIN LEFT"
                    else: cls, badge, col, msg = "priority-safe", "", "status-green", "ON TIME"

                    is_divert = "DIVERT" in str(row['Comment']).upper()
                    div_html = f'<div class="divert-banner">⚠️ {row["Comment"]}</div>' if is_divert else ""
                    if is_divert: cls = "priority-critical"

                    st.markdown(f"""
                    <div class="job-card {cls}">{badge}<div class="card-top"><span class="bay-tag">BAY {row['Bay']}</span><span class="bowser-tag">🚛 {row['Bowser']}</span></div>{div_html}
                    <div class="card-main"><div><div style="font-size:10px; color:#999; font-weight:bold;">FLIGHT</div><div class="flight-id">{row['Flight']}</div><div class="sector-lbl">📍 {row['Sector']}</div></div>
                    <div style="text-align:right;"><div style="font-size:10px; color:#999; font-weight:bold;">DEPARTURE</div><div class="dep-time">{row['Dep']}</div><div class="time-sub {col}">{msg}</div></div></div></div>
                    """, unsafe_allow_html=True)
                    
                    # ACTION ROW
                    ca, cb, cc = st.columns([3, 1.2, 1.2])
                    with ca: val = st.text_input("Rpt", placeholder="Note...", key=f"in_{row['Flight']}_{idx}", label_visibility="collapsed")
                    with cb: 
                        if st.button("Send", key=f"btn_send_{row['Flight']}_{idx}"): 
                            if val: send_update(row['Flight'], "comment", val)
                    with cc:
                        # CLOSE BUTTON
                        if st.button("✅ Done", key=f"btn_close_{row['Flight']}_{idx}"):
                             send_update(row['Flight'], "close")
                    
                    st.markdown("---")

with tab_master:
    if not df_merged.empty:
        df_disp = df_merged.rename(columns={'Qty': '95th %'})
        cols = ['Flight', '95th %', 'Dep', 'Sector', 'Bay', 'Bowser', 'Call Sign', 'ETA', 'Crew', 'Comment', 'Field Feedback']
        st.dataframe(df_disp[cols], hide_index=True, use_container_width=True, height=700)

time.sleep(REFRESH_RATE)
st.rerun()
