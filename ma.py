from datetime import datetime, timedelta
import pandas as pd
import numpy as np
import backtrader as bt

# ---- Alpaca imports ----
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import GetAssetsRequest
from alpaca.trading.enums import AssetClass, AssetExchange
from alpaca.data.enums import DataFeed

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# ======================== CONFIG ========================
# Prefer environment variables. Fall back to placeholders if absent.
API_KEY = 'PK4RYDY843IPHQJLNV5F'
API_SECRET = 'Oe2tXbBlTbxVllQTAnPiK7BRgpuFc6NLzPqKqzM6'

UNIVERSE_EXCHANGE = AssetExchange.NASDAQ
DAYS_BACK = 365  # lookback window for historical bars
BATCH_SIZE = 200 # Alpaca request batch size
MAX_SYMBOLS = 30 # limit to avoid huge backtests initially
ADJUSTMENT = "split"  # or "raw"
DATA_FEED = DataFeed.IEX   # free feed

INITIAL_CASH = 100_000
COMMISSION = 0.001   # 10 bps
STAKE = 10           # shares per order


# Strategy params (tweak freely)
MA_FAST = 20
MA_SLOW = 50
RSI_PERIOD = 14
RSI_BULL = 50         # RSI > 50 considered bullish (you can raise to 55-60)
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

trading_client = TradingClient(API_KEY, API_SECRET)

# Get only US equities on NASDAQ
assets = trading_client.get_all_assets(
    GetAssetsRequest(
        asset_class=AssetClass.US_EQUITY,
        exchange=AssetExchange.NASDAQ
    )
)

# get stocks in batches
def get_closes_last_year(assets, batch_size=200):
    symbols = [a.symbol for a in assets if getattr(a, "tradable", True)]
    start = datetime.now() - timedelta(days=365)
    end   = datetime.now()

    client = StockHistoricalDataClient(API_KEY, API_SECRET)

    frames = [] # for appending the batches
    for i in range(0, len(symbols), batch_size):
        # specifies param for get_stock_bars
        req = StockBarsRequest(
            symbol_or_symbols=symbols[i:i+batch_size],
            timeframe=TimeFrame.Day,
            start=start,
            end=end,
            adjustment="split",   # or "raw" if you prefer unadjusted
            feed=DataFeed.IEX # free ver. of alpaca 
        )
        # The actual SDK for getting bars, using params defined above
        bars = client.get_stock_bars(req)
        df = bars.df
        if df is not None and not df.empty:
            # append the bars from this batch into the list
            frames.append(df.reset_index())
            # frames.append(df.reset_index()[["timestamp","symbol","close"]])

    if not frames:
        return pd.DataFrame()
    # Create a df from the batches in the list
    wide = pd.concat(frames).sort_index()
    # wide = pd.concat(frames).pivot(index="timestamp", columns="symbol", values="close").sort_index()
    return wide

stock_df = get_closes_last_year(assets, batch_size=200)
df = stock_df[['symbol', 'timestamp','open','high','low','close','volume']].copy()
df['timestamp'] = pd.to_datetime(df['timestamp'])
# timestamp to tz-naive DatetimeIndex
try:
    df['timestamp'] = df['timestamp'].dt.tz_convert(None)
except Exception:
    df['timestamp'] = df['timestamp'].dt.tz_localize(None)

# Create a dictionary of DataFrames, one for each symbol
g = df.groupby('symbol')

stock_dict = { sym: x for sym, x in g }
# print(stock_dict['AACB'])

cerebro = bt.Cerebro()
for sym, df_sym in stock_dict.items():
    feed = bt.feeds.PandasData(dataname=df_sym)
    cerebro.adddata(feed, name=sym)

# stock_df = get_closes_last_year(assets, batch_size=200).dropna(axis = 1, how = 'any')

# print(stock_df.head(5))

class CompositeMAMACD(bt.Strategy):
    params = dict(
        ma_fast=MA_FAST,
        ma_slow=MA_SLOW,
        rsi_period=RSI_PERIOD,
        rsi_bull=RSI_BULL,
        macd_fast=MACD_FAST,
        macd_slow=MACD_SLOW,
        macd_signal=MACD_SIGNAL,
    )
    def __init__(self):
        for d in self.datas:
            d.ma_fast = bt.indicators.SMA(d.close, period = self.p.ma_fast)
            d.ma_slow = bt.indicators.SMA(d.close, period = self.p.ma_slow)
            d.macd = bt.indicators.MACD(d.close, 
                                        fastperiod = self.p.macd_fast,
                                        slowperiod = self.p.macd_slow, 
                                        signalperiod = self.p.macd_signal
                                        )
            d.rsi = bt.indicators.RSI(d.close, period = self.p.rsi_period)

    def prenext(self):
         if len(self.datas) < 50:
             return
         else:
             self.next()
        
            
