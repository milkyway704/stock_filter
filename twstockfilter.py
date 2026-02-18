import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
from datetime import datetime, timedelta
import urllib3

# 禁用 SSL 安全警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(page_title="股票 RS 篩選器", page_icon="📈", layout="wide")

# --- 通用工具：時區處理 ---
def get_tw_time():
    return datetime.utcnow() + timedelta(hours=8)

# --- 1. 股票地圖 (台股專用) ---
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
        except:
            continue
    return mapping

# --- 2. MoneyDJ 抓取 (台股專用) ---
def fetch_moneydj_rs(weeks, min_rank):
    url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
    try:
        resp = requests.get(url, timeout=15, verify=False)
        resp.encoding = 'big5'
        match = re.search(r"parent\.sStklistAll\s*=\s*'([^']+)'", resp.text)
        if match:
            raw_codes = match.group(1).encode('utf-8').decode('unicode-escape')
            return [c.strip() for c in raw_codes.split(',') if c.strip().isdigit()]
    except:
        pass
    return []

# --- 3. Google Sheet 抓取 (美股專用) ---
@st.cache_data(ttl=3600)  # 每小時更新一次
def fetch_us_rs_from_gsheet(sheet_url):
    try:
        # 將編輯連結轉換為 CSV 導出連結
        csv_url = sheet_url.replace('/edit?usp=sharing', '/export?format=csv')
        df = pd.read_csv(csv_url)
        # 假設 Google Sheet 欄位包含 'Symbol', 'Name', 'RS Rating', 'Exchange'
        # 您需要根據該 Sheet 的實際標題修改下列欄位名稱
        return df
    except Exception as e:
        st.error(f"讀取 Google Sheet 失敗: {e}")
        return None

# --- 4. 介面佈局 ---
st.sidebar.title("🛠️ 市場切換")
market_choice = st.sidebar.radio("選擇市場", ["台股 (MoneyDJ)", "美股 (Google Sheet)"])

if market_choice == "台股 (MoneyDJ)":
    st.title("🇹🇼 台股 RS Rank 篩選器")
    
    weeks = st.slider("選擇週數", 1, 52, 1)
    min_rank = st.number_input("RS Rank 大於等於", 1, 99, 80)
    max_count = st.number_input("至多顯示幾筆", 1, 500, 200)

    mdj_url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
    st.markdown(f"🔍 [🔗 開啟 MoneyDJ 原始網頁確認]({mdj_url})")

    if st.button("🚀 執行台股篩選", type="primary", use_container_width=True):
        with st.spinner('正在同步數據...'):
            mapping = get_stock_mapping()
            codes = fetch_moneydj_rs(weeks, min_rank)
            if codes:
                final_codes = codes[:max_count]
                tv_list = [f"{mapping.get(c, {'prefix':'TWSE'})['prefix']}:{c}" for c in final_codes]
                display_data = [{"代號": c, "名稱": mapping.get(c, {'name':'名稱待查'})['name'], "市場": mapping.get(c, {'prefix':'TWSE'})['prefix']} for c in final_codes]
                
                # 下載與顯示邏輯 (維持原樣)
                csv_string = ",".join(tv_list)
                st.code(csv_string)
                st.download_button("📥 下載台股清單", csv_string, f"TW_{get_tw_time().strftime('%Y_%m_%d')}.txt")
                st.dataframe(display_data, use_container_width=True)
            else:
                st.warning("查無符合條件之股票。")

else:
    st.title("🇺🇸 美股 RS Rank 篩選器")
    st.info("數據來源：指定的 Google Sheet 公開清單")

    min_rs = st.number_input("RS Rank 最低分數", 1, 99, 90)
    
    gsheet_url = "https://docs.google.com/spreadsheets/d/18EWLoHkh2aiJIKQsJnjOjPo63QFxkUE2U_K8ffHCn1E/edit?usp=sharing"
    
    if st.button("🚀 執行美股篩選", type="primary", use_container_width=True):
        with st.spinner('讀取 Google Sheet 中...'):
            df = fetch_us_rs_from_gsheet(gsheet_url)
            if df is not None:
                # 自動偵測可能的 RS 欄位名稱 (例如 'RS Rating', 'RS', 'RS Rank')
                rs_col = next((c for c in df.columns if 'RS' in c.upper()), None)
                symbol_col = next((c for c in df.columns if 'SYMBOL' in c.upper() or 'TICKER' in c.upper()), None)
                
                if rs_col and symbol_col:
                    # 篩選條件
                    filtered_df = df[df[rs_col] >= min_rs].sort_values(by=rs_col, ascending=False)
                    
                    # 產生 TradingView 格式 (美股通常不需前綴，或視 Sheet 內容加 NASDAQ:/NYSE:)
                    # 這裡示範直接輸出代號，TradingView 通常能自動識別美股
                    tv_list = filtered_df[symbol_col].astype(str).tolist()
                    csv_string = ",".join(tv_list)
                    
                    st.success(f"找到共 {len(filtered_df)} 檔符合條件的美股")
                    st.subheader("🔥 TradingView 匯入字串")
                    st.code(csv_string)
                    
                    st.download_button(
                        label=f"📥 下載 US_{get_tw_time().strftime('%Y_%m_%d')}.txt",
                        data=csv_string,
                        file_name=f"US_{get_tw_time().strftime('%Y_%m_%d')}.txt",
                        mime="text/plain",
                        use_container_width=True
                    )
                    st.dataframe(filtered_df, use_container_width=True)
                else:
                    st.error(f"找不到對應的 RS 或代號欄位。目前的欄位有：{list(df.columns)}")