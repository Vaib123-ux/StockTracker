import concurrent.futures
import datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import yfinance as yf
import gspread
from google.oauth2.service_account import Credentials
import json
import os

# Authenticate with Google Sheets using GitHub Secrets
creds_info = json.loads(os.environ['GCP_CREDENTIALS'])
scopes = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive',
]
credentials = Credentials.from_service_account_info(creds_info, scopes=scopes)
gc = gspread.authorize(credentials)

# Open Google Sheet and load data from 'Data' tab
spreadsheet = gc.open('Nifty_200_Analysis_Current')
data_sheet = spreadsheet.worksheet('Data')

df_input = pd.DataFrame(data_sheet.get_all_records())


def process_row(row):
  symbol_raw = row.get('Symbol Name', '')
  if not symbol_raw:
    return None
  ticker_symbol = symbol_raw.replace('NSE:', '') + '.NS'
  company_name = row.get('Company Name', '')
  symbol = row.get('Symbol', '')

  try:
    ticker = yf.Ticker(ticker_symbol)
    end_date = datetime.date.today()
    start_date = end_date - relativedelta(years=1)

    hist = ticker.history(start=start_date, end=end_date)
    if hist.empty:
      return None

    today_price = hist['Close'].iloc[-1]

    def get_price_ago(target_date):
      filtered = hist[hist.index.date <= target_date]
      if not filtered.empty:
        return filtered['Close'].iloc[-1]
      return None

    price_2m = get_price_ago(end_date - relativedelta(months=2))
    price_3m = get_price_ago(end_date - relativedelta(months=3))
    price_6m = get_price_ago(end_date - relativedelta(months=6))
    price_1y = get_price_ago(end_date - relativedelta(years=1))

    analysis_1y = (
        (today_price - price_1y) / price_1y
        if price_1y and price_1y != 0
        else None
    )
    analysis_2m = (
        (today_price - price_2m) / price_2m
        if price_2m and price_2m != 0
        else None
    )
    analysis_3m = (
        (today_price - price_3m) / price_3m
        if price_3m and price_3m != 0
        else None
    )

    try:
      market_cap = ticker.fast_info.market_cap / 1e7
    except:
      market_cap = row.get('Company MarketCapital in Cr', 0)

    return {
        'Company Name': company_name,
        'Symbol': symbol,
        'Symbol Name': symbol_raw,
        'Today Price': round(today_price, 2) if today_price else None,
        'Price 2 Month ago': round(price_2m, 2) if price_2m else None,
        'Price 3 Month ago': round(price_3m, 2) if price_3m else None,
        'Price 6 Month ago': round(price_6m, 2) if price_6m else None,
        'Price 1 Year ago': round(price_1y, 2) if price_1y else None,
        '2 Month Analysis': round(analysis_2m, 3) if analysis_2m else None,
        '1 Year Analysis': round(analysis_1y, 3) if analysis_1y else None,
        'Company MarketCapital in Cr': (
            round(market_cap, 3) if market_cap else None
        ),
    }
  except Exception as e:
    print(f'Error processing {ticker_symbol} : {e}')
    return None


results = []
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
  futures = [
      executor.submit(process_row, row) for idx, row in df_input.iterrows()
  ]
  for future in concurrent.futures.as_completed(futures):
    res = future.result()
    if res:
      results.append(res)

df_output = pd.DataFrame(results)

data_sheet.clear()
data_sheet.update(
    [df_output.columns.values.tolist()] + df_output.values.tolist()
)
print('Google Sheet "Data" tab successfully updated and saved!')
