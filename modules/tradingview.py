import streamlit.components.v1 as components

def render_tv_chart(symbol="FX_IDC:USDJPY", height=380):
    clean_sym = symbol.replace(':', '_')
    html_code = f"""
    <div class="tradingview-widget-container" style="height:100%;width:100%">
      <div id="tv_chart_{clean_sym}" style="height:{height}px;width:100%"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true,
        "symbol": "{symbol}",
        "interval": "D",
        "timezone": "Asia/Taipei",
        "theme": "dark",
        "style": "1",
        "locale": "zh_TW",
        "toolbar_bg": "#1e222d",
        "enable_publishing": false,
        "allow_symbol_change": true,
        "container_id": "tv_chart_{clean_sym}"
      }});
      </script>
    </div>
    """
    components.html(html_code, height=height + 15)