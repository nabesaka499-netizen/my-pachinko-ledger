import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta
import json
try:
    import holidays
    from streamlit_calendar import calendar
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False
from io import StringIO

# --- Page Config ---
st.set_page_config(page_title="収支管理簿", page_icon="💹", layout="wide")

# --- Custom CSS (Neon Theme) ---
st.markdown("""
<style>
    .main {
        background-color: #0a0b1e;
    }
    .stApp {
        background: radial-gradient(circle at top right, #161b33, #0a0b1e);
    }
    h1, h2, h3 {
        color: #00f2ff !important;
        text-shadow: 0 0 10px rgba(0, 242, 255, 0.5);
    }
    .stMetric {
        background: rgba(0, 242, 255, 0.05) !important;
        border: 1px solid rgba(0, 242, 255, 0.3) !important;
        box-shadow: 0 0 15px rgba(0, 242, 255, 0.1);
    }
    .stDataFrame, .stTable {
        border: 1px solid rgba(0, 242, 255, 0.2);
        border-radius: 10px;
    }
    div[data-testid="stMetricValue"] > div {
        color: #00f2ff !important;
    }
</style>
""", unsafe_allow_html=True)

import requests
import base64

# --- Global Timezone (JST) ---
JST = timezone(timedelta(hours=9))

# --- Data Handling (GitHub and Local CSV) ---
GITHUB_USER = "nabesaka499-netizen"
GITHUB_REPO = "my-pachinko-ledger"
DATA_FILE = "records.csv"

def get_github_auth():
    if "GITHUB_TOKEN" in st.secrets:
        return st.secrets["GITHUB_TOKEN"]
    return None

def load_data():
    token = get_github_auth()
    if token:
        try:
            # Load from GitHub
            url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{DATA_FILE}"
            headers = {"Authorization": f"token {token}"}
            r = requests.get(url, headers=headers)
            if r.status_code == 200:
                content_json = r.json()
                content = base64.b64decode(content_json["content"]).decode("utf-8")
                df = pd.read_csv(StringIO(content))
                # Cleanup: remove completely invalid rows (only date and player are strictly required)
                if not df.empty:
                    # Fill NaN hall/machine with empty string instead of dropping
                    df['hall'] = df['hall'].fillna("")
                    df['machine'] = df['machine'].fillna("")
                    df = df.dropna(subset=['date', 'player'], how='any')
                
                # Normalize date format and ensure it's a string for saving/displaying
                if "date" in df.columns:
                    df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
                    # Remove any coercion failures (Nat)
                    df = df.dropna(subset=['date'])
                st.session_state.records = df
                st.session_state.github_sha = content_json["sha"]
                return df
        except Exception as e:
            st.error(f"GitHub読み込みエラー: {e}")
    
    # Fallback to local or session state
    if "records" not in st.session_state:
        try:
            st.session_state.records = pd.read_csv(DATA_FILE)
            st.session_state.records['date'] = pd.to_datetime(st.session_state.records['date']).dt.strftime('%Y-%m-%d')
        except:
            st.session_state.records = pd.DataFrame(columns=[
                "id", "player", "game_type", "date", "hall", "machine", 
                "hours", "start_time", "end_time", "invest", "start_savings", "end_savings", "cash_out_yen", "rate", "balance", "memo"
            ])
        
        # Stability: Fill missing columns and NaNs for safety
        expected_cols = ["id", "player", "game_type", "date", "hall", "machine", "hours", "start_time", "end_time", "invest", "start_savings", "end_savings", "cash_out_yen", "rate", "balance", "memo"]
        for col in expected_cols:
            if col not in st.session_state.records.columns:
                st.session_state.records[col] = 0 if col in ["invest", "start_savings", "end_savings", "cash_out_yen", "balance", "hours"] else ""
        
        # Fill NaNs in numeric columns
        num_cols = ["invest", "start_savings", "end_savings", "cash_out_yen", "balance", "hours", "rate"]
        st.session_state.records[num_cols] = st.session_state.records[num_cols].fillna(0)
    
    return st.session_state.records

