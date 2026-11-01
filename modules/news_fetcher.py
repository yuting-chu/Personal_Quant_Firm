import urllib.request
import xml.etree.ElementTree as ET
import streamlit as st

@st.cache_data(ttl=300)
def fetch_yahoo_finance_news():
    url = "https://finance.yahoo.com/news/rssindex"
    news_items = []
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=5) as response:
            root = ET.fromstring(response.read())
            for item in root.findall('.//item')[:6]:
                title = item.find('title').text if item.find('title') is not None else "無標題"
                link = item.find('link').text if item.find('link') is not None else "#"
                pub_date = item.find('pubDate').text[:22] if item.find('pubDate') is not None else ""
                news_items.append({"title": title, "link": link, "date": pub_date})
    except Exception:
        news_items.append({"title": "即時總經新聞連線中...", "link": "#", "date": ""})
    return news_items