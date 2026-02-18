import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from datetime import datetime, timedelta
import urllib3

# 禁用 SSL 安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 設定頁面，針對手機版建議使用寬度自動調整
st.set_page_config(page_title="RS Rank Filter", page_icon="📈", layout="centered")

# --- 通用工具 ---
def get_tw_time():
    # 伺服器通常為 UTC，台灣為 UTC+8
    return datetime.utcnow() + timedelta(hours=8)

# --- 1. 台股專用：股票地圖 ---
@st.cache_data(ttl=604800)
def get_stock_mapping():
    urls = {
        "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "TPEX": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    }
    mapping = {}
    headers = {'User-Agent': 'Mozilla/5.0'}
    for market, url in urls.items():
        try:
            resp = requests.get(url, headers=headers, timeout=10, verify=False)
            resp.encoding = 'ms950'
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.find_all('tr')
            prefix = "TWSE" if market == "TWSE" else "TPEX"
            for row in rows:
                cols = row.find_all('td')
                if not cols: continue
                text = cols[0].get_text(strip=True).replace('\u3000', ' ')
                parts = text.split(' ')
                if len(parts) >= 2 and parts[0].isdigit():
                    mapping[str(parts[0])] = {"name": parts[1], "prefix": prefix}
        except: continue
    return mapping

# --- 2. 台股專用：MoneyDJ 抓取 ---
def fetch_moneydj_rs(weeks, min_rank):
    url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
    try:
        resp = requests.get(url, timeout=15, verify=False)
        resp.encoding = 'big5'
        match = re.search(r"parent\.sStklistAll\s*=\s*'([^']+)'", resp.text)
        if match:
            raw_codes = match.group(1).encode('utf-8').decode('unicode-escape')
            return [c.strip() for c in raw_codes.split(',') if c.strip().isdigit()]
    except: pass
    return []

# --- 3. 美股專用：Google Sheet 抓取 ---
@st.cache_data(ttl=3600)
def fetch_us_rs_from_gsheet():
    # 您的 Google Sheet 連結
    gsheet_url = "https://docs.google.com/spreadsheets/d/18EWLoHkh2aiJIKQsJnjOjPo63QFxkUE2U_K8ffHCn1E/edit?usp=sharing"
    csv_url = gsheet_url.replace('/edit?usp=sharing', '/export?format=csv')
    try:
        df = pd.read_csv(csv_url)
        return df
    except Exception as e:
        st.error(f"美股數據讀取失敗: {e}")
        return None

# --- UI 介面開始 ---
# 標題居中 (符合草圖)
st.markdown("<h1 style='text-align: center;'>RS Rank Filter</h1>", unsafe_allow_html=True)

# 使用 Tabs 實作 US / TW 切換 (手機版最直覺的操作)
tab_us, tab_tw = st.tabs(["🇺🇸 US (美股)", "🇹🇼 TW (台股)"])

# --- 美股分頁 ---
with tab_us:
    st.subheader("美股 RS 篩選 (Google Sheet)")
    min_rs_us = st.number_input("RS Rank 最低標", 1, 99, 90, key="us_input")
    
    if st.button("🚀 執行美股篩選", type="primary", use_container_width=True):
        with st.spinner('讀取數據中...'):
            df_us = fetch_us_rs_from_gsheet()
            if df_us is not None:
                # 欄位偵測邏輯
                rs_col = next((c for c in df_us.columns if 'RS' in c.upper()), None)
                sym_col = next((c for c in df_us.columns if 'SYMBOL' in c.upper() or 'TICKER' in c.upper()), None)
                
                if rs_col and sym_col:
                    filtered_us = df_us[df_us[rs_col] >= min_rs_us].sort_values(by=rs_col, ascending=False)
                    tv_list_us = filtered_us[sym_col].astype(str).tolist()
                    csv_us = ",".join(tv_list_us)
                    
                    st.success(f"找到 {len(filtered_us)} 檔標的")
                    st.code(csv_us)
                    st.download_button("📥 下載 US 清單", csv_us, f"US_{get_tw_time().strftime('%Y_%m_%d')}.txt", use_container_width=True)
                    st.dataframe(filtered_us, use_container_width=True)
                else:
                    st.error("Sheet 格式不符，找不到 RS 或 Symbol 欄位。")

# --- 台股分頁 ---
with tab_tw:
    st.subheader("台股 RS 篩選 (MoneyDJ)")
    # 使用 columns 讓手機版併排，減少滾動
    col1, col2 = st.columns(2)
    with col1:
        weeks = st.selectbox("週數", options=[1, 2, 4, 8, 12, 24, 52], index=0)
    with col2:
        min_rank = st.number_input("RS Rank 下限", 1, 99, 80)
    
    max_count = st.slider("顯示上限", 50, 500, 200)

    if st.button("🚀 執行台股篩選", type="primary", use_container_width=True):
        with st.spinner('同步數據中...'):
            mapping = get_stock_mapping()
            codes = fetch_moneydj_rs(weeks, min_rank)
            
            if codes:
                final_codes = codes[:max_count]
                tv_list_tw = []
                display_tw = []
                
                for c in final_codes:
                    info = mapping.get(str(c))
                    mkt = info['prefix'] if info else "TWSE"
                    name = info['name'] if info else f"代號 {c}"
                    tv_list_tw.append(f"{mkt}:{c}")
                    display_tw.append({"代號": c, "名稱": name, "市場": mkt})
                
                st.success(f"找到 {len(codes)} 檔標的")
                csv_tw = ",".join(tv_list_tw)
                st.code(csv_tw)
                st.download_button("📥 下載 TW 清單", csv_tw, f"TW_{get_tw_time().strftime('%Y_%m_%d')}.txt", use_container_width=True)
                st.dataframe(display_tw, use_container_width=True)
            else:
                st.warning("查無符合條件之股票。")