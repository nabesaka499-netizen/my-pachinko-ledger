import streamlit as st
import pandas as pd
from datetime import datetime
import json

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
        background: rgba(255, 255, 255, 0.05);
        padding: 15px;
        border-radius: 10px;
        border: 1px solid rgba(0, 242, 255, 0.2);
    }
    .stButton>button {
        background: linear-gradient(135deg, #00f2ff, #00d4ff);
        color: #0a0b1e;
        font-weight: bold;
        border: none;
        border-radius: 8px;
        width: 100%;
    }
</style>
""", unsafe_allow_html=True)

# --- Data Handling (Local CSV for fallback) ---
DATA_FILE = "records.csv"

def load_data():
    if "records" not in st.session_state:
        try:
            st.session_state.records = pd.read_csv(DATA_FILE)
        except:
            st.session_state.records = pd.DataFrame(columns=[
                "id", "player", "game_type", "date", "hall", "machine", 
                "hours", "invest", "recovery", "balance", "memo"
            ])
    return st.session_state.records

def save_data(df):
    st.session_state.records = df
    df.to_csv(DATA_FILE, index=False)

def calculate_balance(row):
    # Logic from JS: (recovery - invest_from_count) - cash_invest
    # Simplified for Streamlit (assuming direct Yen input for now)
    return row['recovery'] - row['invest']

# --- App Logic ---
df = load_data()

st.title("収支管理簿")
st.caption("Pachinko & Slot Balance Analytics")

# Sidebar for Navigation
menu = st.sidebar.selectbox("メニュー", ["ホーム・記録", "分析 (月別/年別)", "一括インポート", "設定"])

if menu == "ホーム・記録":
    st.subheader("実戦記録の追加")
    col1, col2 = st.columns(2)
    
    with col1:
        player = st.radio("プレイヤー", ["Player 1", "Player 2"], horizontal=True)
        hall = st.text_input("ホール名", placeholder="例: マルハン")
        machine = st.text_input("機種名", placeholder="例: Re:ゼロ")
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

elif menu == "分析 (月別/年別)":
    st.subheader("収支統計")
    if df.empty:
        st.warning("データがありません。")
    else:
        # Metrics
        total_bal = df['balance'].sum()
        total_hours = df['hours'].sum()
        hourly = total_bal / total_hours if total_hours > 0 else 0
        
        m1, m2, m3 = st.columns(3)
        m1.metric("トータル収支", f"¥{int(total_bal):,}")
        m2.metric("合計稼働時間", f"{total_hours:.1f}h")
        m3.metric("平均時給", f"¥{int(hourly):,}")
        
        # Yearly/Monthly aggregation
        df['date'] = pd.to_datetime(df['date'])
        df['year'] = df['date'].dt.year
        df['month'] = df['date'].dt.strftime('%Y/%m')
        
        view_type = st.radio("表示単位", ["月別", "年別"], horizontal=True)
        group_col = 'month' if view_type == "月別" else 'year'
        
        summary = df.groupby(group_col).agg({
            'balance': 'sum',
            'hours': 'sum'
        }).sort_index(ascending=False)
        
        summary['時給'] = (summary['balance'] / summary['hours']).fillna(0).astype(int)
        
        st.dataframe(summary.style.format({
            'balance': '¥{:,}',
            'hours': '{:.1f}h',
            '時給': '¥{:,}'
        }), use_container_width=True)

elif menu == "一括インポート":
    st.subheader("データの移行・取り込み")
    
    # 1. JSON Import (from HTML App)
    st.write("### 1. HTML版アプリからの移行 (.json)")
    uploaded_file = st.file_uploader("エクスポートしたJSONファイルを選択してください", type="json")
    if uploaded_file is not None:
        try:
            records_json = json.load(uploaded_file)
            import_df = pd.DataFrame(records_json)
            # Adjust column names to match Streamlit schema
            rename_map = {"gameType": "game_type", "recoveryCash": "recovery", "cashInvest": "invest"}
            import_df = import_df.rename(columns=rename_map)
            
            if st.button("JSONデータを一括登録"):
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
            from io import StringIO
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
                for col in ["invest", "recovery", "balance", "hours"]:
                    if col in new_df.columns:
                        new_df[col] = pd.to_numeric(new_df[col].astype(str).str.replace('¥', '').str.replace(',', ''), errors='coerce').fillna(0)
                
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
    st.info("ここに Google Sheets の認証情報を入力することで、クラウド同期が有効になります。")