def save_data(df):
    st.session_state.records = df
    token = get_github_auth()
    
    if token:
        try:
            # Save to GitHub (Commit)
            url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{DATA_FILE}"
            headers = {"Authorization": f"token {token}"}
            
            # Get latest SHA to avoid conflicts
            r_get = requests.get(url, headers=headers)
            sha = r_get.json()["sha"] if r_get.status_code == 200 else None
                
            csv_content = df.to_csv(index=False)
            data = {
                "message": f"Update records via App {datetime.now(JST).strftime('%Y-%m-%d %H:%M')}",
                "content": base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
            }
            if sha: data["sha"] = sha
            
            res = requests.put(url, json=data, headers=headers)
            if res.status_code in [200, 201]:
                st.session_state.github_sha = res.json()["content"]["sha"]
            else:
                st.error(f"保存エラー: {res.status_code} {res.text}")
        except Exception as e:
            st.error(f"GitHub保存エラー: {e}")
    else:
        # Local save fallback
        df.to_csv(DATA_FILE, index=False)

def calculate_balance(row):
    return row['recovery'] - row['invest']

def parse_time_to_float(time_val):
    """Converts 'H:M', 'H:MM' or numeric strings/floats to float hours."""
    if pd.isna(time_val) or time_val == "" or time_val == 0:
        return 0.0
    s = str(time_val).strip()
    if ":" in s:
        try:
            h, m = s.split(":")
            return round(int(h) + int(m)/60, 1)
        except:
            return 0.0
    try:
        return round(float(s.replace(',', '')), 1)
    except:
        return 0.0

# --- App Logic ---
df = load_data()

st.title("収支管理簿")
st.caption("Pachinko & Slot Balance Analytics")

# Sidebar for Navigation
st.sidebar.markdown("### メニュー")
menu = st.sidebar.radio("選択してください", ["ホーム・記録", "分析 (月別/年別)", "一括インポート", "設定"], label_visibility="collapsed")

# Helper to get default values for Hall and Machine per player
def get_last_player_defaults(df, player):
    # Try to get from drafts first
    drafts = st.session_state.get('drafts', {})
    p_draft = drafts.get(player, {})
    if p_draft.get('last_hall') and p_draft.get('last_machine'):
        return p_draft['last_hall'], p_draft['last_machine']
    
    # Fallback to history
    if not df.empty:
        p_history = df[df['player'] == player]
        if not p_history.empty:
            last = p_history.iloc[-1]
            return last['hall'], last['machine']
    return "新規入力...", "新規入力..."

def get_last_hall_savings(df, player, hall_name):
    if df.empty or not hall_name or hall_name in ["記録しない", "新規入力..."]:
        return None
    p_df = df[(df['player'] == player) & (df['hall'] == hall_name)]
    if p_df.empty:
        return None
    # Sort by date and id to get the absolute latest
    last_row = p_df.sort_values(by=['date', 'id'], ascending=False).iloc[0]
    e_savings = last_row.get('end_savings', 0)
    c_out_yen = last_row.get('cash_out_yen', 0)
    rate = last_row.get('rate', 1.0)
    
    # Convert Yen back to savings: (Yen / 100 * Rate)
    # The formula (Yen / 100 * Rate) gives the number of coins/balls
    # e.g., 10,000 yen / 100 * 5.06 = 506 coins
    c_out_savings = (c_out_yen / 100) * rate if rate > 0 else 0
    return e_savings - c_out_savings

# --- Draft Persistence (for "Browser Closed" scenario) ---
DRAFT_FILE = "drafts.json"

def load_drafts():
    if "drafts" not in st.session_state:
        try:
            with open(DRAFT_FILE, "r") as f:
                st.session_state.drafts = json.load(f)
        except:
            st.session_state.drafts = {
                "Player 1": {"start_hour": 9, "start_min": 0, "last_hall": None, "last_machine": None, "last_rate": None}, 
                "Player 2": {"start_hour": 9, "start_min": 0, "last_hall": None, "last_machine": None, "last_rate": None}
            }
    return st.session_state.drafts

def save_drafts():
    try:
        with open(DRAFT_FILE, "w") as f:
            json.dump(st.session_state.drafts, f)
    except:
        pass

load_drafts()

