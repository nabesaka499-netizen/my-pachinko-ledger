import streamlit as st
import pandas as pd
from datetime import datetime, timezone, timedelta, time, date
import json
import requests
import base64
from io import StringIO

try:
    import holidays
    from streamlit_calendar import calendar
    CALENDAR_AVAILABLE = True
except ImportError:
    CALENDAR_AVAILABLE = False

# --- Page Config ---
st.set_page_config(page_title="収支管理簿", page_icon="💹", layout="wide")

# --- Custom CSS (Neon Theme) ---
st.markdown("""
<style>
    .main { background-color: #0a0b1e; }
    .stApp { background: radial-gradient(circle at top right, #161b33, #0a0b1e); }
    h1, h2, h3 { color: #00f2ff !important; text-shadow: 0 0 10px rgba(0, 242, 255, 0.5); }
    .stMetric { background: rgba(0, 242, 255, 0.05) !important; border: 1px solid rgba(0, 242, 255, 0.3) !important; box-shadow: 0 0 15px rgba(0, 242, 255, 0.1); }
    .stDataFrame, .stTable { border: 1px solid rgba(0, 242, 255, 0.2); border-radius: 10px; }
    div[data-testid="stMetricValue"] > div { color: #00f2ff !important; }
</style>
""", unsafe_allow_html=True)

# --- Global Timezone (JST) ---
JST = timezone(timedelta(hours=9))

# --- Data Constants ---
GITHUB_USER = "nabesaka499-netizen"
GITHUB_REPO = "my-pachinko-ledger"
DATA_FILE = "records.csv"
DRAFT_FILE = "drafts.json"

# --- Initialization ---
if "active_p" not in st.session_state:
    st.session_state.active_p = "Player 1"
if "selected_cal_date" not in st.session_state:
    st.session_state.selected_cal_date = None
if "editing_id" not in st.session_state:
    st.session_state.editing_id = None
if "view_month" not in st.session_state:
    st.session_state.view_month = datetime.now().strftime("%Y-%m")
if "nav_lock" not in st.session_state:
    st.session_state.nav_lock = False

# --- Helper Functions ---
def get_github_auth():
    return st.secrets.get("GITHUB_TOKEN")

def load_data():
    if "records" not in st.session_state:
        token = get_github_auth()
        if token:
            try:
                url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{DATA_FILE}"
                headers = {"Authorization": f"token {token}"}
                r = requests.get(url, headers=headers)
                if r.status_code == 200:
                    content_json = r.json()
                    content = base64.b64decode(content_json["content"]).decode("utf-8")
                    df = pd.read_csv(StringIO(content))
                    st.session_state.github_sha = content_json["sha"]
                else:
                    df = pd.DataFrame()
            except Exception:
                df = pd.DataFrame()
        else:
            try:
                df = pd.read_csv(DATA_FILE)
            except Exception:
                df = pd.DataFrame()

        # Schema Fix
        expected_cols = ["id", "player", "game_type", "date", "hall", "machine", "hours", "start_time", "end_time", "invest", "start_savings", "end_savings", "cash_out_yen", "rate", "balance", "memo"]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = 0 if col in ["invest", "start_savings", "end_savings", "cash_out_yen", "balance", "hours", "rate"] else ""
        
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'], errors='coerce').dt.strftime('%Y-%m-%d')
            df = df.dropna(subset=['date'])
            num_cols = ["invest", "start_savings", "end_savings", "cash_out_yen", "balance", "hours", "rate"]
            df[num_cols] = df[num_cols].fillna(0)
        st.session_state.records = df
    return st.session_state.records

def save_data(df):
    st.session_state.records = df
    token = get_github_auth()
    if token:
        try:
            url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{DATA_FILE}"
            headers = {"Authorization": f"token {token}"}
            r_get = requests.get(url, headers=headers)
            sha = r_get.json()["sha"] if r_get.status_code == 200 else None
            csv_content = df.to_csv(index=False)
            data = {
                "message": f"Update @ {datetime.now(JST).strftime('%Y-%m-%d %H:%M')}",
                "content": base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
            }
            if sha:
                data["sha"] = sha
            res = requests.put(url, json=data, headers=headers)
            if res.status_code in [200, 201]:
                st.session_state.github_sha = res.json()["content"]["sha"]
        except Exception as e:
            st.error(f"Save Error: {e}")
    else:
        df.to_csv(DATA_FILE, index=False)

def load_drafts():
    if "drafts" not in st.session_state:
        try:
            with open(DRAFT_FILE, "r") as f:
                st.session_state.drafts = json.load(f)
        except Exception:
            st.session_state.drafts = {
                "Player 1": {"start_hour": 9, "start_min": 0, "last_hall": None, "last_machine": None, "last_rate": None},
                "Player 2": {"start_hour": 9, "start_min": 0, "last_hall": None, "last_machine": None, "last_rate": None}
            }
    return st.session_state.drafts

