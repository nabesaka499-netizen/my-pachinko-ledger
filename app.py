import streamlit as st
import pandas as pd
from datetime import datetime
import json
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
                "hours", "invest", "recovery", "balance", "memo"
            ])
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
                "message": f"Update records via App {datetime.now().strftime('%Y-%m-%d %H:%M')}",
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
menu = st.sidebar.selectbox("メニュー", ["ホーム・記録", "分析 (月別/年別)", "一括インポート", "設定"])

if menu == "ホーム・記録":
    # --- Month Summary Header ---
    st.subheader("今月の収支サマリー")
    current_month = datetime.now().strftime("%Y-%m")
    df_this_month = df.copy()
    df_this_month['month'] = pd.to_datetime(df['date']).dt.strftime('%Y-%m')
    df_this_month = df_this_month[df_this_month['month'] == current_month]
    
    sum_cols = st.columns(3)
    players_to_show = ["Player 1", "Player 2", "全員"]
    
    for i, p_name in enumerate(players_to_show):
        with sum_cols[i]:
            if p_name == "全員":
                p_df = df_this_month
            else:
                p_df = df_this_month[df_this_month['player'] == p_name]
            
            p_bal = p_df['balance'].sum()
            p_hours = p_df['hours'].sum()
            p_hourly = p_bal / p_hours if p_hours > 0 else 0
            
            st.markdown(f"""
            <div style="padding:10px; border:1px solid rgba(0,242,255,0.2); border-radius:10px; background:rgba(0,242,255,0.05);">
                <div style="font-weight:bold; color:#00f2ff; margin-bottom:5px;">{p_name} ({datetime.now().strftime('%m月')})</div>
                <div style="font-size:1.2em; font-weight:bold;">¥{int(p_bal):,}</div>
                <div style="font-size:0.8em; opacity:0.8;">{p_hours:.1f}h | ¥{int(p_hourly):,}/h</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.divider()
    st.subheader("実戦記録の追加")
    col1, col2 = st.columns(2)
    
    with col1:
        player = st.radio("プレイヤー", ["Player 1", "Player 2"], horizontal=True)
        # Suggestions for Hall and Machine
        hall_list = sorted(df['hall'].dropna().unique().tolist())
        hall = st.selectbox("ホール名", ["新規入力..."] + hall_list)
        if hall == "新規入力...":
            hall = st.text_input("新しいホール名を入力", placeholder="例: マルハン")
        
        machine_list = sorted(df['machine'].dropna().unique().tolist())
        machine = st.selectbox("機種名", ["新規入力..."] + machine_list)
        if machine == "新規入力...":
            machine = st.text_input("新しい機種名を入力", placeholder="例: Re:ゼロ")
            
        date = st.date_input("日付", datetime.now())

    with col2:
        game_type = st.selectbox("種別", ["スロット", "パチンコ"], index=0)
        invest = st.number_input("現金投資 (¥)", min_value=0, step=500, value=0)
        recovery = st.number_input("回収金額 (¥)", min_value=0, step=10, value=0)
        
        # Simple Time Sliders
        col_sh, col_sm = st.columns(2)
        start_hour = col_sh.slider("開始時", 9, 23, 9)
        start_min = col_sm.slider("開始分", 0, 55, 0, step=5)
        col_eh, col_em = st.columns(2)
        end_hour = col_eh.slider("終了時", 9, 23, 22)
        end_min = col_em.slider("終了分", 0, 55, 0, step=5)
        
        # Calculate hours
        h_diff = (end_hour + end_min/60) - (start_hour + start_min/60)
        if h_diff < 0: h_diff += 24
        st.write(f"稼働時間: {h_diff:.1f}h")

    if st.button("保存する"):
        new_row = {
            "id": str(int(datetime.now().timestamp())),
            "player": player,
            "game_type": game_type,
            "date": date.strftime("%Y-%m-%d"),
            "hall": hall,
            "machine": machine,
            "hours": round(h_diff, 1),
            "invest": invest,
            "recovery": recovery,
            "balance": recovery - invest,
            "memo": ""
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_data(df)
        st.success("データを保存しました！")
        st.rerun()

    st.divider()
    st.subheader("最新の記録 (10件)")
    if df.empty:
        st.info("まだ記録がありません。")
    else:
        # Show recent 10 records
        recent_df = df.tail(10).iloc[::-1]
        st.dataframe(recent_df[["date", "hall", "machine", "balance", "player"]].style.format({
            "balance": "¥{:,}"
        }), use_container_width=True)

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

            # Metrics
            t_bal = df_v['balance'].sum()
            t_hours = df_v['hours'].sum()
            h_ly = t_bal / t_hours if t_hours > 0 else 0
            
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("トータル収支", f"¥{int(t_bal):,}")
            mc2.metric("合計稼働時間", f"{t_hours:.1f}h")
            mc3.metric("平均時給", f"¥{int(h_ly):,}")
            
            # Yearly/Monthly aggregation
            df_v['date_dt'] = pd.to_datetime(df_v['date'])
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
