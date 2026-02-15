import streamlit as st
import requests
from bs4 import BeautifulSoup
import json
import re

# --- 設定網頁標題 ---
st.set_page_config(page_title="台股 RS 篩選器", page_icon="📈")

# --- 1. 股票地圖獲取邏輯 ---
@st.cache_data(ttl=604800)
def get_stock_mapping():
    urls = {
        "TWSE": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2",
        "TPEX": "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"
    }
    mapping = {}
    for market, url in urls.items():
        try:
            resp = requests.get(url, timeout=10)
            resp.encoding = 'ms950'
            soup = BeautifulSoup(resp.text, 'html.parser')
            # 原本的 find('table', class_='h4') 有時會失效，改用更通用的抓取方式
            rows = soup.find_all('tr')
            prefix = "TWSE" if market == "TWSE" else "TPEX"
            for row in rows:
                cols = row.find_all('td')
                if not cols: continue
                text = cols[0].get_text(strip=True).replace('\u3000', ' ')
                parts = [p for p in text.split(' ') if p.strip()]
                # 確保代號是字串格式且長度正確
                if len(parts) >= 2 and parts[0].isdigit():
                    mapping[str(parts[0])] = {"name": parts[1], "prefix": prefix}
        except Exception as e:
            st.error(f"地圖抓取失敗 ({market}): {e}")
    return mapping

# --- 2. MoneyDJ API 抓取邏輯 ---
def fetch_moneydj_rs(weeks, min_rank):
    url = f"https://moneydj.emega.com.tw/z/zk/zkf/zkResult.asp?D=1&A=x@250,a@{weeks},b@{min_rank}&site="
    try:
        resp = requests.get(url, timeout=15)
        resp.encoding = 'big5'
        match = re.search(r"parent\.sStklistAll\s*=\s*'([^']+)'", resp.text)
        if match:
            raw_codes = match.group(1).encode('utf-8').decode('unicode-escape')
            return [c.strip() for c in raw_codes.split(',') if c.strip()]
    except Exception as e:
        st.error(f"連連 MoneyDJ 發生錯誤: {e}")
    return []

# --- 3. 網頁 UI 介面 ---
st.title("🇹🇼 台股 RS Rank 偵錯工具")

with st.sidebar:
    st.header("參數設定")
    weeks = st.slider("週數", 1, 52, 2)
    min_rank = st.number_input("RS Rank >=", 1, 99, 80)
    btn = st.button("開始篩選並檢查 Mapping", type="primary")

if btn:
    mapping = get_stock_mapping()
    codes = fetch_moneydj_rs(weeks, min_rank)
    
    # --- 【新增：除錯資訊區】 ---
    st.subheader("🛠️ 系統偵錯資訊")
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Mapping 總筆數", len(mapping))
    with col_b:
        st.metric("MoneyDJ 抓取筆數", len(codes))
    
    if len(mapping) == 0:
        st.error("❌ 警告：股票名稱地圖（Mapping）是空的！可能是證交所封鎖了連線。")
    else:
        st.info(f"💡 地圖樣本：{list(mapping.items())[:3]}") # 印出前三筆範例
    
    # --- 處理資料 ---
    if codes:
        tv_format_list = []
        display_data = []
        
        for c in codes:
            # 確保用字串去比對
            info = mapping.get(str(c))
            if info:
                prefix_code = f"{info['prefix']}:{c}"
                tv_format_list.append(prefix_code)
                display_data.append({"代號": c, "名稱": info['name'], "市場": info['prefix']})
            else:
                # 如果找不到，也暫時顯示出來看看原因
                display_data.append({"代號": c, "名稱": "⚠️ Mapping 找不到", "市場": "未知"})

        st.success(f"結果：比對成功 {len(tv_format_list)} 檔。")
        
        if tv_format_list:
            st.subheader("TradingView 字串")
            st.code(",".join(tv_format_list))
        
        st.subheader("比對結果清單")
        st.dataframe(display_data, use_container_width=True)
    else:
        st.warning("查無符合條件之股票。")