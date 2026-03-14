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
SAVINGS_FILE = "savings.csv"

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
if "preview_date" not in st.session_state:
    st.session_state.preview_date = None
if "tentative_date" not in st.session_state:
    st.session_state.tentative_date = None

# --- Helper Functions ---
def get_github_auth():
    try:
        return st.secrets.get("GITHUB_TOKEN")
    except Exception:
        return None

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

        st.session_state.records = df

    # セッションから取得したdfに対してもスキーマ保証と型キャストを行う（キャッシュ後続のアプデ対策）
    df = st.session_state.records.copy()
    expected_cols = [
        "id", "player", "game_type", "date", "hall", "machine",
        "hours", "invest", "recovery", "balance", "memo",
        "start_savings", "end_savings", "rate", "cash_out_yen",
        "start_time", "end_time"
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = 0 if col in ["invest", "recovery", "balance", "start_savings", "end_savings",
                                    "cash_out_yen", "hours", "rate"] else ""
    
    if not df.empty:
        df['player'] = df['player'].astype(str).str.strip()
        num_cols = ["invest", "recovery", "balance", "start_savings", "end_savings", "rate", "cash_out_yen", "hours"]
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
        str_cols = ["player", "game_type", "hall", "machine", "memo", "start_time", "end_time"]
        for col in str_cols:
            if col in df.columns:
                df[col] = df[col].fillna("")
        
        if 'date' in df.columns:
            try:
                df['date'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m-%d')
            except: pass

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

def load_savings():
    if "savings" not in st.session_state:
        token = get_github_auth()
        if token:
            try:
                url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{SAVINGS_FILE}"
                headers = {"Authorization": f"token {token}"}
                r = requests.get(url, headers=headers)
                if r.status_code == 200:
                    content_json = r.json()
                    content = base64.b64decode(content_json["content"]).decode("utf-8")
                    df = pd.read_csv(StringIO(content))
                    st.session_state.github_sha_savings = content_json["sha"]
                else:
                    df = pd.DataFrame()
            except Exception:
                df = pd.DataFrame()
        else:
            try:
                df = pd.read_csv(SAVINGS_FILE)
            except Exception:
                df = pd.DataFrame()

        st.session_state.savings = df

    df_s = st.session_state.savings.copy()
    expected_cols_s = ["id", "player", "hall", "saved_medals", "saved_balls", "medal_rate", "ball_rate", "updated_at"]
    for col in expected_cols_s:
        if col not in df_s.columns:
            df_s[col] = 0.0 if col in ["medal_rate", "ball_rate"] else (0 if col in ["saved_medals", "saved_balls"] else "")
    
    st.session_state.savings = df_s
    return st.session_state.savings

def save_savings(df):
    st.session_state.savings = df
    token = get_github_auth()
    if token:
        try:
            url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/contents/{SAVINGS_FILE}"
            headers = {"Authorization": f"token {token}"}
            r_get = requests.get(url, headers=headers)
            sha = r_get.json()["sha"] if r_get.status_code == 200 else None
            csv_content = df.to_csv(index=False)
            data = {
                "message": f"Update savings @ {datetime.now(JST).strftime('%Y-%m-%d %H:%M')}",
                "content": base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
            }
            if sha:
                data["sha"] = sha
            res = requests.put(url, json=data, headers=headers)
            if res.status_code in [200, 201]:
                st.session_state.github_sha_savings = res.json()["content"]["sha"]
        except Exception as e:
            st.error(f"Save Error: {e}")
    else:
        df.to_csv(SAVINGS_FILE, index=False)

def load_drafts():
    if "drafts" not in st.session_state:
        try:
            with open(DRAFT_FILE, "r") as f:
                st.session_state.drafts = json.load(f)
        except Exception:
            st.session_state.drafts = {
                "Player 1": {"start_hour": 9, "start_min": 0, "last_hall": None,
                              "last_machine": None, "last_rate": None},
                "Player 2": {"start_hour": 9, "start_min": 0, "last_hall": None,
                              "last_machine": None, "last_rate": None}
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

def get_last_hall_savings(df_s, player, hall_name, game_type="スロット"):
    if df_s.empty or not hall_name or hall_name in ["記録しない", "新規入力..."]:
        return 0
    p_df = df_s[(df_s['player'] == player) & (df_s['hall'] == hall_name)]
    if p_df.empty:
        return 0
    l = p_df.iloc[0]
    if game_type == "スロット":
        return int(l.get('saved_medals', 0))
    else:
        return int(l.get('saved_balls', 0))

# --- Main Logic ---
df = load_data()
df_s = load_savings()
load_drafts()

# ============================================================
# Sidebar
# ============================================================
st.sidebar.title("💹 収支管理簿")
menu = st.sidebar.radio(
    "メニュー",
    ["ホーム・記録", "分析 (月別/年別)", "貯玉・貯メダル管理", "一括インポート", "設定"],
    label_visibility="collapsed"
)

# Navigation Reset
if "p_menu" not in st.session_state:
    st.session_state.p_menu = menu
if st.session_state.p_menu != menu:
    if menu in ["ホーム・記録", "貯玉・貯メダル管理"]:
        st.session_state.selected_cal_date = None
        st.session_state.editing_id = None
        for k in list(st.session_state.keys()):
            if str(k).startswith("main_cal"):
                del st.session_state[k]
    st.session_state.p_menu = menu

# ============================================================
# ホーム・記録
# ============================================================
if menu == "ホーム・記録":
    curr_date_str = st.session_state.get("selected_cal_date")
    p_date = st.session_state.get("preview_date")

    # 1. フォーム表示モード (新規追加 / 編集)
    if curr_date_str and str(curr_date_str).lower() != "none":
        st.markdown(f"### 📅 {curr_date_str.replace('-', '/')} の記録")
        st.divider()

        e_id = st.session_state.get("editing_id")

        ctx_c1, ctx_c2 = st.columns([5, 1])
        ctx_c1.subheader("修正" if e_id else "新規記録")
        if ctx_c2.button("🔙 戻る", use_container_width=True):
            st.session_state.selected_cal_date = None
            st.session_state.editing_id = None
            st.session_state.preview_date = None
            for k in list(st.session_state.keys()):
                if str(k).startswith("main_cal"):
                    del st.session_state[k]
            st.rerun()

        e_row = None
        if e_id:
            matched = df[
                (df['id'] == e_id) &
                (df['player'].astype(str).str.strip() == st.session_state.active_p)
            ]
            if not matched.empty:
                e_row = matched.iloc[0]

        f_p = st.session_state.active_p

        col1, col2 = st.columns(2)
        with col1:
            h_list = sorted(df['hall'].dropna().unique().tolist())
            last_h, last_m = get_last_player_defaults(df, f_p)
            h_idx = (h_list.index(last_h) + 1) if last_h in h_list else 0
            hall = st.selectbox("ホール名", ["新規入力..."] + h_list, index=h_idx)
            if hall == "新規入力...":
                hall = st.text_input("ホール名を入力",
                                     value=(e_row['hall'] if e_row is not None else ""))

            m_list = sorted(df['machine'].dropna().unique().tolist())
            m_idx = (m_list.index(last_m) + 1) if last_m in m_list else 0
            mach = st.selectbox("機種名", ["新規入力..."] + m_list, index=m_idx)
            if mach == "新規入力...":
                mach = st.text_input("機種名を入力",
                                     value=(e_row['machine'] if e_row is not None else ""))

            memo = st.text_area("メモ", value=(e_row['memo'] if e_row is not None else ""))

        with col2:
            gt_idx = 0 if e_row is None or e_row['game_type'] == "スロット" else 1
            gt = st.radio("種別", ["スロット", "パチンコ"], horizontal=True, index=gt_idx)

            r_idx = 0
            if e_row is not None and e_row['rate'] in [5.06, 5.5, 27.0, 27.5]:
                r_idx = [5.06, 5.5, 27.0, 27.5].index(e_row['rate'])
            else:
                hall_history = df[df['hall'] == hall]
                if not hall_history.empty:
                    last_hall_rate = hall_history.iloc[-1]['rate']
                    if last_hall_rate in [5.06, 5.5, 27.0, 27.5]:
                        r_idx = [5.06, 5.5, 27.0, 27.5].index(last_hall_rate)
                else:
                    drafts = load_drafts()
                    l_r = drafts.get(f_p, {}).get("last_rate")
                    if l_r in [5.06, 5.5, 27.0, 27.5]:
                        r_idx = [5.06, 5.5, 27.0, 27.5].index(l_r)
            rate = st.radio("交換率", [5.06, 5.5, 27.0, 27.5], horizontal=True, index=r_idx)

            invest = st.number_input("投資 (¥)", min_value=0, step=500,
                                     value=int(e_row['invest']) if e_row is not None else 0)
            cash_out = st.number_input("換金額 (回収) (¥)", min_value=0, step=500,
                                       value=int(e_row.get('cash_out_yen', 0)) if e_row is not None else 0)
            l_sav = get_last_hall_savings(df_s, f_p, hall, gt)
            s_s = st.number_input("開始貯メダル/玉", min_value=0,
                                  value=int(e_row['start_savings'] if e_row is not None else l_sav))
            s_e = st.number_input("終了貯メダル/玉", min_value=0,
                                  value=int(e_row['end_savings'] if e_row is not None else 0))

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

            dummy_d = date.today()
            dt_start = datetime.combine(dummy_d, start_time)
            dt_end = datetime.combine(dummy_d, end_time)
            if dt_end < dt_start:
                dt_end += timedelta(days=1)
            delta_hr = (dt_end - dt_start).total_seconds() / 3600.0
            st.info(f"⏳ **稼働時間: {delta_hr:.1f} 時間** (保存前に確認)")

        if st.button("保存する", use_container_width=True, type="primary"):
            bal = round((s_e - s_s) * (100 / rate) - invest) + cash_out
            n_row = {
                "id": e_id if e_id else str(int(datetime.now().timestamp())),
                "player": f_p,
                "game_type": gt,
                "date": str(curr_date_str),
                "hall": hall,
                "machine": mach,
                "hours": round(delta_hr, 1),
                "invest": invest,
                "recovery": cash_out,
                "balance": bal,
                "memo": memo,
                "start_savings": s_s,
                "end_savings": s_e,
                "rate": rate,
                "cash_out_yen": cash_out,
                "start_time": start_time.strftime("%H:%M"),
                "end_time": end_time.strftime("%H:%M")
            }
            if e_id:
                df = df[df['id'] != e_id]
            df = pd.concat([df, pd.DataFrame([n_row])], ignore_index=True)
            save_data(df)

            updated = False
            for idx, row in df_s.iterrows():
                if row['player'] == f_p and row['hall'] == hall:
                    if gt == "スロット":
                        df_s.at[idx, 'saved_medals'] = s_e
                        df_s.at[idx, 'medal_rate'] = float(rate)
                    else:
                        df_s.at[idx, 'saved_balls'] = s_e
                        df_s.at[idx, 'ball_rate'] = float(rate)
                    df_s.at[idx, 'updated_at'] = datetime.now(JST).strftime('%Y-%m-%d %H:%M')
                    updated = True
                    break

            if not updated and s_e > 0:
                new_s_row = {
                    "id": str(int(datetime.now().timestamp())),
                    "player": f_p,
                    "hall": hall,
                    "saved_medals": s_e if gt == "スロット" else 0,
                    "saved_balls": s_e if gt == "パチンコ" else 0,
                    "medal_rate": float(rate) if gt == "スロット" else 0.0,
                    "ball_rate": float(rate) if gt == "パチンコ" else 0.0,
                    "updated_at": datetime.now(JST).strftime('%Y-%m-%d %H:%M')
                }
                df_s = pd.concat([df_s, pd.DataFrame([new_s_row])], ignore_index=True)

            save_savings(df_s)
            drafts = load_drafts()
            drafts[f_p].update({"last_hall": hall, "last_machine": mach, "last_rate": rate})
            save_drafts()

            st.session_state.selected_cal_date = None
            st.session_state.editing_id = None
            for k in list(st.session_state.keys()):
                if str(k).startswith("main_cal"):
                    del st.session_state[k]
            st.success("保存完了！")
            st.rerun()

        if e_id:
            if st.button("🗑️ 記録を削除"):
                target = df[(df['id'] == e_id) & (df['player'].astype(str).str.strip() == f_p)]
                if not target.empty:
                    df = df[df['id'] != e_id]
                    save_data(df)
                st.session_state.selected_cal_date = None
                st.session_state.editing_id = None
                for k in list(st.session_state.keys()):
                    if str(k).startswith("main_cal"):
                        del st.session_state[k]
                st.rerun()

    # 2. カレンダー / 詳細表示モード
    else:
        # --- TOP SECTION (Metrics & Navigation) ---
        if p_date:
            st.write(f"### 👤 {st.session_state.active_p}")
            c_top = st.container()
        else:
            c_h1, c_h2 = st.columns([1, 1])
            with c_h1:
                p_idx = 0 if st.session_state.active_p == "Player 1" else 1
                st.write("### プレイヤー選択")
                p_sel = st.radio("表示プレイヤー", ["Player 1", "Player 2"],
                                horizontal=True, index=p_idx, key="p_main")
                if p_sel != st.session_state.active_p:
                    st.session_state.active_p = p_sel
                    st.session_state.preview_date = None
                    if "records" in st.session_state:
                        del st.session_state["records"]
                    st.rerun()
            c_top = c_h2 # c_h1/c_h2 を利用

        # Monthly Summary calculation (always needed)
        v_m = st.session_state.view_month
        v_dt = pd.to_datetime(v_m + "-01")
        df_all = load_data()
        if not df_all.empty:
            df_m = df_all.copy()
            df_m['month'] = pd.to_datetime(df_m['date']).dt.strftime('%Y-%m')
            p_data = df_m[
                (df_m['month'] == v_m) & 
                (df_m['player'].astype(str).str.strip() == st.session_state.active_p)
            ]
            p_bal = p_data['balance'].sum()
            p_hours = p_data['hours'].sum()
            p_hourly = p_bal / p_hours if p_hours > 0 else 0
        else:
            p_bal, p_hours, p_hourly = 0, 0, 0

        with c_top:
            m1, m2, m3 = st.columns(3)
            m1.metric(f"{v_dt.strftime('%m月')}収支", f"¥{int(p_bal):,}")
            m2.metric("稼働時間", f"{p_hours:.1f}h")
            m3.metric("平均時給", f"¥{int(p_hourly):,}")

        st.divider()

        # Navigation
        nav_c1, nav_c2, nav_c3 = st.columns([1, 6, 1])
        with nav_c1:
            if st.button("◀ 前月", use_container_width=True):
                st.session_state.view_month = (v_dt - pd.DateOffset(months=1)).strftime("%Y-%m")
                for k in list(st.session_state.keys()):
                    if str(k).startswith("main_cal"):
                        del st.session_state[k]
                st.rerun()
        with nav_c2:
            sign = "+" if p_bal > 0 else ""
            bal_color = "#00f2ff" if p_bal >= 0 else "#ff4b4b"
            bal_text = f"{sign}{int(p_bal):,}円"
            st.markdown(
                f"<h3 style='text-align: center; color: #00f2ff; margin-top: 0;'>"
                f"{v_dt.strftime('%Y年%m月')} <span style='color: {bal_color}; margin-left: 20px;'>{bal_text}</span>"
                f"</h3>", 
                unsafe_allow_html=True
            )
        with nav_c3:
            if st.button("次月 ▶", use_container_width=True):
                st.session_state.view_month = (v_dt + pd.DateOffset(months=1)).strftime("%Y-%m")
                for k in list(st.session_state.keys()):
                    if str(k).startswith("main_cal"):
                        del st.session_state[k]
                st.rerun()
        
        # --- [案A] 選択中の日の詳細への誘導ボタン用プレースホルダー ---
        btn_placeholder = st.empty()
        
        if not st.session_state.get('tentative_date') and not st.session_state.preview_date:
             btn_placeholder.info("💡 カレンダーの日付をタップして選択してください。")

        # --- PREVIEW SECTION ---
        if p_date:
            st.markdown(f"### 🔍 {p_date.replace('-', '/')} の記録詳細")
            if not df.empty and 'player' in df.columns:
                day_records = df[
                    (df['date'] == p_date) &
                    (df['player'].astype(str).str.strip() == st.session_state.active_p)
                ]
            else:
                day_records = pd.DataFrame()

            if day_records.empty:
                st.info("この日の記録はありません。")
            else:
                for idx, row in day_records.iterrows():
                    with st.container(border=True):
                        c0, c1, c2, c3 = st.columns([3, 3, 3, 3])
                        c0.markdown(f"**店舗:** {row['hall']}")
                        c1.markdown(f"**時間:** {row.get('start_time', '--')} - {row.get('end_time', '--')}")
                        c2.markdown(f"**収支:** ¥{int(row['balance']):,}")
                        
                        btn_col1, btn_col2 = c3.columns(2)
                        if btn_col1.button("✏️ 編集", key=f"edit_{row['id']}", use_container_width=True):
                            st.session_state.editing_id = row['id']
                            st.session_state.selected_cal_date = p_date
                            st.session_state.preview_date = None
                            st.rerun()
                        if btn_col2.button("🗑️", key=f"del_{row['id']}", type="primary", use_container_width=True):
                            if row['player'].astype(str).str.strip() == st.session_state.active_p:
                                df = df[df['id'] != row['id']]
                                save_data(df)
                                st.success("削除しました。")
                                st.rerun()

            st.write("")
            col_a1, col_a2 = st.columns([4, 1])
            with col_a1:
                if st.button("➕ この日に新規記録を追加", use_container_width=True, type="primary"):
                    st.session_state.selected_cal_date = p_date
                    st.session_state.editing_id = None
                    st.session_state.preview_date = None
                    st.rerun()
            with col_a2:
                if st.button("✖ 閉じる", use_container_width=True):
                    st.session_state.preview_date = None
                    st.session_state.tentative_date = None
                    st.rerun()
            st.markdown("---")

        # --- CALENDAR ---
        if not CALENDAR_AVAILABLE:
            st.info("カレンダー機能を準備中です。")
            st.date_input("日付を選択して記録", datetime.now(JST), key="tmp_d", on_change=lambda: st.session_state.update({"selected_cal_date": st.session_state.tmp_d.strftime("%Y-%m-%d")}))
        else:
            events = []
            custom_css = ".fc-daygrid-day-number, .fc-toolbar-title { color: #00f2ff !important; } .fc-daygrid-day { cursor: pointer; } .fc-col-header-cell-cushion { cursor: default; } .fc-day-sat .fc-col-header-cell-cushion, .fc-day-sat .fc-daygrid-day-number { color: #4b8bff !important; } .fc-day-sun .fc-col-header-cell-cushion, .fc-day-sun .fc-daygrid-day-number { color: #ff4b4b !important; } .fc-event { border: none !important; background: transparent !important; } .fc-event-main { padding: 0 !important; text-align: center; } .fc-event-title { white-space: pre-wrap !important; word-wrap: break-word !important; font-size: clamp(0.6rem, 2.5vw, 0.9rem) !important; line-height: 1.1 !important; letter-spacing: -0.5px !important; } .fc-day-today { background: transparent !important; }"
            
            if not df.empty:
                cal_df = df[df['player'].astype(str).str.strip() == st.session_state.active_p].copy()
                d_bal = cal_df.groupby('date')['balance'].sum().reset_index()
                for _, r in d_bal.iterrows():
                    b = int(r['balance'])
                    color = "#ffffff" if b >= 0 else "#ff4b4b"
                    events.append({"id": f"s_{r['date']}", "title": f"{'+' if b >= 0 else ''}{b:,}円", "start": r['date'], "backgroundColor": "transparent", "borderColor": "transparent", "textColor": color, "extendedProps": {"type": "summary", "date": r['date']}})
            
            try:
                for d, n in holidays.Japan(years=range(2024, 2027)).items():
                    date_str = d.strftime("%Y-%m-%d")
                    events.append({"title": n, "start": date_str, "display": "background", "backgroundColor": "#ff4b4b1a"})
                    custom_css += f'.fc-day[data-date="{date_str}"] .fc-daygrid-day-number {{ color: #ff4b4b !important; }}\n'
            except: pass

            # 選択中の日付(tentative_date)をハイライト
            if st.session_state.get('tentative_date'):
                custom_css += f'.fc-day[data-date="{st.session_state.tentative_date}"] {{ background: rgba(0, 242, 255, 0.2) !important; border: 2px solid #00f2ff !important; }}\n'
            
            # プレビュー表示中はカレンダーの高さを少し抑える
            cal_height = 500 if st.session_state.preview_date else 700

            cal_res = calendar(
                events=events,
                options={
                    "headerToolbar": False,
                    "initialDate": f"{st.session_state.view_month}-01",
                    "firstDay": int((v_dt.dayofweek + 1) % 7),
                    "locale": "ja",
                    "height": cal_height,
                    "selectable": False,
                    "editable": False
                },
                custom_css=custom_css,
                callbacks=['dateClick', 'eventClick', 'select'],
                key=f"main_cal_{st.session_state.view_month}_{st.session_state.active_p}"
            )
            if cal_res and "callback" in cal_res:
                cb = cal_res.get("callback")
                t_d = None
                
                # イベントデータから日付を抽出する統合ロジック
                if cb == "dateClick":
                    t_d = cal_res.get("dateClick", {}).get("dateStr") or cal_res.get("dateClick", {}).get("date")
                elif cb == "select":
                    t_d = cal_res.get("select", {}).get("startStr") or cal_res.get("select", {}).get("start")
                elif cb == "eventClick":
                    props = cal_res.get("eventClick", {}).get("event", {}).get("extendedProps", {})
                    if props.get("type") == "summary":
                        t_d = props.get("date")
                
                if t_d:
                    # 日付文字列の正規化（タイムゾーンを考慮してJSTに変換）
                    try:
                        ts = pd.to_datetime(t_d)
                        if ts.tzinfo is not None:
                            ts = ts.astimezone(JST)
                        clean_date = ts.strftime("%Y-%m-%d")
                    except:
                        clean_date = str(t_d).split("T")[0]
                    
                    # すでに選択中の日を再度クリックした場合は、詳細を開く（ダブルクリック対応）
                    if st.session_state.get('tentative_date') == clean_date:
                        st.session_state.preview_date = clean_date
                        st.session_state.tentative_date = None
                        st.session_state.selected_cal_date = None
                        st.session_state.editing_id = None
                        st.rerun()
                    else:
                        # 別の日の場合は選択状態を更新
                        st.session_state.tentative_date = clean_date
                        st.rerun()

            # --- プレースホルダーの中身を更新 (現在の状態を反映) ---
            if st.session_state.get('tentative_date'):
                t_date = st.session_state.tentative_date
                try:
                    display_date = datetime.strptime(t_date, "%Y-%m-%d").strftime("%m/%d")
                except:
                    display_date = t_date
                
                with btn_placeholder.container(border=True):
                    st.markdown(f"#### 📍 選択中: {display_date}")
                    if st.button(f"👉 {display_date} の詳細を表示 / 記録を追加", use_container_width=True, type="primary"):
                        st.session_state.preview_date = t_date
                        st.session_state.tentative_date = None
                        st.session_state.selected_cal_date = None
                        st.session_state.editing_id = None
                        st.rerun()

# ============================================================
# 分析
# ============================================================
elif menu == "分析 (月別/年別)":
    st.subheader("収支統計")
    if df.empty:
        st.warning("データがありません。")
    else:
        tab_p1, tab_p2, tab_all = st.tabs(["Player 1", "Player 2", "全員"])

        def show_analysis(filter_p):
            if filter_p == "全員":
                df_base = df.copy()
            else:
                df_base = df[df['player'].astype(str).str.strip() == filter_p].copy()

            if df_base.empty:
                st.warning("データがありません。")
                return

            df_base['date_dt'] = pd.to_datetime(df_base['date'])
            min_date = df_base['date_dt'].min().date()
            max_date = df_base['date_dt'].max().date()

            # --- プレースホルダーを使用して表示順序を制御 ---
            table_container = st.container()
            summary_container = st.container()
            total_container = st.container()
            date_range_picker_container = st.container()

            # 最下に日付選択を配置（ただし、計算のために初期化だけ先に行う）
            with date_range_picker_container:
                st.write("")
                st.markdown("---")
                col_d1, col_d2 = st.columns(2)
                with col_d1:
                    start_date = st.date_input(f"{filter_p} - 開始日", min_date, key=f"start_{filter_p}")
                with col_d2:
                    end_date = st.date_input(f"{filter_p} - 終了日", max_date, key=f"end_{filter_p}")

            # フィルタリング適用
            df_v = df_base[
                (df_base['date_dt'].dt.date >= start_date) &
                (df_base['date_dt'].dt.date <= end_date)
            ].copy()

            # 1. 月別・年別の詳細表 (最上部)
            with table_container:
                if df_v.empty:
                    st.info("指定された期間のデータはありません。")
                else:
                    df_v['year'] = df_v['date_dt'].dt.year
                    df_v['month'] = df_v['date_dt'].dt.strftime('%Y/%m')

                    v_type = st.radio(f"{filter_p} - 表示単位", ["月別", "年別"],
                                       horizontal=True, key=f"v_type_{filter_p}")
                    g_col = 'month' if v_type == "月別" else 'year'

                    import numpy as np
                    summ = df_v.groupby(g_col).agg({'balance': 'sum', 'hours': 'sum'}).sort_index(ascending=False)
                    summ['balance'] = summ['balance'].astype(int)
                    summ['時給'] = (summ['balance'] / summ['hours'].replace(0, np.nan)).fillna(0).astype(int)

                    st.dataframe(summ.style.format({
                        'balance': '¥{:,}',
                        'hours': '{:.1f}h',
                        '時給': '¥{:,}'
                    }), use_container_width=True)

            # 2. 直近サマリー
            with summary_container:
                st.markdown("#### ✨ 直近サマリー (全期間から算出)")
                p_recent_cols = st.columns(4)
                now_dt = pd.Timestamp.now()

                for i, months in enumerate([3, 6, 9, 12]):
                    start_p = now_dt - pd.DateOffset(months=months)
                    label = f"{months}ヶ月" if months < 12 else "1年"
                    df_p = df_base[df_base['date_dt'] >= start_p]

                    p_bal_recent = df_p['balance'].sum()
                    p_hours_recent = df_p['hours'].sum()
                    p_hourly_recent = p_bal_recent / p_hours_recent if p_hours_recent > 0 else 0

                    with p_recent_cols[i]:
                        st.markdown(f"""
                        <div style="padding:10px; border:1px solid rgba(0,242,255,0.2);
                                    border-radius:10px; background:rgba(0,242,255,0.05); text-align:center;">
                            <div style="font-weight:bold; color:#00f2ff; font-size:0.9em;">直近{label}</div>
                            <div style="font-size:1.1em; font-weight:bold; margin:5px 0;">¥{int(p_bal_recent):,}</div>
                            <div style="font-size:0.8em; opacity:0.8;">{p_hours_recent:.1f}h | ¥{int(p_hourly_recent):,}/h</div>
                        </div>
                        """, unsafe_allow_html=True)
                st.write("")

            # 3. トータル収支
            with total_container:
                if not df_v.empty:
                    t_bal = df_v['balance'].sum()
                    t_hours = df_v['hours'].sum()
                    h_ly = t_bal / t_hours if t_hours > 0 else 0

                    mc1, mc2, mc3 = st.columns(3)
                    # ユーザー要望の「トータル収支」名称に合わせて、フィルタリング後であることを明記
                    mc1.metric("トータル収支 (指定期間)", f"¥{int(t_bal):,}")
                    mc2.metric("合計稼働時間", f"{t_hours:.1f}h")
                    mc3.metric("平均時給", f"¥{int(h_ly):,}")

        with tab_p1:
            show_analysis("Player 1")
        with tab_p2:
            show_analysis("Player 2")
        with tab_all:
            show_analysis("全員")

# ============================================================
# 貯玉・貯メダル管理
# ============================================================
elif menu == "貯玉・貯メダル管理":
    st.subheader("貯玉・貯メダル管理")

    p_idx = 0 if st.session_state.active_p == "Player 1" else 1
    p_sel = st.radio("表示プレイヤー", ["Player 1", "Player 2"],
                     horizontal=True, index=p_idx, key="p_savings")
    st.session_state.active_p = p_sel

    # 円評価額の計算ロジック
    p_savings = df_s[df_s['player'] == p_sel].copy()
    
    def calc_yen(row, rate_col, amt_col):
        rate = row.get(rate_col, 0)
        amt = row.get(amt_col, 0)
        if pd.isna(rate) or rate <= 0:
            return 0
        return int((amt / rate) * 100)

    p_savings['メダル評価額 (¥)'] = p_savings.apply(lambda r: calc_yen(r, 'medal_rate', 'saved_medals'), axis=1)
    p_savings['玉評価額 (¥)'] = p_savings.apply(lambda r: calc_yen(r, 'ball_rate', 'saved_balls'), axis=1)
    p_savings['合計評価額 (¥)'] = p_savings['メダル評価額 (¥)'] + p_savings['玉評価額 (¥)']

    total_yen = p_savings['合計評価額 (¥)'].sum()
    st.metric(f"💰 {p_sel} の総資産 (円評価額)", f"¥{total_yen:,}")
    st.divider()

    st.markdown("### 📊 貯玉・貯メダル一覧 (編集・削除可能)")
    st.info("セルをクリックして直接数値を編集できます。行の追加（下部）や削除（選択してDelete）も可能です。")

    edit_df = p_savings[['hall', 'saved_medals', 'saved_balls', 'medal_rate', 'ball_rate']].copy()
    
    edited_df = st.data_editor(
        edit_df,
        num_rows="dynamic",
        column_config={
            "hall": st.column_config.TextColumn("店舗名", required=True),
            "saved_medals": st.column_config.NumberColumn("貯メダル (枚)", min_value=0, step=100),
            "saved_balls": st.column_config.NumberColumn("貯玉 (玉)", min_value=0, step=100),
            "medal_rate": st.column_config.NumberColumn("メダル交換率 (例:5.06)", min_value=0.0, format="%.2f"),
            "ball_rate": st.column_config.NumberColumn("玉交換率 (例:28.0)", min_value=0.0, format="%.2f"),
        },
        use_container_width=True,
        key="savings_editor"
    )

    if st.button("💾 変更を保存する", type="primary", use_container_width=True):
        # 該当プレイヤーの既存データを削除
        df_s = df_s[df_s['player'] != p_sel].copy()
        
        # 新しいデータを追加
        if not edited_df.empty:
            edited_copy = edited_df.copy()
            edited_copy['player'] = p_sel
            edited_copy['id'] = [str(int(datetime.now().timestamp()) + i) for i in range(len(edited_copy))]
            edited_copy['updated_at'] = datetime.now(JST).strftime('%Y-%m-%d %H:%M')
            
            # NoneやNaNを適切に0.0に埋める
            edited_copy['saved_medals'] = edited_copy['saved_medals'].fillna(0).astype(int)
            edited_copy['saved_balls'] = edited_copy['saved_balls'].fillna(0).astype(int)
            edited_copy['medal_rate'] = edited_copy['medal_rate'].fillna(0.0)
            edited_copy['ball_rate'] = edited_copy['ball_rate'].fillna(0.0)

            df_s = pd.concat([df_s, edited_copy], ignore_index=True)
            
        save_savings(df_s)
        st.success("貯玉データを同期しました！")
        st.rerun()

    st.markdown("#### 🏢 店舗別 資産評価額")
    if p_savings.empty:
        st.write("データがありません。")
    else:
        disp_df = p_savings[['hall', 'メダル評価額 (¥)', '玉評価額 (¥)', '合計評価額 (¥)', 'updated_at']]
        st.dataframe(disp_df.style.format({
            'メダル評価額 (¥)': '¥{:,}',
            '玉評価額 (¥)': '¥{:,}',
            '合計評価額 (¥)': '¥{:,}'
        }), use_container_width=True, hide_index=True)

# ============================================================
# 一括インポート
# ============================================================
elif menu == "一括インポート":
    st.subheader("CSVインポート")
    st.info("既存のCSVファイルと同じ形式のレコードを一括で追加します。")
    up_file = st.file_uploader("CSVファイルを選択", type="csv")
    if up_file:
        up_df = pd.read_csv(up_file)
        st.write("プレビュー:")
        st.dataframe(up_df.head())
        if st.button("インポート実行"):
            df = pd.concat([df, up_df], ignore_index=True)
            save_data(df)
            st.success("インポート完了！")
            st.rerun()

# ============================================================
# 設定
# ============================================================
elif menu == "設定":
    st.subheader("システム設定")
    if st.button("キャッシュをクリア"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.success("キャッシュをクリアしました。再読み込みしてください。")
        st.rerun()
    
    st.divider()
    st.write("#### データの書き出し")
    if not df.empty:
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button("records.csv をダウンロード", csv, "records.csv", "text/csv")
        
        csv_s = df_s.to_csv(index=False).encode('utf-8-sig')
        st.download_button("savings.csv をダウンロード", csv_s, "savings.csv", "text/csv")