def save_drafts():
    try:
        with open(DRAFT_FILE, "w") as f:
            json.dump(st.session_state.drafts, f)
    except Exception:
        pass

def get_last_player_defaults(df, player):
    p_draft = load_drafts().get(player, {})
    if p_draft.get('last_hall') and p_draft.get('last_machine'):
        return p_draft['last_hall'], p_draft['last_machine']
    if not df.empty:
        p_history = df[df['player'] == player]
        if not p_history.empty:
            l = p_history.iloc[-1]
            return l['hall'], l['machine']
    return "新規入力...", "新規入力..."

def get_last_hall_savings(df, player, hall_name):
    if df.empty or not hall_name or hall_name in ["記録しない", "新規入力..."]:
        return 0
    p_df = df[(df['player'] == player) & (df['hall'] == hall_name)]
    if p_df.empty:
        return 0
    l = p_df.sort_values(by=['date', 'id'], ascending=False).iloc[0]
    return int(l.get('end_savings', 0) - (l.get('cash_out_yen', 0) / 100 * l.get('rate', 1.0)))

# --- Main Logic ---
df = load_data()
load_drafts()

# Sidebar (Title and Navigation)
st.sidebar.title("💹 収支管理簿")
menu = st.sidebar.radio("メニュー", ["ホーム・記録", "分析 (月別/年別)", "一括インポート", "設定"], label_visibility="collapsed")

# Navigation Reset
if "p_menu" not in st.session_state:
    st.session_state.p_menu = menu
if st.session_state.p_menu != menu:
    if menu == "ホーム・記録":
        st.session_state.selected_cal_date = None
        st.session_state.editing_id = None
        if "main_cal" in st.session_state:
            del st.session_state["main_cal"]
    st.session_state.p_menu = menu