if menu == "ホーム・記録":
    # --- Month Summary Header ---
    current_month = datetime.now().strftime("%Y-%m")
    df_this_month = df.copy()
    df_this_month['month'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m')
    df_this_month = df_this_month[df_this_month['month'] == current_month]
    
    sum_cols = st.columns(2)
    for i, p_name in enumerate(["Player 1", "Player 2"]):
        with sum_cols[i]:
            p_df = df_this_month[df_this_month['player'] == p_name]
            p_bal = p_df['balance'].sum()
            p_hours = p_df['hours'].sum()
            p_hourly = p_bal / p_hours if p_hours > 0 else 0
            
            st.markdown(f"""
            <div style="padding:10px; border:1px solid rgba(0,242,255,0.2); border-radius:10px; background:rgba(0,242,255,0.05); text-align:center;">
                <div style="font-weight:bold; color:#00f2ff; margin-bottom:5px;">{p_name} ({datetime.now().strftime('%m月')}収支)</div>
                <div style="font-size:1.4em; font-weight:bold;">¥{int(p_bal):,}</div>
                <div style="font-size:0.8em; opacity:0.8;">{p_hours:.1f}h | ¥{int(p_hourly):,}/h</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.divider()
    
    # --- CALENDAR VIEW (Top-level Interface) ---
    st.subheader("収支カレンダー")
    
    if not CALENDAR_AVAILABLE:
        st.info("🔄 カレンダー機能を準備中です。ライブラリのインストールが完了するまでお待ちください。")
        selected_date_picker = st.date_input("記録・編集する日付を選択", datetime.now(JST))
        st.session_state.selected_cal_date = selected_date_picker.strftime("%Y-%m-%d")
    else:
        # Player Filter for Calendar
        p_cal = st.radio("表示切り替え", ["Player 1", "Player 2"], horizontal=True, key="cal_p_selector", index=0)
        
        # Prepare calendar events
        events = []
        jp_holidays = holidays.Japan()
        
        # 1. Add Holidays
        if not df.empty:
            df_dates = pd.to_datetime(df['date'], errors='coerce')
            df_dates = df_dates.dropna()
            if not df_dates.empty:
                start_year = df_dates.min().year
                end_year = df_dates.max().year
                cur_year = datetime.now(JST).year
                for y in range(min(start_year, cur_year), max(end_year, cur_year) + 1):
                    for d, name in sorted(holidays.Japan(years=y).items()):
                        d_str = d.strftime("%Y-%m-%d")
                        events.append({"title": f"㊗️ {name}", "start": d_str, "allDay": True, "display": "background", "backgroundColor": "#ff4b4b1a"})
                        events.append({"title": name, "start": d_str, "allDay": True, "textColor": "#ff4b4b", "backgroundColor": "transparent", "borderColor": "transparent"})

        # 2. Add Profit/Loss
        cal_df = df[df['player'] == p_cal].copy()
        if not cal_df.empty:
            daily_summary = cal_df.groupby('date')['balance'].sum().reset_index()
            for _, row in daily_summary.iterrows():
                bal = int(row['balance'])
                color = "#ffffff" if bal >= 0 else "#ff4b4b"
                sign = "+" if bal >= 0 else ""
                events.append({
                    "id": f"summary_{row['date']}",
                    "title": f"{sign}{bal:,}円",
                    "start": row['date'],
                    "allDay": True,
                    "backgroundColor": "transparent",
                    "borderColor": "transparent",
                    "textColor": color,
                    "extendedProps": {"type": "summary", "date": row['date']}
                })
        
        calendar_options = {
            "editable": False,
            "selectable": True,
            "headerToolbar": {"left": "today prev,next", "center": "title", "right": "dayGridMonth"},
            "initialView": "dayGridMonth",
            "locale": "ja",
            "height": 650,
        }
        
        custom_css="""
            .fc-event-title { font-weight: bold; font-size: 0.9em; cursor: pointer; }
            .fc-daygrid-day-number { color: #00f2ff !important; }
            .fc-col-header-cell-cushion { color: #00f2ff !important; }
            .fc-toolbar-title { color: #00f2ff !important; }
            .fc-daygrid-day:hover { background: rgba(0, 242, 255, 0.05) !important; cursor: pointer; }
        """
        
        cal_res = calendar(events=events, options=calendar_options, custom_css=custom_css, key="main_cal")
        
        # Interaction Logic: Prioritize NEW interactions from the component return value
        res = cal_res or st.session_state.get("main_cal", {})
        if res:
            cb = res.get("callback")
            target_date = None
            
            if cb == "dateClick":
                dc = res.get("dateClick", {})
                target_date = dc.get("dateStr") or dc.get("date")
            elif cb == "select":
                sel = res.get("select", {})
                target_date = sel.get("startStr") or sel.get("start")
            elif cb == "eventClick":
                ec = res.get("eventClick", {})
                event = ec.get("event", {})
                props = event.get("extendedProps", {})
                if props.get("type") == "summary":
                    target_date = props.get("date")
                    # Set editing_id if it's an event click
                    day_records = cal_df[cal_df['date'] == target_date]
                    if not day_records.empty:
                        st.session_state.editing_id = day_records.iloc[0]['id']
            
            if target_date:
                new_date = target_date.split("T")[0]
                # Only update and rerun if the date or mode actually changed to avoid loops
                if st.session_state.get("selected_cal_date") != new_date or (cb == "dateClick" and st.session_state.editing_id is not None):
                    st.session_state.selected_cal_date = new_date
                    if cb in ["dateClick", "select"]:
                        st.session_state.editing_id = None
                    st.rerun()

    # --- INPUT FORM ---
    selected_date_str = st.session_state.get("selected_cal_date")
    
    if not selected_date_str:
        st.markdown("""
            <div style="padding:20px; text-align:center; border:2px dashed rgba(0,242,255,0.3); border-radius:15px; margin-top:20px;">
                <h3 style="color:#00f2ff;">👆 カレンダーの日付をタップしてください</h3>
                <p style="opacity:0.8;">タップした日の記録フォームがここに表示されます。</p>
            </div>
        """, unsafe_allow_html=True)
    else:
        st.success(f"📅 {selected_date_str} が選択されました。画面を下にスクロールして入力してください。")

    st.divider()
    edit_id = st.session_state.get("editing_id")
    
    col_ctx1, col_ctx2 = st.columns([3, 1])
    with col_ctx1:
        st.markdown(f"### 📅 {selected_date_str.replace('-', '/')} の{'修正' if edit_id else '新規記録'}")
    with col_ctx2:
        if st.button("キャンセル", key="cancel_form"):
            st.session_state.selected_cal_date = None
            st.session_state.editing_id = None
            st.rerun()

    col1, col2 = st.columns(2)
    with col1:
        # Check if we are editing
        edit_id = st.session_state.get("editing_id")
        edit_row = None
        if edit_id:
            edit_row_query = df[df['id'] == edit_id]
            if not edit_row_query.empty:
                edit_row = edit_row_query.iloc[0]
                player = edit_row['player']
            else:
                st.session_state.editing_id = None
                st.rerun()
        else:
            player = st.radio("プレイヤー", ["Player 1", "Player 2"], horizontal=True, key="active_player")
        
        date = datetime.strptime(st.session_state.selected_cal_date, "%Y-%m-%d")

        # Suggestions for Hall and Machine with last used defaults (Player-specific)
        last_hall, last_machine = get_last_player_defaults(df, player)
        def_hall = edit_row['hall'] if edit_row is not None else last_hall
        def_mach = edit_row['machine'] if edit_row is not None else last_machine
        
        # Define default date
        if edit_row is not None:
            try:
                def_date = pd.to_datetime(edit_row['date']).to_pydatetime()
            except:
                def_date = datetime.now(JST)
        else:
            def_date = datetime.now(JST)
        
        hall_list = sorted(df['hall'].dropna().unique().tolist())
        hall_options = ["記録しない", "新規入力..."] + hall_list
        hall = st.selectbox("ホール名", hall_options, 
                            index=(hall_options.index(last_hall) if last_hall in hall_options else 1))
        if hall == "新規入力...":
            hall = st.text_input("新しいホール名を入力", value=(def_hall if def_hall not in hall_options else ""), placeholder="例: マルハン")
        
        machine_list = sorted(df['machine'].dropna().unique().tolist())
        machine_options = ["記録しない", "新規入力..."] + machine_list
        machine = st.selectbox("機種名", machine_options, 
                               index=(machine_options.index(last_machine) if last_machine in machine_options else 1))
        if machine == "新規入力...":
            machine = st.text_input("新しい機種名を入力", value=(def_mach if def_mach not in machine_options else ""), placeholder="例: Re:ゼロ")
            

    with col2:
        game_type = st.selectbox("種別", ["スロット", "パチンコ"], 
                                 index=(0 if (edit_row is not None and edit_row['game_type'] == "スロット") else 1 if (edit_row is not None) else 0))
        
        # Dynamic labels
        label_savings = "貯メダル" if game_type == "スロット" else "貯玉"
        unit_savings = "枚" if game_type == "スロット" else "個"
        
        # Rate Selection
        st.write(f"換算レート設定 ({label_savings})")
        p_draft = st.session_state.drafts.get(player, {})
        last_r = p_draft.get("last_rate")
        
        if game_type == "スロット":
            rate_options = [5.06, 5.5]
            # Default to last used or first option
            def_idx = rate_options.index(last_r) if last_r in rate_options else 0
            rate = st.radio("交換レート (円/枚)", rate_options, index=def_idx, horizontal=True)
        else:
            rate_options = [27.0, 27.5]
            def_idx = rate_options.index(last_r) if last_r in rate_options else 0
            rate = st.radio("交換レート (個/100円)", rate_options, index=def_idx, horizontal=True)
            
        # Update last rate in draft
        if last_r != rate:
            st.session_state.drafts[player]["last_rate"] = rate
            save_drafts()

        # Input fields (Empty defaults using value=None)
        # Auto-populate Starting Savings from last Ending Savings of this hall
        hall_last_savings = get_last_hall_savings(df, player, hall)
        
        raw_invest = edit_row['invest'] if edit_row is not None else None
        invest_def = int(raw_invest) if raw_invest is not None and not pd.isna(raw_invest) else None
        invest = st.number_input("現金投資 (¥)", min_value=0, step=500, value=invest_def)
        
        # If editing, use the row's value. Otherwise, try to auto-populate from hall's last record.
        def_s_start = None
        if edit_row is not None:
            raw_s_start = edit_row.get('start_savings', 0)
            def_s_start = int(raw_s_start) if raw_s_start is not None and not pd.isna(raw_s_start) else None
        elif hall_last_savings is not None:
            def_s_start = int(hall_last_savings) if hall_last_savings is not None and not pd.isna(hall_last_savings) else None
            
        s_start = st.number_input(f"開始{label_savings} ({unit_savings})", min_value=0, step=10, value=def_s_start)
        
        raw_s_end = edit_row.get('end_savings', 0) if edit_row is not None else None
        s_end_def = int(raw_s_end) if raw_s_end is not None and not pd.isna(raw_s_end) else None
        s_end = st.number_input(f"終了{label_savings} ({unit_savings})", min_value=0, step=10, value=s_end_def)
        
        # Hidden or legacy fields (handled in save)
        # invest_val = invest or 0
        # s_start_val = s_start or 0
        # s_end_val = s_end or 0
        
        # Time Sliders with Persistence and Sync
        st.write("稼働時間設定")
        now = datetime.now(JST)
        
        # Keys for widgets
        sh_key = f"sh_widget_{player}"
        sm_key = f"sm_widget_{player}"
        eh_key = f"eh_widget_{player}"
        em_key = f"em_widget_{player}"
        check_24h_key = f"check_24h_{player}"

        # Initialize widget keys in session state if not exists
        if sh_key not in st.session_state:
            val = st.session_state.drafts.get(player, {}).get("start_hour", 9)
            st.session_state[sh_key] = max(9, min(23, val))
        if sm_key not in st.session_state:
            st.session_state[sm_key] = st.session_state.drafts.get(player, {}).get("start_min", 0)
        if eh_key not in st.session_state:
            st.session_state[eh_key] = 22
        if em_key not in st.session_state:
            st.session_state[em_key] = 0
        if check_24h_key not in st.session_state:
            st.session_state[check_24h_key] = False

        # --- Dynamic Slider Range calc ---
        start_min_h = 0 if st.session_state[check_24h_key] else 9

        col_st_time, col_ed_time = st.columns(2)
        with col_st_time:
            if st.button("開始時間"):
                if now.hour < 9:
                    st.session_state[check_24h_key] = True
                st.session_state[sh_key] = now.hour
                st.session_state[sm_key] = (now.minute // 5) * 5
                st.session_state.drafts[player]["start_hour"] = st.session_state[sh_key]
                st.session_state.drafts[player]["start_min"] = st.session_state[sm_key]
                save_drafts()
                st.rerun() 
            
            s_h = st.slider("開始時", start_min_h, 23, step=1, key=sh_key)
            s_m = st.slider("開始分", 0, 55, step=5, key=sm_key)
            
            # Update draft on slider change
            if s_h != st.session_state.drafts[player]["start_hour"] or s_m != st.session_state.drafts[player]["start_min"]:
                st.session_state.drafts[player]["start_hour"] = s_h
                st.session_state.drafts[player]["start_min"] = s_m
                save_drafts()

        with col_ed_time:
            if st.button("終了時間"):
                if now.hour < 9:
                    st.session_state[check_24h_key] = True
                st.session_state[eh_key] = now.hour
                st.session_state[em_key] = (now.minute // 5) * 5
                st.rerun()
                
            e_h = st.slider("終了時", start_min_h, 23, step=1, key=eh_key)
            e_m = st.slider("終了分", 0, 55, step=5, key=em_key)
        
        # Move checkbox here to allow button logic to update its state before rendering
        st.checkbox("深夜・24時間表示 (0時〜)", key=check_24h_key)
        
        # Calculate hours
        h_diff = (st.session_state[eh_key] + st.session_state[em_key]/60) - (st.session_state[sh_key] + st.session_state[sm_key]/60)
        if h_diff < 0: h_diff += 24
        st.write(f"稼働時間: **{h_diff:.1f}h**")
        
        # Sync widget values with session state precisely
        st.write("---")
        # Cash-Out field (Yen based)
        st.write("精算・換金 (任意)")
        raw_co_yen = edit_row.get('cash_out_yen', 0) if edit_row is not None else None
        co_yen_def = int(raw_co_yen) if raw_co_yen is not None and not pd.isna(raw_co_yen) else None
        cash_out_yen = st.number_input(f"換金した金額 (¥)", min_value=0, step=500, value=co_yen_def)
        st.write("---")

    if st.button("保存する" if not edit_id else "修正を完了する"):
        # Update last used hall/machine in drafts
        st.session_state.drafts[player]["last_hall"] = hall
        st.session_state.drafts[player]["last_machine"] = machine
        save_drafts()

        # Balance Calculation logic
        # Slot/Pachinko: (End - Start) * (100 / Rate) - Invest
        # The user confirmed 5.06/5.5 for slots are "coins per 100 yen"
        invest_val = invest if invest is not None else 0
        s_start_val = s_start if s_start is not None else 0
        s_end_val = s_end if s_end is not None else 0
        cash_out_yen_val = cash_out_yen if cash_out_yen is not None else 0
        
        calc_bal = round((s_end_val - s_start_val) * (100 / rate) - invest_val)
        
        # Format times
        s_time_str = f"{st.session_state[sh_key]:02d}:{st.session_state[sm_key]:02d}"
        e_time_str = f"{st.session_state[eh_key]:02d}:{st.session_state[em_key]:02d}"

        now_ts = datetime.now(JST)
        new_id = edit_id if edit_id else str(int(now_ts.timestamp()))
        new_row = {
            "id": new_id,
            "player": player,
            "game_type": game_type,
            "date": date.strftime("%Y-%m-%d"),
            "hall": hall,
            "machine": machine,
            "hours": round(h_diff, 1),
            "start_time": s_time_str,
            "end_time": e_time_str,
            "invest": invest_val,
            "start_savings": s_start_val,
            "end_savings": s_end_val,
            "cash_out_yen": cash_out_yen_val,
            "rate": rate,
            "balance": calc_bal,
            "memo": edit_row['memo'] if edit_row is not None else ""
        }
        
        if edit_id:
            df = df[df['id'] != edit_id] # Remove old version
        
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df)
        
        # Reset time sliders and inputs for the next entry
        st.session_state.drafts[player]["start_hour"] = 9
        st.session_state.drafts[player]["start_min"] = 0
        for k in [sh_key, sm_key, eh_key, em_key]:
            if k in st.session_state:
                del st.session_state[k]
        save_drafts()
        
        st.session_state.editing_id = None
        
        st.success("データを保存しました！")
        st.rerun()

        if edit_id:
            # Delete Button (Safe Confirmation)
            st.divider()
            del_conf_key = f"del_form_conf_{edit_id}"
            if st.session_state.get(del_conf_key):
                st.warning("この記録を本当に削除しますか？")
                c_del1, c_del2 = st.columns(2)
                if c_del1.button("はい、削除します", key="del_final_yes"):
                    df_new = df[df['id'] != edit_id]
                    save_data(df_new)
                    st.session_state.editing_id = None
                    st.session_state.selected_cal_date = None
                    del st.session_state[del_conf_key]
                    st.success("削除しました。")
                    st.rerun()
                if c_del2.button("いいえ", key="del_final_no"):
                    del st.session_state[del_conf_key]
                    st.rerun()
            else:
                if st.button("🗑️ この記録を削除する", key="del_trigger_btn"):
                    st.session_state[del_conf_key] = True
                    st.rerun()

    # --- ANALYTICS (Brief list if user still wants it?) ---
    # User requested to remove "Latest History" item and replace with calendar.
    # So we don't render render_history_list here anymore.

elif menu == "分析 (月別/年別)":
    st.subheader("収支統計")
    if df.empty:
        st.warning("データがありません。")
    else:
        # Player Filter Tabs
        tab_p1, tab_p2, tab_all = st.tabs(["Player 1", "Player 2", "全員"])
        
        # Determine current selection based on active tab
        # Note: In Streamlit, tabs handle their own content. We can define the logic inside each tab.
        
        def show_analysis(filter_p):
            if filter_p == "全員":
                df_v = df.copy()
            else:
                df_v = df[df['player'] == filter_p].copy()
            
            if df_v.empty:
                st.warning("データがありません。")
                return

            # --- Date Range Filter ---
            df_v['date_dt'] = pd.to_datetime(df_v['date'])
            min_date = df_v['date_dt'].min().date()
            max_date = df_v['date_dt'].max().date()
            
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                start_date = st.date_input(f"{filter_p} - 開始日", min_date, key=f"start_{filter_p}")
            with col_d2:
                end_date = st.date_input(f"{filter_p} - 終了日", max_date, key=f"end_{filter_p}")
            
            # Application of filter
            df_v = df_v[(df_v['date_dt'].dt.date >= start_date) & (df_v['date_dt'].dt.date <= end_date)]

            if df_v.empty:
                st.info("指定された期間のデータはありません。")
                return

            # Metrics
            t_bal = df_v['balance'].sum()
            t_hours = df_v['hours'].sum()
            h_ly = t_bal / t_hours if t_hours > 0 else 0
            
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("トータル収支", f"¥{int(t_bal):,}")
            mc2.metric("合計稼働時間", f"{t_hours:.1f}h")
            mc3.metric("平均時給", f"¥{int(h_ly):,}")
            
            # --- Periodic Summaries (3, 6, 9 months, 1 year) ---
            st.markdown("#### 直近サマリー (全期間から算出)")
            p_cols = st.columns(4)
            now_dt = pd.Timestamp.now()
            
            # Use data filtered by player but NOT by the specific date range for these "Recent" summaries
            if filter_p == "全員":
                df_recent_base = df.copy()
            else:
                df_recent_base = df[df['player'] == filter_p].copy()
            df_recent_base['date_dt'] = pd.to_datetime(df_recent_base['date'])

            for i, months in enumerate([3, 6, 9, 12]):
                start_p = now_dt - pd.DateOffset(months=months)
                label = f"{months}ヶ月" if months < 12 else "1年"
                df_p = df_recent_base[df_recent_base['date_dt'] >= start_p]
                
                p_bal = df_p['balance'].sum()
                p_hours = df_p['hours'].sum()
                p_hourly = p_bal / p_hours if p_hours > 0 else 0
                
                with p_cols[i]:
                    st.markdown(f"""
                    <div style="padding:10px; border:1px solid rgba(0,242,255,0.2); border-radius:10px; background:rgba(0,242,255,0.05); text-align:center;">
                        <div style="font-weight:bold; color:#00f2ff; font-size:0.9em;">直近{label}</div>
                        <div style="font-size:1.1em; font-weight:bold; margin:5px 0;">¥{int(p_bal):,}</div>
                        <div style="font-size:0.8em; opacity:0.8;">{p_hours:.1f}h | ¥{int(p_hourly):,}/h</div>
                    </div>
                    """, unsafe_allow_html=True)
            st.write("")

            # Yearly/Monthly aggregation
            df_v['year'] = df_v['date_dt'].dt.year
            df_v['month'] = df_v['date_dt'].dt.strftime('%Y/%m')
            
            v_type = st.radio(f"{filter_p} - 表示単位", ["月別", "年別"], horizontal=True, key=f"v_type_{filter_p}")
            g_col = 'month' if v_type == "月別" else 'year'
        
            summ = df_v.groupby(g_col).agg({
                'balance': 'sum',
                'hours': 'sum'
            }).sort_index(ascending=False)
            
            # Filter out 0 or less balance if requested
            summ = summ[summ['balance'] > 0]
            
            import numpy as np
            summ['balance'] = summ['balance'].astype(int)
            summ['時給'] = (summ['balance'] / summ['hours'].replace(0, np.nan)).fillna(0).astype(int)
            
            if summ.empty:
                st.info("条件に一致する（収支がプラスの）データがありません。")
            else:
                st.dataframe(summ.style.format({
                    'balance': '¥{:,}',
                    'hours': '{:.1f}h',
                    '時給': '¥{:,}'
                }), use_container_width=True)

        with tab_p1:
            show_analysis("Player 1")
        with tab_p2:
            show_analysis("Player 2")
        with tab_all:
            show_analysis("全員")

elif menu == "一括インポート":
    st.subheader("データの移行・取り込み")
    
    # 1. JSON/CSV ファイルからの移行
    st.write("### 1. ファイルから移行 (.json / .csv)")
    uploaded_file = st.file_uploader("ファイルを選択してください", type=["json", "csv"])
    if uploaded_file is not None:
        try:
            if uploaded_file.name.endswith(".json"):
                records_json = json.load(uploaded_file)
                import_df = pd.DataFrame(records_json)
                # Adjust column names to match Streamlit schema
                rename_map = {"gameType": "game_type", "recoveryCash": "recovery", "cashInvest": "invest"}
                import_df = import_df.rename(columns=rename_map)
            else:
                # CSV Import
                import_df = pd.read_csv(uploaded_file)
                # Ensure date format and common column mapping
                if "日付" in import_df.columns:
                    col_map = {
                        "日付": "date", "ホール": "hall", "タイプ": "game_type", 
                        "機種": "machine", "投資": "invest", "回収": "recovery", 
                        "収支": "balance", "時間": "hours", "メモ": "memo"
                    }
                    import_df = import_df.rename(columns=col_map)
            
            # Common processing for imported data
            for col in ["id", "player"]:
                if col not in import_df.columns:
                    if col == "id": import_df[col] = [str(int(datetime.now().timestamp()) + i) for i in range(len(import_df))]
                    if col == "player": import_df[col] = import_player if "import_player" in locals() else "Player 1"
            
            # Numeric conversion
            for col in ["invest", "recovery", "balance"]:
                if col in import_df.columns:
                    import_df[col] = pd.to_numeric(import_df[col].astype(str).str.replace('¥', '').str.replace(',', ''), errors='coerce').fillna(0)
            
            if "hours" in import_df.columns:
                import_df["hours"] = import_df["hours"].apply(parse_time_to_float)

            st.write("プレビュー:", import_df.head())
            if st.button("選んだデータを一括登録"):
                # Reorder columns to match main dataframe
                cols_to_keep = ["id", "player", "game_type", "date", "hall", "machine", "hours", "invest", "recovery", "balance", "memo"]
                import_df = import_df[[c for c in cols_to_keep if c in import_df.columns]]
                
                df = pd.concat([df, import_df], ignore_index=True)
                save_data(df)
                st.success(f"{len(import_df)}件のデータをインポートしました！")
        except Exception as e:
            st.error(f"読み込みエラー: {e}")

    st.divider()

    # 2. TSV Import (Manual copy-paste)
    st.write("### 2. テキスト・Excelからの取り込み (TSV形式)")
    import_player = st.radio("インポート先のプレイヤー", ["Player 1", "Player 2"], horizontal=True)
    import_data = st.text_area("テキストデータを貼り付け", height=200)
    
    if st.button("テキストを解析してインポート"):
        if import_data:
            try:
                # TSV Parsing matching user format:
                # 日付	ホール	タイプ	機種	投資	回収	収支	時間	メモ
                new_df = pd.read_csv(StringIO(import_data), sep='\t')
                
                # Column mapping and cleaning
                col_map = {
                    "日付": "date", "ホール": "hall", "タイプ": "game_type", 
                    "機種": "machine", "投資": "invest", "回収": "recovery", 
                    "収支": "balance", "時間": "hours", "メモ": "memo"
                }
                new_df = new_df.rename(columns=col_map)
                
                # Fill missing columns and select relevant ones
                for col in ["id", "player"]:
                    if col not in new_df.columns:
                        if col == "id": new_df[col] = [str(int(datetime.now().timestamp()) + i) for i in range(len(new_df))]
                        if col == "player": new_df[col] = import_player
                
                # Convert numeric columns
                for col in ["invest", "recovery", "balance"]:
                    if col in new_df.columns:
                        new_df[col] = pd.to_numeric(new_df[col].astype(str).str.replace('¥', '').str.replace(',', ''), errors='coerce').fillna(0)
                
                if "hours" in new_df.columns:
                    new_df["hours"] = new_df["hours"].apply(parse_time_to_float)
                
                # Reorder columns to match main dataframe
                cols_to_keep = ["id", "player", "game_type", "date", "hall", "machine", "hours", "invest", "recovery", "balance", "memo"]
                new_df = new_df[[c for c in cols_to_keep if c in new_df.columns]]
                
                # Merge with existing data
                df = pd.concat([df, new_df], ignore_index=True)
                save_data(df)
                st.success(f"{len(new_df)}件のデータをインポートしました！")
                st.dataframe(new_df.head())
            except Exception as e:
                st.error(f"パースエラー: {e}")

elif menu == "設定":
    st.subheader("アプリケーション設定")
    
    st.markdown("---")
    st.subheader("⚠️ データの管理")
    st.write("これまでに記録したすべてのデータを削除し、初期状態に戻します。")
    st.warning("この操作は取り消せません。実行前にバックアップ（エクスポート）を推奨します。")
    
    if st.button("すべての記録を完全に削除する"):
        empty_df = pd.DataFrame(columns=[
            "id", "player", "game_type", "date", "hall", "machine", 
            "hours", "invest", "recovery", "balance", "memo"
        ])
        save_data(empty_df)
        st.success("すべてのデータを削除しました。")
        st.rerun()
