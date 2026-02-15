import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

# --- 設定網頁標題與風格 ---
st.set_page_config(page_title="台股 RS 篩選器", page_icon="📈")

# --- 1. 股票地圖獲取邏輯 (增加保底與超時處理) ---
@st.cache_data(ttl=604800)
def get_stock_mapping():
    urls = {
        "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "TPEX": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    }
    mapping = {}
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    for market, url in urls.items():
        try:
            resp = requests.get(url, headers=headers, timeout=5) # 設定較短的超時防止卡死
            resp.encoding = 'ms950'
            soup = BeautifulSoup(resp.text, 'html.parser')
            rows = soup.find_all('tr')
            prefix = "TWSE" if market == "TWSE" else "TPEX"
            for row in rows:
                cols = row.find_all('td')
                if not cols: continue
                text = cols[0].get_text(strip=True).replace('\u3000', ' ')
                parts = text.split(' ')
                # 只要開頭是數字且長度 >= 4 就抓
                if len(parts) >= 2 and parts[0].isdigit() and len(parts[0]) >= 4:
                    mapping[parts[0]] = {"name": parts[1], "prefix": prefix}
        except Exception:
            continue
    return mapping

# --- 2. MoneyDJ 抓取邏輯 (維持你執行成功的正則邏輯) ---
def fetch_moneydj_rs(weeks, min_rank):
    url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.encoding = 'big5'
        # 這是你截圖中證明成功的核心邏輯
        match = re.search(r"parent\.sStklistAll\s*=\s*'([^']+)'", resp.text)
        if match:
            raw_codes = match.group(1).encode('utf-8').decode('unicode-escape')
            return [c.strip() for c in raw_codes.split(',') if c.strip().isdigit()]
    except Exception as e:
        st.error(f"連線 MoneyDJ 發生錯誤: {e}")
    return []

# --- 3. 網頁 UI 介面 (單欄佈局) ---
st.title("🇹🇼 台股 RS Rank 篩選器")

st.header("1. 設定篩選條件")
col1, col2 = st.columns(2)
with col1:
    weeks = st.slider("選擇週數", 1, 52, 1)
with col2:
    min_rank = st.number_input("RS Rank 大於等於", 1, 99, 80)

max_count = st.number_input("至多顯示幾筆", min_value=1, max_value=500, value=200)

mdj_url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
st.markdown(f"🔍 [🔗 開啟 MoneyDJ 原始網頁確認]({mdj_url})")

btn = st.button("🚀 執行篩選並產出清單", type="primary", use_container_width=True)

st.divider()

if btn:
    with st.spinner('正在同步數據...'):
        mapping = get_stock_mapping()
        codes = fetch_moneydj_rs(weeks, min_rank)
        
        if codes:
            final_codes = codes[:max_count]
            tv_format_list = []
            display_data = []
            
            for c in final_codes:
                info = mapping.get(c)
                
                # --- 保底機制重點 ---
                # 如果 mapping 抓不到，預設為 TWSE 且名稱顯示為 "待查"
                mkt = info['prefix'] if info else "TWSE"
                name = info['name'] if info else "名稱待查"
                
                prefix_code = f"{mkt}:{c}"
                tv_format_list.append(prefix_code)
                display_data.append({"代號": c, "名稱": name, "市場": mkt})
            
            st.success(f"找到共 {len(codes)} 檔股票，目前顯示前 {len(display_data)} 檔")

            # 動態檔名
            current_date = datetime.now().strftime("%Y_%m_%d")
            dynamic_filename = f"TW_{current_date}.txt"
            
            # TradingView 區塊
            csv_string = ",".join(tv_format_list)
            st.subheader("🔥 TradingView 匯入字串")
            if csv_string:
                st.code(csv_string, language="text") 
            else:
                st.warning("抓到了代碼但格式轉換失敗，請重新執行。")
            
            st.download_button(
                label=f"📥 下載 {dynamic_filename}",
                data=csv_string,
                file_name=dynamic_filename,
                mime="text/plain",
                use_container_width=True
            )
            
            st.subheader("📋 詳細清單")
            if display_data:
                st.dataframe(display_data, use_container_width=True)
            else:
                st.write("目前無清單數據可顯示。")
        else:
            st.warning("查無符合條件之股票，或 IP 被暫時阻擋。")