if menu == "ホーム・記録":
    curr_date_str = st.session_state.get("selected_cal_date")
    
    # Strictly hide form if no date selected
    if curr_date_str is None or str(curr_date_str).lower() == "none" or curr_date_str == "":
        # --- CALENDAR VIEW ---
        c_h1, c_h2 = st.columns([1, 1])
        with c_h1:
            # Synced Player Selection
            p_idx = 0 if st.session_state.active_p == "Player 1" else 1
            st.write("### プレイヤー選択")
            p_sel = st.radio("表示プレイヤー", ["Player 1", "Player 2"], horizontal=True, index=p_idx, key="p_main")
            st.session_state.active_p = p_sel # Update state
        
        # Monthly Summary for Selected Player (Synced with Calendar View)
        v_m = st.session_state.view_month
        df_m = df.copy()
        df_m['month'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m')
        p_data = df_m[(df_m['month'] == v_m) & (df_m['player'] == st.session_state.active_p)]
        p_bal = p_data['balance'].sum()
        p_hours = p_data['hours'].sum()
        p_hourly = p_bal / p_hours if p_hours > 0 else 0
        
        with c_h2:
            try:
                m_label = datetime.strptime(v_m, "%Y-%m").strftime("%m月")
            except:
                m_label = v_m
            
            # Using 3 columns for metrics to keep it clean
            m1, m2, m3 = st.columns(3)
            m1.metric(f"{m_label}収支", f"¥{int(p_bal):,}")
            m2.metric("稼働時間", f"{p_hours:.1f}h")
            m3.metric("平均時給", f"¥{int(p_hourly):,}")
        st.divider()

        if not CALENDAR_AVAILABLE:
            st.info("カレンダー機能を準備中です。")
            def on_d_chg():
                st.session_state.selected_cal_date = st.session_state.tmp_d.strftime("%Y-%m-%d")
            st.date_input("日付を選択して記録", datetime.now(JST), key="tmp_d", on_change=on_d_chg)
        else:
            events = []
            if not df.empty:
                cal_df = df[df['player'] == st.session_state.active_p].copy()
                d_bal = cal_df.groupby('date')['balance'].sum().reset_index()
                for _, r in d_bal.iterrows():
                    b = int(r['balance'])
                    color = "#ffffff" if b >= 0 else "#ff4b4b"
                    events.append({
                        "id": f"s_{r['date']}",
                        "title": f"{'+' if b>=0 else ''}{b:,}円",
                        "start": r['date'],
                        "backgroundColor": "transparent",
                        "borderColor": "transparent",
                        "textColor": color,
                        "extendedProps": {"type": "summary", "date": r['date']}
                    })
                # Holidays
                try:
                    for d, n in holidays.Japan(years=range(2024, 2027)).items():
                        events.append({
                            "title": n,
                            "start": d.strftime("%Y-%m-%d"),
                            "display": "background",
                            "backgroundColor": "#ff4b4b1a"
                        })
                except Exception:
                    pass

            cal_opts = {
                "headerToolbar": {"left": "prev,next", "center": "title", "right": ""},
                "locale": "ja",
                "height": 700,
                "selectable": True,
                "editable": False,
                "navLinks": False,
                "selectMirror": True,
            }
            cal_res = calendar(
                events=events,
                options=cal_opts,
                custom_css=".fc-daygrid-day-number, .fc-toolbar-title { color: #00f2ff !important; } .fc-daygrid-day { cursor: pointer; }",
                callbacks=['dateClick', 'eventClick', 'select', 'datesSet'],
                key="main_cal"
            )
            
            # Click Handling
            res = cal_res
            if res and "callback" in res:
                cb = res.get("callback")
                t_d = None
                
                # 1. Capture date selection primary triggers with robust key checking
                if cb == "dateClick":
                    cd = res.get("dateClick", {})
                    t_d = cd.get("dateStr") or cd.get("date") or cd.get("start") or cd.get("startStr")
                elif cb == "select":
                    cs = res.get("select", {})
                    t_d = cs.get("startStr") or cs.get("start") or cs.get("date") or cs.get("dateStr")
                elif cb == "navLinkDayClick":
                    cn = res.get("navLinkDayClick", {})
                    t_d = cn.get("dateStr") or cn.get("date")
                elif cb == "eventClick":
                    props = res.get("eventClick", {}).get("event", {}).get("extendedProps", {})
                    if props.get("type") == "summary":
                        t_d = props.get("date")
                        day_q = cal_df[cal_df['date'] == t_d]
                        if not day_q.empty:
                            st.session_state.editing_id = day_q.iloc[0]['id']
                
                # 2. Priority 1: If a date was selected, GO to form view
                if t_d:
                    if cb != "eventClick":
                        st.session_state.editing_id = None
                    try:
                        # Reliably convert UTC ISO strings to JST to prevent 1-day offsets
                        dt = pd.to_datetime(t_d)
                        if dt.tzinfo is not None:
                            dt = dt.tz_convert('Asia/Tokyo')
                        clean_date = dt.strftime("%Y-%m-%d")
                    except Exception:
                        clean_date = str(t_d).split("T")[0]
                        
                    st.session_state.selected_cal_date = clean_date
                    st.rerun()

                # 3. Priority 2: Handle month navigation if no date was clicked
                if "view" in res or cb == "datesSet":
                    v_start = res.get("view", {}).get("activeStart")
                    if not v_start and cb == "datesSet":
                        # Sometimes activeStart is inside the datesSet object directly
                        v_start = res.get("datesSet", {}).get("startStr") or res.get("datesSet", {}).get("view", {}).get("activeStart")
                    
                    if v_start:
                        try:
                            dt_v = pd.to_datetime(v_start)
                            if dt_v.tzinfo is not None:
                                dt_v = dt_v.tz_convert('Asia/Tokyo')
                            new_view_month = dt_v.strftime("%Y-%m")
                        except Exception:
                            new_view_month = str(v_start).split("T")[0][:7]
                            
                        if st.session_state.view_month != new_view_month:
                            st.session_state.view_month = new_view_month
                            st.rerun()
    else:
        # --- FORM VIEW ---
        st.markdown(f"### 📅 {curr_date_str.replace('-', '/')} の記録")
        st.divider()
        e_id = st.session_state.get("editing_id")
        
        ctx_c1, ctx_c2 = st.columns([5, 1])
        ctx_c1.subheader("修正" if e_id else "新規記録")
        if ctx_c2.button("🔙 戻る", use_container_width=True):
            st.session_state.selected_cal_date = None
            st.session_state.editing_id = None
            if "main_cal" in st.session_state:
                del st.session_state["main_cal"]
            st.rerun()

        e_row = df[df['id'] == e_id].iloc[0] if e_id and not df[df['id'] == e_id].empty else None
        
        col1, col2 = st.columns(2)
        with col1:
            # Sync player state from home screen
            f_p = st.session_state.active_p
            
            h_list = sorted(df['hall'].dropna().unique().tolist())
            last_h, last_m = get_last_player_defaults(df, f_p)
            h_idx = (h_list.index(last_h)+1) if last_h in h_list else 0
            hall = st.selectbox("ホール名", ["新規入力..."] + h_list, index=h_idx)
            if hall == "新規入力...":
                hall = st.text_input("ホール名を入力", value=(e_row['hall'] if e_row is not None else ""))
            
            m_list = sorted(df['machine'].dropna().unique().tolist())
            m_idx = (m_list.index(last_m)+1) if last_m in m_list else 0
            mach = st.selectbox("機種名", ["新規入力..."] + m_list, index=m_idx)
            if mach == "新規入力...":
                mach = st.text_input("機種名を入力", value=(e_row['machine'] if e_row is not None else ""))
            memo = st.text_area("メモ", value=(e_row['memo'] if e_row is not None else ""))

        with col2:
            gt_idx = 0 if e_row is None or e_row['game_type'] == "スロット" else 1
            gt = st.radio("種別", ["スロット", "パチンコ"], horizontal=True, index=gt_idx)
            
            r_idx = 0
            if e_row is not None and e_row['rate'] in [5.06, 5.5, 27.0, 27.5]:
                r_idx = [5.06, 5.5, 27.0, 27.5].index(e_row['rate'])
            rate = st.radio("交換率", [5.06, 5.5, 27.0, 27.5], horizontal=True, index=r_idx)
            
            invest = st.number_input("投資 (¥)", min_value=0, step=500, value=int(e_row['invest']) if e_row is not None else 0)
            l_sav = get_last_hall_savings(df, f_p, hall)
            s_s = st.number_input("開始貯メダル/玉", min_value=0, value=int(e_row['start_savings'] if e_row is not None else l_sav))
            s_e = st.number_input("終了貯メダル/玉", min_value=0, value=int(e_row['end_savings'] if e_row is not None else 0))
            
            # --- Start and End Time Inputs ---
            default_start = time(10, 0)
            default_end = time(12, 0)
            if e_row is not None and pd.notna(e_row.get('start_time')) and e_row['start_time']:
                try:
                    default_start = datetime.strptime(e_row['start_time'], "%H:%M").time()
                except Exception:
                    pass
            if e_row is not None and pd.notna(e_row.get('end_time')) and e_row['end_time']:
                try:
                    default_end = datetime.strptime(e_row['end_time'], "%H:%M").time()
                except Exception:
                    pass

            c_t1, c_t2 = st.columns(2)
            with c_t1:
                start_time = st.time_input("開始時間", value=default_start)
            with c_t2:
                end_time = st.time_input("終了時間", value=default_end)
            
            # Dynamic hours calculation (handling cross-midnight)
            dummy_d = date.today()
            dt_start = datetime.combine(dummy_d, start_time)
            dt_end = datetime.combine(dummy_d, end_time)
            if dt_end < dt_start:
                dt_end += timedelta(days=1)
            
            delta_hr = (dt_end - dt_start).total_seconds() / 3600.0
            st.info(f"⏳ **稼働時間: {delta_hr:.1f} 時間** (保存前に確認)")

        if st.button("保存する", use_container_width=True, type="primary"):
            bal = round((s_e - s_s) * (100 / rate) - invest)
            n_row = {
                "id": e_id if e_id else str(int(datetime.now().timestamp())),
                "player": f_p, "game_type": gt, "date": str(curr_date_str),
                "hall": hall, "machine": mach, "hours": round(delta_hr, 1),
                "invest": invest, "start_savings": s_s, "end_savings": s_e,
                "rate": rate, "balance": bal, "memo": memo,
                "start_time": start_time.strftime("%H:%M"), "end_time": end_time.strftime("%H:%M"), "cash_out_yen": 0
            }
            if e_id:
                df = df[df['id'] != e_id]
            df = pd.concat([df, pd.DataFrame([n_row])], ignore_index=True)
            save_data(df)
            
            # Save defaults
            drafts = load_drafts()
            drafts[f_p].update({"last_hall": hall, "last_machine": mach, "last_rate": rate})
            save_drafts()
            
            st.session_state.selected_cal_date = None
            st.session_state.editing_id = None
            if "main_cal" in st.session_state:
                del st.session_state["main_cal"]
            st.success("保存完了！")
            st.rerun()

        if e_id:
            if st.button("🗑️ 記録を削除"):
                df = df[df['id'] != e_id]
                save_data(df)
                st.session_state.selected_cal_date = None
                st.session_state.editing_id = None
                if "main_cal" in st.session_state:
                    del st.session_state["main_cal"]
                st.rerun()

elif menu == "分析 (月別/年別)":
    st.subheader("収支統計")
    if df.empty:
        st.warning("データがありません。")
    else:
        # Player Filter Tabs
        tab_p1, tab_p2, tab_all = st.tabs(["Player 1", "Player 2", "全員"])
        
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
            
            import numpy as np
            summ['balance'] = summ['balance'].astype(int)
            summ['時給'] = (summ['balance'] / summ['hours'].replace(0, np.nan)).fillna(0).astype(int)
            
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
    st.subheader("一括インポート")
    u = st.file_uploader("CSVを選択", type="csv")
    if u and st.button("インポート実行"):
        df = pd.concat([df, pd.read_csv(u)], ignore_index=True)
        save_data(df)
        st.success("完了")

elif menu == "設定":
    st.subheader("設定")
    if st.button("⚠️ 全データ初期化"):
        save_data(pd.DataFrame(columns=df.columns))
        st.success("初期化完了")
        st.rerun()
