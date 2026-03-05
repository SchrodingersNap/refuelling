import streamlit as st
import pandas as pd
import requests
import re
import os
from streamlit_autorefresh import st_autorefresh

# --- CONFIGURATION ---
SHEET_API_URL = 'https://script.google.com/macros/s/AKfycbzbBOdm442zsjhvkiV6wuX-ZdSWtxaDtxrIRenROtaoYoBAz8ApbnNj916zIpRrnYWe/exec'
FUEL_FILE = 'flight_fuel.csv'

st.set_page_config(page_title="Refuel Ops", page_icon="⛽", layout="wide") 

# --- SAFE AUTO-REFRESH (5 Min) ---
st_autorefresh(interval=300000, limit=None, key="auto_refresh_timer")

# --- ULTRA-MINIMALIST CSS OVERHAUL ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800&display=swap');

    .stApp { background-color: #F4F5F7; font-family: 'Inter', sans-serif; }
    header {visibility: hidden;} footer {visibility: hidden;}
    .block-container { padding: 0rem !important; max-width: 100%; }

    /* Custom Streamlit Tabs Styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 20px;
        padding: 20px 20px 0px 20px;
        background-color: #F4F5F7;
    }
    .stTabs [data-baseweb="tab"] {
        padding: 10px 20px;
        background-color: transparent;
        border-radius: 50px;
        border: 2px solid #E2E8F0;
        font-weight: 800;
        color: #94A3B8;
        transition: all 0.3s ease;
    }
    .stTabs [aria-selected="true"] {
        background-color: #0F172A;
        color: #FFFFFF !important;
        border-color: #0F172A;
    }

    /* Minimalist Flight Card */
    .flight-card {
        background: #FFFFFF;
        border-radius: 20px;
        padding: 20px 25px;
        margin: 15px 20px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 10px 40px -10px rgba(0,0,0,0.05);
        border: 1px solid rgba(0,0,0,0.02);
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .flight-card:hover { transform: translateY(-3px); box-shadow: 0 15px 50px -10px rgba(0,0,0,0.1); }
    
    /* Active Bowser Styling */
    .card-active { border-left: 6px solid #10B981; }
    .bowser-badge { background: #D1FAE5; color: #065F46; padding: 6px 14px; border-radius: 30px; font-weight: 800; font-size: 14px; }
    
    /* Column Info Styling */
    .info-group { display: flex; flex-direction: column; gap: 4px; }
    .label { font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #94A3B8; font-weight: 600; }
    .value { font-size: 16px; color: #1E293B; font-weight: 600; }
    
    .flight-id { font-size: 22px; font-weight: 800; color: #0F172A; letter-spacing: -0.5px; }
    .load-val { color: #F59E0B; font-weight: 800; font-size: 18px; }
    .bay-val { background: #F1F5F9; padding: 4px 12px; border-radius: 8px; font-weight: 800; }
    .sub-text { font-size: 14px; color: #64748B; }
    .comment-text { font-style: italic; color: #EF4444; font-size: 13px; max-width: 150px; line-height: 1.2;}

    /* Force Refresh Button Styling */
    .stButton>button {
        width: calc(100% - 40px);
        margin: 10px 20px 30px 20px;
        height: 55px;
        background-color: #E2E8F0;
        color: #0F172A;
        border-radius: 16px;
        font-weight: 800;
        font-size: 16px;
        border: none;
        transition: 0.3s;
    }
    .stButton>button:hover { background-color: #CBD5E1; color: black; }

    /* MOBILE RESPONSIVENESS */
    @media (max-width: 768px) {
        .flight-card {
            flex-wrap: wrap;
            gap: 15px;
            padding: 20px;
        }
        .info-group { width: 45%; } 
        .info-group.comment-group { width: 100%; margin-top: 10px; padding-top: 10px; border-top: 1px dashed #E2E8F0; }
        .comment-text { max-width: 100%; }
        .stTabs [data-baseweb="tab-list"] { padding: 10px 10px 0px 10px; justify-content: center; }
        .flight-card { margin: 15px 10px; }
    }
</style>
""", unsafe_allow_html=True)

# --- FUNCTIONS ---
def normalize_flight_id(val):
    if not isinstance(val, str): val = str(val)
    val = val.strip().upper()
    match = re.search(r'^(\d)\.?0*E\+?(\d+)$', val)
    if match: val = f"{match.group(1)}E{match.group(2)}"
    return val.replace(" ", "").replace("-", "")

@st.cache_data(ttl=300) 
def fetch_and_calculate_fuel_stats():
    if not os.path.exists(FUEL_FILE): return pd.DataFrame(columns=['JoinKey', 'Qty'])
    try:
        df_fuel = pd.read_csv(FUEL_FILE, dtype=str)
        df_fuel.columns = df_fuel.columns.str.strip().str.replace(" ", "_")
        if 'Flight_ID' not in df_fuel.columns: df_fuel.rename(columns={df_fuel.columns[0]: 'Flight_ID'}, inplace=True)
        if 'Qty' not in df_fuel.columns: df_fuel.rename(columns={df_fuel.columns[1]: 'Qty'}, inplace=True)
        df_fuel['JoinKey'] = df_fuel['Flight_ID'].apply(normalize_flight_id)
        df_fuel['Qty'] = pd.to_numeric(df_fuel['Qty'], errors='coerce')
        df_agg = df_fuel.groupby('JoinKey')['Qty'].quantile(0.90).reset_index()
        df_agg['Qty'] = df_agg['Qty'].round(1)
        return df_agg
    except: return pd.DataFrame(columns=['JoinKey', 'Qty'])

@st.cache_data(ttl=5)
def fetch_live_data():
    try:
        response = requests.get(SHEET_API_URL)
        if response.status_code == 200:
            data = response.json()
            list_data = data.get('flights', []) if isinstance(data, dict) else []
            rows = []
            for item in list_data:
                d = item['data']
                while len(d) < 11: d.append("") 
                rows.append({
                    'Flight': str(d[0]).strip().upper(), 'Dep': str(d[1]), 'Des': str(d[2]), 
                    'Sign': str(d[3]), 'Bay': str(d[4]), 'ETA': str(d[5]), 'Crew': str(d[6]), 
                    'Bowser': str(d[7]), 'Comment': str(d[8]), 'FieldFeedback': str(d[9]), 'Status': str(d[10]) 
                })
            return pd.DataFrame(rows)
    except: pass
    return pd.DataFrame()

def render_cards(df, is_active_tab=True):
    """Generates the minimalist HTML for the flight cards."""
    if df.empty:
        st.markdown('<div style="text-align:center; padding: 40px; color:#94A3B8; font-weight:600;">No flights found.</div>', unsafe_allow_html=True)
        return

    # Using a list to combine the HTML strictly without weird Markdown indentation
    html_parts = []
    
    for _, row in df.iterrows():
        # Clean up data
        bowser = str(row['Bowser']).strip()
        comment = str(row['Comment']).strip()
        crew = str(row['Crew']).strip()
        
        has_bowser = bowser != "" and bowser.lower() != "nan"
        comment_display = comment if comment and comment.lower() != 'nan' else "--"
        crew_display = crew if crew and crew.lower() != 'nan' else "--"
        
        # Apply glowing green border if Bowser is assigned in the Active Tab
        card_class = "flight-card card-active" if has_bowser and is_active_tab else "flight-card"
        bowser_html = f'<span class="value bowser-badge">🚛 {bowser}</span>' if has_bowser else '<span class="value sub-text">--</span>'

        # Build Card HTML perfectly flushed to the left to prevent Markdown code block triggers
        card_html = f"""<div class="{card_class}">
<div class="info-group"><span class="label">Flight</span><span class="value flight-id">{row['Flight']}</span></div>
<div class="info-group"><span class="label">Load</span><span class="value load-val">{row['Load']}</span></div>
<div class="info-group"><span class="label">Dep</span><span class="value">{row['Dep']}</span></div>
<div class="info-group"><span class="label">Des / Sign</span><span class="value">{row['Des']} <span class="sub-text">| {row['Sign']}</span></span></div>
<div class="info-group"><span class="label">Bay</span><span class="value bay-val">{row['Bay']}</span></div>
<div class="info-group"><span class="label">Crew</span><span class="value sub-text">{crew_display}</span></div>
<div class="info-group"><span class="label">Bowser</span>{bowser_html}</div>
<div class="info-group comment-group"><span class="label">Comment</span><span class="value comment-text">{comment_display}</span></div>
</div>"""
        html_parts.append(card_html)
        
    # Combine and render
    st.markdown("".join(html_parts), unsafe_allow_html=True)


# --- MAIN APPLICATION ---

df_live = fetch_live_data()
df_stats = fetch_and_calculate_fuel_stats()

if not df_live.empty:
    df_live['JoinKey'] = df_live['Flight'].apply(normalize_flight_id)
    df_merged = pd.merge(df_live, df_stats[['JoinKey', 'Qty']], on='JoinKey', how='left')
    
    df_merged.rename(columns={'Qty': 'Load'}, inplace=True)
    df_merged['Load'] = df_merged['Load'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "--")
    df_merged = df_merged[df_merged['Flight'] != ""]

    is_done = df_merged['FieldFeedback'].str.strip().str.lower() == 'done'
    
    df_refuelled = df_merged[is_done].copy()
    df_active = df_merged[~is_done].copy()

    # --- UI TABS ---
    tab_active, tab_refuelled = st.tabs(["✈️ ACTIVE FLIGHTS", "✅ REFUELLED"])

    with tab_active:
        render_cards(df_active, is_active_tab=True)

    with tab_refuelled:
        render_cards(df_refuelled, is_active_tab=False)

else:
    st.markdown('<div style="text-align:center; padding: 50px; color:#64748B; font-weight:800; font-size:20px;">Waiting for Google Sheets data...</div>', unsafe_allow_html=True)

# --- MANUAL REFRESH ---
if st.button("🔄 Force Refresh Now"):
    st.rerun()
