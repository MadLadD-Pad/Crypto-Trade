import ccxt
import logging
from time import sleep
from datetime import datetime as dt
import calendar
from threading import Thread, Lock
from math import isnan
from plotly import graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from ta.trend import EMAIndicator, SMAIndicator
from ta.momentum import rsi, stochrsi
from ta.volatility import BollingerBands
# import dash
# from dash.dependencies import Output, Input
# import dash_core_components as dcc
# import dash_html_components as html
# from collections import deque
# https://www.geeksforgeeks.org/plot-live-graphs-using-python-dash-and-plotly/

# Define global variables.
import config
import tools

now = dt.utcnow()
unix_time = calendar.timegm(now.utctimetuple())  # Current time in unix format.
unix_dict_key = {'1s': 1, '1m': 60, '3m': 180, '5m': 300, '15m': 900,
                 '1h': 3600, '4h': 14400, '1d': 86400, '1w': 604800}
trend_tolerance = {'1m': 0.002, '3m': 0.002, '5m': 0.003, '15m': 0.004,
                   '1h': 0.007, '4h': 0.01, '1d': 0.02, '1w': 0.05}
DEFAULT_TIME = '4h'
PREFERRED_EXCHANGES = ['Binance', 'FTX', 'OKX', 'KuCoin', 'Phemex']
can_trade = []  # Stores name tags such as BTC/USDT-Binance-True
lock = Lock()
log_format_string = '%(asctime)s:%(levelname)s:%(message)s'
logging.basicConfig(level=logging.INFO, filename='', filemode='w', format=log_format_string)
time_frame_preferences = {'HighTimeFrames': ['1w', '1d', '4h'], 'LowTimeFrames': ['1h', '15m', '5m', '3m', '1m']}


class Asset:
    """Builds asset objects containing all relevant chart data for 1m, 5m, 15m, 1h, 4h, 1d, and 1w time frames."""

    # Initialization function.
    def __init__(self, symbol, time_frames=None):
        logging.info("Instantiating {0} asset object".format(symbol))
        if time_frames is None:
            time_frames = ['1m', '3m', '5m', '15m', '1h', '4h', '1d', '1w']
        if isinstance(time_frames, list):
            self.time_frames = time_frames
        elif isinstance(time_frames, str):
            self.time_frames = time_frames.split(',')
        self.symbol = symbol
        self.usdt = symbol + "/USDT"
        self.tradeable_exchanges = []
        self.tickers = get_ticker_combos(symbol)
        self.chart = {}

        # See which exchanges the asset can trade on, if it hasn't been checked already
        get_markets = True
        for name_tag in can_trade:
            if self.symbol in name_tag:
                tags = name_tag.split()
                exchange = tags[-1]
                self.tradeable_exchanges.append(exchange)
                get_markets = False

        if not get_markets:
            self.obj_run_log('Exchanges already checked for {}'.format(self.symbol))

        elif get_markets:
            self.tradeable_exchanges = PREFERRED_EXCHANGES
            exchange_threads = []
            for xchng in self.tradeable_exchanges:
                thread = api_request_threading(self.usdt, xchng, None, None, 'markets')
                exchange_threads.append(thread)

            for thread in exchange_threads:
                thread.start()

            for thread in exchange_threads:
                thread.join()

            for xchng in self.tradeable_exchanges:
                for tag in can_trade:
                    if self.symbol in tag:
                        if xchng in tag:
                            if "True" in tag:
                                pass
                            if "False" in tag:
                                self.tradeable_exchanges.remove(xchng)

        if 'Binance' in self.tradeable_exchanges:
            exchange = 'Binance'
        else:
            exchange = self.tradeable_exchanges[0]

        # Build charts
        for time in self.time_frames:
            self.chart[time] = Chart(self.usdt, time, exchange=exchange)
        self.last_traded = self.chart['1m'].candles[-1]['Close']

    # CLASS FUNCTIONS
    # Update price
    def price_update(self):
        """Update price of the asset object"""
        self.obj_run_log('Updating last traded price')
        self.last_traded = get_current_price(self.usdt)

    # Store object specific information in the run.log file
    def obj_run_log(self, string):
        """Adds an object identifier and string to the run.log"""
        log = "From " + self.symbol + " object: "
        logging.info(log + string)

    # Calls initialization function again
    def rebuild_asset(self):
        """Simply calls the __init__() function again to rebuild attribute list."""
        self.obj_run_log('Updating asset data...')
        self.__init__(self.symbol, self.time_frames)

    # Display object data
    def print_data(self):
        """Prints asset name and other data for testing purposes."""
        print("Symbol: {0}\nExchanges: {1}".format(self.symbol, self.tradeable_exchanges))

    # Update chart candles
    def update_charts(self):
        """Checks current time to see if it's time for a candle to close or not. If so, then a new candle is created
        and added to the list of candles on the chart."""
        # Update current global unix time stamp
        update_time()
        for time, chart in self.chart.items():
            # Get a slice of the 1 minute chart and build a new candle from the data.
            one_minute_keys = {'5m': -5, '15': -15, '1h': -60, '4h': -240, '1d': -1440}
            one_minute_chart_exists = False
            if chart.time_interval in unix_dict_key.keys():
                num_seconds = unix_dict_key[chart.time_interval]
                _timestamp = 0
                _open = 0
                _high = 0
                _low = 0
                _close = 0
                _volume = 0

                # Check global unix time and see if it's time to any of the charts.
                if unix_time % num_seconds == 0:
                    self.obj_run_log('Adding new candle to {} chart'.format(chart.time_interval))
                    if chart.time_interval == '1m':
                        one_minute_chart_exists = True
                        sleep(0.5)  # Wait a moment to ensure the 1 minute chart has been updated on Binance
                        candles = get_candle_data(self.usdt, time_frame=chart.time_interval, candle_limit=2)
                        candle = candles[0]
                        chart.update_obj_candle_list(candle)
                    if one_minute_chart_exists and chart.time_interval != '1m':
                        candle_list = self.chart['1m'].candles[one_minute_keys[time]:]
                        _timestamp = candle_list[0]['Timestamp']
                        _open = candle_list[0]['Open']
                        _high = candle_list[0]['High']
                        _low = candle_list[0]['Low']
                        _close = candle_list[-1]['Close']
                        _volume = candle_list[0]['Volume']
                        for c in candle_list:
                            if c['Low'] < _low:
                                _low = c['Low']
                            if c['High'] > _high:
                                _high = c['High']
                            _volume += c['Volume']
                        candle = {'Timestamp': _timestamp, 'Open': _open, 'High': _high,
                                  'Low': _low, 'Close': _close, 'Volume': _volume}
                        chart.update_obj_candle_list(candle)
                    else:
                        sleep(0.75)
                        candles = get_candle_data(self.usdt, time_frame=chart.time_interval, candle_limit=2)
                        candle = candles[0]
                        chart.update_obj_candle_list(candle)
                else:
                    pass

            else:
                raise Exception('Unsupported time frame')

    def get_trades(self, limit=1000, since=None, until=None):
        """Fetches order book trade history. Trades come up to 1000 at a time and get added to a list. If no start or
        stop times are specified then the x most recent trades are returned with x being the limit= parameter."""
        # Update current unix timestamp
        if limit > 1000:
            limit = 1000
        if 'Binance' in self.tradeable_exchanges:
            xchng = set_exchange('Binance')
        else:
            xchng = set_exchange(self.tradeable_exchanges[0])
        trades = xchng.fetch_trades(self.symbol, limit=limit, since=since)
        if since is not None:
            update_time()
            current_unix_time = unix_time * 1000
            counter = 0
            if until is None:
                while trades[-1]['timestamp'] < current_unix_time:
                    counter += 1
                    logging.info('Getting trade chunk {0} since timestamp {1}'.format(counter, trades[-1]['timestamp']))
                    new_trades = xchng.fetch_trades(self.symbol, limit=limit, since=trades[-1]['timestamp'])
                    for i in new_trades:
                        trades.append(i)
            elif until is not None:
                while trades[-1]['timestamp'] < until:
                    counter += 1
                    logging.info('Getting trade chunk {0} since timestamp {1}'.format(counter, trades[-1]['timestamp']))
                    new_trades = xchng.fetch_trades(self.symbol, limit=limit, since=trades[-1]['timestamp'])
                    for i in new_trades:
                        trades.append(i)

        return trades


class Chart:
    """Builds chart data objects using candle data and various technical indicators."""

    # Initialization function.
    def __init__(self, symbol, time_interval, exchange='Binance'):

        # Initialization variables
        logging.info("Instantiating {0} {1} chart object from {2} data...".format(time_interval, symbol, exchange))

        chunks, limit = 0, 0
        if time_interval in time_frame_preferences['HighTimeFrames']:
            chunks = 1
            if time_interval == '4h':
                limit = 1000
            elif time_interval == '1d':
                limit = 730  # 2 years worth of daily candles
            elif time_interval == '1w':
                limit = 104  # 2 years worth of weekly candles
        elif time_interval in time_frame_preferences['LowTimeFrames']:
            chunks = 2
            limit = 1000
        else:
            raise Exception("That time interval is not supported.")

        # Get data to be used in object attributes
        candle_data = get_candle_data_chunks(symbol, chunks=chunks, candle_limit=limit, time_frame=time_interval,
                                             exchange=exchange)
        candles = bar_patterns(candle_packaging(candle_data), bars=(2, 3, 4))
        close_data = []
        volume_data = []
        twap = []
        for candle in candles:
            close_data.append(candle['Close'])
            volume_data.append(candle['Volume'])
            twap.append(candle['TWAP'])

        # Object attributes
        self.symbol = symbol
        self.time_interval = time_interval
        self.exchange = exchange
        self.candles = candles
        self.ema_ribbon = self.EMARibbon(data=close_data)
        self.volume_moving_average = self.VolumeMovingAverage(volume_data, 21)
        self.time_weighted_average = self.TWAP(twap, ma_type='sma', ma_length=21)
        self.bbands = self.BBands(data=close_data)
        self.rsi = self.RSI(data=close_data)
        self.stoch_rsi = self.StochRSI(data=close_data)
        self.trend_lines = []
        if time_interval != '1d' and time_interval != '1w':
            self.vpvr = self.VPVR(self.symbol, self.candles, time_interval)

    def print_data(self):
        close_prices = []
        for i in self.candles:
            close_prices.append(i['Close'])
        print('Price: {0}'.format(close_prices))
        self.ema_ribbon.print_data()
        self.bbands.print_data()
        self.rsi.print_data()
        self.stoch_rsi.print_data()

    def rebuild_chart(self):
        """Reinitialize the object to update all values."""
        self.__init__(self.symbol, self.time_interval, self.exchange)

    def update_obj_candle_list(self, candle):
        """Add a new candle to the list and delete the first candle in the list to keep the list the same length."""
        # Ensure that the the data passed as the argument is a dictionary with candle data elements in it.
        if type(candle) == dict:
            if 'Timestamp' in self.candles[0].keys() and 'Open' in self.candles[0].keys():
                self.candles.append(candle)

                # Keep 1m list long, but delete extra candles on other time frames. 1m candles can be used to
                # update all other chart candles without making lots of API calls.
                if not self.time_interval == '1m':
                    if len(self.candles) > 2000:
                        self.candles.pop(__index=0)
            else:
                logging.warning('Data provided to update_candles function doesn\'t contain candle data.')
        else:
            logging.warning('Data provided to update_candles function doesn\'t match candle dictionary format.')

    def save_candle_data(self, extension='txt'):
        """Stores candle data into a txt or csv file for later use."""
        config.save_candle_data(self.symbol, self.candles, extension=extension,
                                exchange=self.exchange)

    def add_trend_line(self, data, mode=None):
        """Adds a new trend line object to self.trend_lines. Specify support or resistance detection with
        mode argument"""
        if not isinstance(data, Chart.TrendLine):
            line = self.TrendLine(data, self.time_interval, mode=mode)
            self.trend_lines.append(line)
        elif isinstance(data, Chart.TrendLine):
            self.trend_lines.append(data)

    def delete_trend_line(self, line):
        """Pass a trend line as an argument to delete it from self.trend_lines"""
        if line in self.trend_lines:
            del line

    def analyze_price_action(self, window_size=3):
        """Looks at price action boxes and attempts to determine the current trend, and when the trend has changed."""

        def get_price_action_boxes(window=window_size):
            """Creates a list of price action boxes"""
            box_list = []
            c_list = []
            for candle in self.candles:
                index = self.candles.index(candle)
                c_list.append(candle)
                if index != 0 and index % window == 0:
                    new_box = Chart.PriceActionBoxes(c_list)
                    box_list.append(new_box)
                    for i in range(len(c_list) - 1, -1, -1):
                        c_list.pop(i)

            return box_list

        boxes = get_price_action_boxes(window=window_size)

        projection = Chart.PriceActionBoxes(None, empty=True)
        for box in boxes:
            if box is boxes[-1]:
                break

            timestamp_start = int(box.start / 1000)
            timestamp_end = int(box.end / 1000)
            p_time = timestamp_end - timestamp_start
            p_start = box.end
            p_end = int((p_start + p_time) * 1000)
            p_range = box.close - box.open
            p_open = box.close
            p_close = p_open + p_range

            projection.set_attributes(_open=p_open, close=p_close, start=p_start, end=p_end)

    def detect_pivot_points(self, mode='window', window_size=30, clean_up=True):
        """Loops through the candle list of the Chart object and attempts to identify pivot points in the price
        action. The mode= parameter can change the way that the pivot points are calculated by changing the string to
        'basic', 'wicks', 'flexible', or 'window'. Basic simply looks at five candles at once, and compares their
        closing prices. Wicks considers the highest and lowest points of the candles. Flexible uses wicks but is less
        strict with what it considers a pivot point. Window mode looks at a set number of candles and tries to determine
        if the trend is going up, down, or sideways. When the trend changes, a point is assigned to the candle that
        the price pivot occurred on. Control the size of the window with the window_size parameter."""

        logging.info('Detecting pivot points for {0} {1} chart'.format(self.symbol, self.time_interval))
        mode = mode.lower()

        # Loop through candles
        candles = self.candles
        length = len(candles) - 1
        if mode != 'window':
            for candle in candles:
                if candles.index(candle) < 2:
                    continue
                if candles.index(candle) >= length - 2:
                    break
                else:
                    c_one = candles[candles.index(candle) - 2]
                    c_two = candles[candles.index(candle) - 1]
                    c_three = candles[candles.index(candle)]
                    c_four = candles[candles.index(candle) + 1]
                    c_five = candles[candles.index(candle) + 2]

                if mode == 'basic':
                    # Top pivots
                    if c_one['Close'] < c_two['Close'] or c_one['Open'] < c_two['Close']:
                        if c_two['Close'] < c_three['Close'] or c_two['Close'] < c_three['High']:
                            if c_three['Close'] > c_four['Close']:
                                if c_four['Close'] > c_five['Close'] or c_four['Open'] > c_five['Close']:
                                    if c_three['Color'] == 'Red':
                                        c_three['Pivot-Top'] = c_three['Open']
                                    elif c_three['Color'] == 'Green':
                                        c_three['Pivot-Top'] = c_three['Close']

                    # Bottom pivots
                    if c_one['Close'] > c_two['Close'] or c_one['Open'] > c_two['Close']:
                        if c_two['Close'] > c_three['Close'] or c_two['Close'] < c_three['Low']:
                            if c_three['Close'] < c_four['Close']:
                                if c_four['Close'] < c_five['Close'] or c_four['Open'] < c_five['Close']:
                                    if c_three['Color'] == 'Red':
                                        c_three['Pivot-Bottom'] = c_three['Close']
                                    elif c_three['Color'] == 'Green':
                                        c_three['Pivot-Bottom'] = c_three['Open']

                if mode == 'wicks':
                    # Top Pivots
                    if c_one['High'] <= c_two['High'] or (
                            c_one['Close'] < c_two['Close'] and c_one['Color'] == 'Green'):
                        if c_two['High'] <= c_three['High']:
                            if c_three['High'] >= c_four['High']:
                                if c_three['High'] >= c_five['High'] or c_four['High'] >= c_five['High']:
                                    c_three['Pivot-Top'] = c_three['High']

                    # Bottom Pivots
                    if c_one['Low'] >= c_two['Low'] or (c_one['Close'] > c_two['Close'] and c_one['Color'] == 'Red'):
                        if c_two['Low'] >= c_three['Low']:
                            if c_three['Low'] <= c_four['Low']:
                                if c_three['Low'] <= c_five['Low'] or c_four['Low'] <= c_five['Low']:
                                    c_three['Pivot-Bottom'] = c_three['Low']

                if mode == 'flexible':
                    # Top Pivots
                    if c_one['High'] < c_three['High'] and c_two['High'] < c_three['High']:
                        if c_four['High'] < c_three['High'] and c_five['High'] < c_three['High']:
                            c_three['Pivot-Top'] = c_three['High']

                    # Bottom Pivots
                    if c_one['Low'] > c_three['Low'] and c_two['Low'] > c_three['Low']:
                        if c_four['Low'] > c_three['Low'] and c_five['Low'] > c_three['Low']:
                            c_three['Pivot-Bottom'] = c_three['Low']

                else:
                    raise Exception('Unsupported pivot point detection mode.')

        if mode == 'window':
            # Loop through candles and separate by slices

            # Find high points
            last_index = 0
            end = False
            while True:
                if last_index + window_size > len(candles):
                    sl = candles[last_index:-1]
                    end = True
                else:
                    sl = candles[last_index:last_index + window_size]

                high = 0
                low = 0
                high_index = 0
                low_index = 0

                # Loop through slices and generate high points
                for c in sl:
                    if high == 0 or c['High'] > high:
                        high = c['High']
                        high_index = candles.index(c)
                    if low == 0 or c['Low'] < low:
                        low = c['Low']
                        low_index = candles.index(c)
                if not end:
                    last_index = candles.index(sl[-1]) + 1

                candles[high_index]['Pivot-Top'] = candles[high_index]['High']
                candles[low_index]['Pivot-Bottom'] = candles[low_index]['Low']
                if end:
                    break

            if clean_up:
                # Clean up excess data points
                for candle in candles:
                    if 'Pivot-Top' in candle.keys():
                        high = None
                        index = candles.index(candle)
                        sl = candles[index:index + (window_size + 1)]
                        tops = []
                        for c in sl:
                            if high is None:
                                high = c['High']
                                tops.append(c)
                            elif high is not None and 'Pivot-Top' in c:
                                if c['High'] > high:
                                    high = c['High']
                                    tops.append(c)
                                else:
                                    tops.append(c)
                            else:
                                continue

                        if len(tops) > 2:
                            for c in range(len(tops) - 2):
                                candle_one = tops[c]
                                candle_two = tops[c + 1]
                                if candle_one['Pivot-Top'] > candle_two['Pivot-Top']:
                                    del candle_two['Pivot-Top']
                                elif candle_one['Pivot-Top'] <= candle_two['Pivot-Top']:
                                    del candle_one['Pivot-Top']
                        elif len(tops) == 2:
                            candle_one = tops[0]
                            candle_two = tops[1]
                            if candle_one['Pivot-Top'] > candle_two['Pivot-Top']:
                                del candle_two['Pivot-Top']
                            elif candle_one['Pivot-Top'] <= candle_two['Pivot-Top']:
                                del candle_one['Pivot-Top']
                        elif len(tops) < 2:
                            pass

                    elif 'Pivot-Bottom' in candle.keys():
                        low = None
                        index = candles.index(candle)
                        sl = candles[index:index + (window_size + 1)]
                        bottoms = []
                        for c in sl:
                            if low is None:
                                low = c['Low']
                                bottoms.append(c)
                            elif low is not None and 'Pivot-Bottom' in c:
                                if c['Low'] < low:
                                    low = c['Low']
                                    bottoms.append(c)
                                else:
                                    bottoms.append(c)
                            else:
                                continue

                        if len(bottoms) > 2:
                            for c in range(len(bottoms) - 2):
                                candle_one = bottoms[c]
                                candle_two = bottoms[c + 1]
                                if candle_one['Pivot-Bottom'] < candle_two['Pivot-Bottom']:
                                    del candle_two['Pivot-Bottom']
                                elif candle_one['Pivot-Bottom'] >= candle_two['Pivot-Bottom']:
                                    del candle_one['Pivot-Bottom']
                        elif len(bottoms) == 2:
                            candle_one = bottoms[0]
                            candle_two = bottoms[1]
                            if candle_one['Pivot-Bottom'] < candle_two['Pivot-Bottom']:
                                del candle_two['Pivot-Bottom']
                            elif candle_one['Pivot-Bottom'] >= candle_two['Pivot-Bottom']:
                                del candle_one['Pivot-Bottom']
                        elif len(bottoms) < 2:
                            pass

                    if 'Pivot-Top' in candle.keys() or 'Pivot-Bottom' in candle.keys():
                        index = candles.index(candle)
                        sl = candles[index - 3:index + 4]
                        for c in sl:
                            if 'Pivot-Top' in candle.keys():
                                if c['High'] > candle['High']:
                                    del candle['Pivot-Top']
                                    c['Pivot-Top'] = c['High']
                            elif 'Pivot-Bottom' in candle.keys():
                                if c['Low'] < candle['Low']:
                                    del candle['Pivot-Bottom']
                                    c['Pivot-Bottom'] = c['Low']

    class VolumeMovingAverage:
        """Creates a moving average for volume data."""

        def __init__(self, data, length):
            ma = moving_average(length, data=data, mode='sma', data_type='Volume')
            lst = []
            for name in ma.keys():
                lst.append(name)
            key = lst[0]
            self.key = key
            self.volume_ma = ma[key]
            self.length = length
            self.data = data

        def update_volume_ma(self, data=None, length=None):
            """Rebuilds the volume moving average data."""
            if data is None and length is None:
                self.__init__(data=self.data, length=self.length)
            elif data is None and length is not None:
                self.__init__(data=self.data, length=length)
            elif data is not None and length is None:
                self.__init__(data=data, length=self.length)

    class TWAP:
        """Time Weighted Average Price"""

        def __init__(self, data, ma_type='sma', ma_length=21):
            ma = moving_average(ma_length, data, mode=ma_type, data_type='TWAP')
            lst = []
            for name in ma.keys():
                lst.append(name)
            key = lst[0]
            self.length = ma_length
            self.twap_moving_average = ma[key]
            self.key = key

    class BBands:
        """Creates Bollinger bands indicator object."""

        def __init__(self, data):
            bbands = bollinger_bands(data=data)
            self.high_band = bbands['High-BBand']
            self.mid_band = bbands['Mid-BBand']
            self.low_band = bbands['Low-BBand']
            del bbands

        def print_data(self):
            """Print Bollinger Band data for the object."""
            print('BBand High: {0}\nBBand Mid: {1}\nBBand Low: {2}'.format(self.high_band, self.mid_band,
                                                                           self.low_band))

    class EMARibbon:
        """Creates and EMA ribbon consisting of EMA's that are based on Fibonacci numbers 13, 21, 34, 55, 233. Also
        200 as it's such a commonly used EMA period."""

        def __init__(self, data):
            ema_rib = ma_ribbon(data=data)
            self.ema13 = ema_rib['EMA13']
            self.ema21 = ema_rib['EMA21']
            self.ema34 = ema_rib['EMA34']
            self.ema55 = ema_rib['EMA55']
            self.ema200 = ema_rib['EMA200']
            self.ema233 = ema_rib['EMA233']
            del ema_rib

        # Checks if price is within a given range
        def slow_ema_band(self, price):
            """Checks if the price is within the slow EMA band (between 200 and 233 EMA)"""
            if self.ema200[-1] > self.ema233[-1]:
                range_check = tools.is_in_range(price, self.ema233[-1], self.ema200[-1])
            elif self.ema200[-1] < self.ema233[-1]:
                range_check = tools.is_in_range(price, self.ema200[-1], self.ema233[-1])
            else:
                return False
            return range_check

        # Determines trend direction. Establishes trading bias.
        def ema_trend(self, price=None, index=-1):
            """Checks if the trend is up or down based on EMA values. Takes 4 consecutive points from the EMA and
            analyzes and imaginary line connecting each point to determine which direction the EMA is pointing.
            Iterate through self.candles """
            trend = 'null'

            def trend_trajectory(data, ind=index):
                """Gets the current trajectory of a specific EMA"""

                # Set variables
                length = len(data)
                max_range = range(length - 4, length)
                if ind in max_range or ind == -1:
                    line = data[-4:length]
                else:
                    line = data[ind:ind + 4]
                trajectory = ''

                # Analyze an imaginary line between EMA coordinates
                if line[0] < line[1] < line[2] < line[3]:
                    trajectory = 'Up'
                elif line[0] > line[1] > line[2] > line[3]:
                    trajectory = 'Down'
                elif line[0] < line[1] > line[2] < line[3] or line[0] > line[1] < line[2] > line[3]:
                    trajectory = 'Sideways'
                elif line[0] < line[1] > line[2] > line[3] or line[0] > line[1] < line[2] < line[3]:
                    trajectory = 'Breaking'
                elif line[0] < line[1] < line[2] > line[3]:
                    trajectory = 'DownTick'
                elif line[0] > line[1] > line[2] < line[3]:
                    trajectory = 'UpTick'

                return trajectory

            if price is not None:
                # Bull trend formations
                if self.ema13[index] > self.ema55[index]:
                    trend = 'Bull-Trend'
                    if price > self.ema13[index]:
                        if trend_trajectory(self.ema13) == 'Up' and trend_trajectory(self.ema21) == 'Up':
                            if trend_trajectory(self.ema34) == 'Up' or trend_trajectory(self.ema34) == 'Breaking':
                                trend = 'Strong-' + trend
                    elif price < self.ema13[index] < self.ema21[index]:
                        if trend_trajectory(self.ema13) == 'Breaking' or trend_trajectory(self.ema13) == 'Down':
                            if trend_trajectory(self.ema21) == 'Sideways' or trend_trajectory(self.ema21) == 'Breaking':
                                trend = trend + '-Reversing'
                    elif price < self.ema21[index]:
                        trend = 'Weakened' + trend
                    elif price < self.ema34[index]:
                        trend = trend + '-Danger-Zone'
                elif self.ema13[index] > self.ema55[index] > price:
                    if trend_trajectory(self.ema13) == 'Down' or trend_trajectory(self.ema13) == 'Breaking':
                        trend = 'Dead-' + trend

                # Bear trend formations
                elif self.ema13[index] < self.ema55[index]:
                    trend = 'Bear-Trend'
                    if price < self.ema13[index]:
                        if trend_trajectory(self.ema13) == 'Down' and trend_trajectory(self.ema21) == 'Down':
                            trend = 'Strong-' + trend
                    elif price > self.ema13[index] > self.ema21[index]:
                        if trend_trajectory(self.ema13) == 'Breaking' or trend_trajectory(self.ema13) == 'Up':
                            if trend_trajectory(self.ema21) == 'Sideways' or trend_trajectory(self.ema21) == 'Breaking':
                                trend = trend + '-Reversing'
                    elif self.ema34[index] < price > self.ema21[index]:
                        trend = 'Weakened-' + trend
                    elif price > self.ema34[index]:
                        trend = trend + '-Danger-Zone'
                elif self.ema13[index] < self.ema55[index] < price:
                    if trend_trajectory(self.ema13) == 'Up' or trend_trajectory(self.ema13) == 'Breaking':
                        trend = 'Dead-' + trend

            # Price is not compared to EMA
            elif price is None:
                trend = 'null'
                # BULL TREND formations
                # 13 above 55
                if self.ema13[index] > self.ema55[index]:
                    trend = 'Bull-Trend'
                    # 13 above 21
                    if self.ema13[index] > self.ema21[index]:
                        # 13 and 21 projecting upwards.
                        if trend_trajectory(self.ema13) == 'Up' and trend_trajectory(self.ema21) == 'Up':
                            # 21 above 34 and 34 above 55
                            if self.ema21[index] > self.ema34[index] > self.ema55[index]:
                                # 34 projecting upwards
                                if trend_trajectory(self.ema34) == 'Up':
                                    if self.ema34[index] >= self.ema55[index]:
                                        trend = 'Strong-' + trend
                                        return trend
                        elif not trend_trajectory(self.ema13) == 'Up' and not trend_trajectory(self.ema21) == 'Up':
                            if trend_trajectory(self.ema34) == 'Up' and trend_trajectory(self.ema55) == 'Up':
                                trend = trend + '-Accumulation'
                                return trend
                            elif not trend_trajectory(self.ema34) == 'Up' and \
                                    not trend_trajectory(self.ema55) == 'Up':
                                trend = trend + '-Weakened'
                                return trend
                    # 13 below 21
                    elif self.ema13[index] <= self.ema21[index]:
                        if trend_trajectory(self.ema13) == 'Down' or trend_trajectory(self.ema13) == 'Breaking':
                            if trend_trajectory(self.ema21) == 'Down' or trend_trajectory(self.ema21) == 'Breaking':
                                if not trend_trajectory(self.ema34) == 'Up':
                                    if self.ema13[index] >= self.ema34[index] or self.ema21[index] >= self.ema34[index]:
                                        trend = trend + '-Accumulation'
                                        return trend
                                    elif self.ema13[index] < self.ema34[index] or self.ema21[index] < self.ema34[index]:
                                        if trend_trajectory(self.ema55) == 'DownTick' or \
                                                trend_trajectory(self.ema55) == 'Breaking':
                                            trend = trend + '-Breakdown'
                                            return trend
                                        else:
                                            trend = trend + '-Dead'
                                            return trend
                if self.ema13[index] > self.ema55[index] > self.ema34[index]:
                    trend = 'Void'
                    return trend

                # BEAR TREND formations
                if self.ema13[index] < self.ema55[index]:
                    trend = 'Bear-Trend'
                    # 13 below 21
                    if self.ema13[index] < self.ema21[index]:
                        # 13 and 21 projecting down
                        if trend_trajectory(self.ema13) == 'Down' and trend_trajectory(self.ema21) == 'Down':
                            # 21 below 34 and 34 below 55
                            if self.ema21[index] < self.ema34[index] < self.ema55[index]:
                                # 34 projecting down
                                if trend_trajectory(self.ema34) == 'Down':
                                    if self.ema34[index] >= self.ema55[index]:
                                        trend = 'Strong-' + trend
                                        return trend
                        elif not trend_trajectory(self.ema13) == 'Down' and not trend_trajectory(self.ema21) == 'Down':
                            if trend_trajectory(self.ema34) == 'Down' and trend_trajectory(self.ema55) == 'Down':
                                trend = trend + '-Accumulation'
                                return trend
                            elif not trend_trajectory(self.ema34) == 'Down' and \
                                    not trend_trajectory(self.ema55) == 'Down':
                                trend = trend + '-Weakened'
                                return trend
                    # 13 above 21
                    elif self.ema13[index] >= self.ema21[index]:
                        if trend_trajectory(self.ema13) == 'Up' or trend_trajectory(self.ema13) == 'Breaking':
                            if trend_trajectory(self.ema21) == 'Up' or trend_trajectory(self.ema21) == 'Breaking':
                                if not trend_trajectory(self.ema34) == 'Down':
                                    if self.ema13[index] <= self.ema34[index] or self.ema21[index] <= self.ema34[index]:
                                        trend = trend + '-Accumulation'
                                        return trend
                                    elif self.ema13[index] > self.ema34[index] or self.ema21[index] > self.ema34[index]:
                                        if self.ema21[index] < self.ema55[index]:
                                            if trend_trajectory(self.ema55) == 'UpTick' or \
                                                    trend_trajectory(self.ema55) == 'Breaking':
                                                trend = trend + '-Breakup'
                                            return trend
                                        else:
                                            trend = trend + '-Dead'
                                            return trend
                if self.ema13[index] >= self.ema55[index] >= self.ema34[index] or \
                        self.ema13[index] <= self.ema55[index] <= self.ema34[index]:
                    trend = 'Void'
                    return trend

            return trend

        def print_data(self):
            """Print EMA Ribbon data for the object."""
            print('EMA13: {0}\nEMA21: {1}\nEMA34: {2}\nEMA55: {3}\nEMA200: {4}\nEMA233: {5}'.format(self.ema13,
                                                                                                    self.ema21,
                                                                                                    self.ema34,
                                                                                                    self.ema55,
                                                                                                    self.ema200,
                                                                                                    self.ema233))

    class RSI:
        """Creates an RSI object"""

        def __init__(self, data):
            rsi_data = r_strength_index(data=data)
            self.rsi = rsi_data['RSI']

        def print_data(self):
            """Print RSI data of the object."""
            print('RSI: {}'.format(self.rsi))

    class StochRSI:
        """Returns Stochastic RSI data"""

        def __init__(self, data):
            rsi_data = stoch_rsi(data=data)
            self.k = rsi_data['Stoch-RSI-%K']
            self.d = rsi_data['Stoch-RSI-%D']

        def print_data(self):
            """Print RSI data of the object."""
            print('Stoch RSI K: {0}\nStoch RSI D: {1}'.format(self.k, self.d))

    class VPVR:
        """Volume per volume range profile. Adjust the range sizes by giving a value to the range_size parameter.
        a range_size of 1 uses the default range sizes. Using 2 would double the ranges sizes"""

        def __init__(self, symbol, candles, time_frame, range_size=1):
            logging.info('Building VPVR ranges...')

            # Get highest and lowest price of entire candle range.
            self.segments = {}
            self.symbol = symbol
            self.time_frame = time_frame
            segment_range = 0
            low = candles[0]['Low']
            high = candles[0]['High']
            first_candle = candles[0]
            data_exists = config.manage_vpvr_data(self.symbol, time_frame, None, mode='scan')
            start_time = first_candle['Timestamp']
            last_candle = candles[-1]
            end_time = last_candle['Timestamp']
            average = 0
            num_candles = len(candles)
            recent_update = False
            if data_exists:
                logging.info('Existing VPVR data detected. Loading data.')
                data = config.manage_vpvr_data(self.symbol, time_frame, None, mode='read')
                for k, v in data.items():
                    self.segments[k] = v
                start_time = data['Last Update'] * 1000
                del self.segments['Last Update']

                # If data has been updated within the past hour, skip update
                if (int(start_time / 1000) + unix_dict_key['1h']) > unix_time:
                    logging.info('VPVR data recently updated, skipping new update.')
                    recent_update = True

            if not recent_update:
                for candle in candles:
                    if candle['High'] > high:
                        high = int(round(candle['High'], 2))
                    if candle['Low'] < low:
                        low = int(round(candle['Low'], 2))
                    average += candle['Close']
                average = round(average / num_candles, 2)

                # Set segment range based on asset price.
                if average <= 10:
                    segment_range = round(0.05 * range_size, 2)
                elif 10 < average <= 100:
                    segment_range = round(0.5 * range_size, 2)
                    if segment_range >= 1:
                        segment_range = int(segment_range)
                elif 100 < average <= 500:
                    segment_range = 1 * range_size
                elif 500 < average <= 1000:
                    segment_range = 2 * range_size
                elif 1000 < average <= 10000:
                    segment_range = 10 * range_size
                elif 10000 < average <= 100000:
                    segment_range = 50 * range_size
                elif average > 100000:
                    segment_range = 100 * range_size

                def rounding(num):
                    """Used by VPVR indicator to determine appropriate segment ranges. Useful for avoiding weird price
                    level segments such as $1.653 or $232. Running those numbers through this function should return
                    $1.6 or $230"""
                    # If less than 4, then multiply by 10, round to nearest whole number, then divide by 10.
                    if average <= 4:
                        num = int(num * 10)
                        rounded = round(num / 10, 2)
                        return rounded
                    elif 4 < average <= 100:
                        num = int(num)
                        return num
                    elif 100 < average:
                        num = int(num)
                        while num % segment_range != 0:
                            num -= 1
                        return num

                # Build dictionary of segment ranges
                seg_low = rounding(low)
                seg_high = 0
                while seg_low < high:
                    if segment_range < 1:
                        seg_high = round(seg_low + segment_range, 2)
                    elif segment_range >= 1:
                        seg_high = seg_low + segment_range
                    seg_key = str(seg_low) + '-' + str(seg_high)
                    if seg_key in self.segments.keys():
                        pass
                    else:
                        self.segments[seg_key] = 0
                    seg_low = seg_high

                # Loop through saved 1m candle history. If candle is in range, add volume to range total
                if (int(start_time / 1000) - unix_dict_key['1m']) < unix_time:
                    config.update_candles_csv(symbol, '1m')
                one_minute_slice = config.slice_csv_data(symbol, '1m', start_time, end_time)
                logging.info('Looping through {0} {1} VPVR segments'.format(self.time_frame, self.symbol))
                if one_minute_slice is not None:
                    for candle in one_minute_slice:
                        for segment in self.segments.keys():
                            nums = segment.split('-')
                            if '.' in nums[0] or '.' in nums[1]:
                                num1 = float(nums[0])
                                num2 = float(nums[1])
                            else:
                                num1 = int(nums[0])
                                num2 = int(nums[1])
                            volume = int(candle['Volume'] / 3)
                            if num1 <= candle['Close'] < num2:
                                self.segments[segment] += volume
                            if num1 <= candle['High'] < num2:
                                self.segments[segment] += volume
                            if num1 <= candle['Low'] < num2:
                                self.segments[segment] += volume

            # If data has not been previously saved, save it.
            if not data_exists or not recent_update:
                logging.info('Saving VPVR data')
                self.sort_segments('ranges')
                config.manage_vpvr_data(symbol, time_frame, self.segments, mode='save')

        def print_data(self):
            """Prints VPVR data"""
            for segment, volume in self.segments.items():
                print(segment, volume)

        def sort_segments(self, key='volume'):
            """Sorts VPVR dictionary data by volume values or ranges. Choose by passing 'volume' or 'ranges' as the
            keyword argument in the key= parameter."""

            if key == 'volume':
                d_copy = self.segments.copy()
                sorted_d = {}
                for _ in range(len(self.segments)):
                    highest_value = 0
                    new_key = None
                    for k, v in d_copy.items():
                        if v >= highest_value:
                            highest_value = v
                            new_key = k
                    sorted_d[new_key] = highest_value
                    del d_copy[new_key]
                self.segments = sorted_d

            elif key == 'ranges':
                d_copy = self.segments.copy()
                sorted_d = {}
                lowest = 0
                for i in range(len(self.segments)):
                    key = None
                    value = None
                    for k, v in d_copy.items():

                        # Split string
                        tag = k.split('-')
                        num = tag[0]

                        # Convert string to numbers
                        if '.' in num:
                            num = round(float(num), 2)
                        elif '.' not in num:
                            num = int(num)

                        # Set values
                        if lowest == 0:
                            lowest = num
                            key = k
                            value = v
                        elif num < lowest:
                            lowest = num
                            key = k
                            value = v
                    lowest = 0
                    sorted_d[key] = value
                    del d_copy[key]
                self.segments = sorted_d

        def save_vpvr_data(self):
            """Saves VPVR data as a csv file."""
            config.manage_vpvr_data(self.symbol, self.time_frame, self.segments, mode='save')

    class TrendLine:
        """Draws trend lines using pivot point data."""

        def __init__(self, data, time_frame, mode, tolerance=10, length=3):
            self.start = {'Timestamp': 0, 'Price': 0}
            self.anchor = {'Timestamp': 0, 'Price': 0}
            self.end = {'Timestamp': 0, 'Price': 0}
            self.type = None
            self.ascension_rate = None
            self.time_frame = time_frame

            mode = mode.lower()
            logging.info('Building {0} trend line from pivot points.'.format(mode))
            anchor_index = int
            tol = tolerance

            if mode != 'resistance' and mode != 'support':
                raise Exception('Unsupported trend line mode. Must be support or resistance.')

            # Loop through candles and look for pivot points.
            count = 0
            for candle in data:
                if mode == 'resistance':
                    if 'Pivot-Top' in candle.keys():
                        if count == 0:
                            self.start['Timestamp'] = candle['Timestamp']
                            self.start['Price'] = candle['Pivot-Top']
                            self.type = 'Resistance'
                            count += 1
                        elif count > 0:
                            self.anchor['Timestamp'] = candle['Timestamp']
                            self.anchor['Price'] = candle['Pivot-Top']
                            anchor_index = data.index(candle)
                            break
                    else:
                        continue

                elif mode == 'support':
                    if 'Pivot-Bottom' in candle.keys():
                        if count == 0:
                            self.start['Timestamp'] = candle['Timestamp']
                            self.start['Price'] = candle['Pivot-Bottom']
                            self.type = 'Support'
                            count += 1
                        elif count == 1:
                            self.anchor['Timestamp'] = candle['Timestamp']
                            self.anchor['Price'] = candle['Pivot-Bottom']
                            anchor_index = data.index(candle)
                            break
                    else:
                        continue

            num_candles = calculate_num_candles(self.start['Timestamp'], self.anchor['Timestamp'], time_frame)
            ts_start = int(self.start['Timestamp'] / 1000)
            ts_anchor = int(self.anchor['Timestamp'] / 1000)
            self.end['Timestamp'] = int((ts_anchor + ((ts_anchor - ts_start) * length)) * 1000)

            p_start = self.start['Price']
            p_anchor = self.anchor['Price']
            self.end['Price'] = round(p_anchor + ((p_anchor - p_start) * length), 2)
            self.ascension_rate = round((p_anchor - p_start) / num_candles, 6)
            self.length = calculate_num_candles(self.start['Timestamp'], self.end['Timestamp'], time_frame)

            # Loop from anchor point onward, looking for more points.
            sl = data[anchor_index:]
            first_slice_element = sl[0]
            for c in sl:
                if c is first_slice_element:
                    continue
                else:
                    if mode == 'support':
                        if 'Pivot-Bottom' in c.keys():
                            num_candles = calculate_num_candles(self.start['Timestamp'], c['Timestamp'])
                            target = (self.ascension_rate * num_candles) + self.start['Price']
                            upper_limit = target + (self.ascension_rate * tol)
                            lower_limit = target - (self.ascension_rate * tol)
                            if lower_limit < c['Pivot-Bottom'] < upper_limit:
                                self.anchor['Timestamp'] = c['Timestamp']
                                self.anchor['Price'] = c['Pivot-Bottom']
                                p_start = self.start['Price']
                                p_anchor = self.anchor['Price']
                                self.end['Price'] = round(p_anchor + (p_anchor - p_start), 2)
                                self.ascension_rate = round((p_anchor - p_start) / num_candles, 6)
                            else:
                                continue

                    if mode == 'resistance':
                        if 'Pivot-Top' in c.keys():
                            num_candles = calculate_num_candles(self.start['Timestamp'], c['Timestamp'])
                            target = (self.ascension_rate * num_candles) + self.start['Price']
                            upper_limit = target + (abs(self.ascension_rate * tol))
                            lower_limit = target - (abs(self.ascension_rate * tol))
                            if lower_limit < c['Pivot-Top'] < upper_limit:
                                self.anchor['Timestamp'] = c['Timestamp']
                                self.anchor['Price'] = c['Pivot-Top']
                                p_start = self.start['Price']
                                p_anchor = self.anchor['Price']
                                self.end['Price'] = round(p_anchor + (p_anchor - p_start), 2)
                                self.ascension_rate = round((p_anchor - p_start) / num_candles, 6)
                            else:
                                continue

        def update_start_point(self, start, price):
            """Updates the starting point of the trend line."""
            num_candles = calculate_num_candles(self.start['Timestamp'], self.anchor['Timestamp'], self.time_frame)
            self.start['Timestamp'] = start
            self.start['Price'] = price
            ts_start = int(self.start['Timestamp'] / 1000)
            ts_anchor = int(self.anchor['Timestamp'] / 1000)
            self.end['Timestamp'] = int((ts_anchor + (ts_anchor - ts_start)) * 1000)
            p_start = self.start['Price']
            p_anchor = self.anchor['Price']
            self.end['Price'] = round(p_anchor + (p_anchor - p_start), 2)
            self.ascension_rate = round((p_anchor - p_start) / num_candles, 6)

        def update_end_point(self, end, price):
            """Updates the starting point of the trend line."""
            self.end['Timestamp'] = end
            self.end['Price'] = price
            ts_start = int(self.start['Timestamp'] / 1000)
            ts_end = int(self.end['Timestamp'] / 1000)
            self.anchor['Timestamp'] = int((((ts_end - ts_start) / 2) + ts_start) * 1000)
            num = self.end['Price'] - self.start['Price']
            if num < 0:
                self.anchor['Price'] = (((self.start['Price'] - self.end['Price']) / 2) - self.start['Price'])
            elif num >= 0:
                self.anchor['Price'] = (((self.end['Price'] - self.start['Price']) / 2) + self.start['Price'])

        def print_trend_line(self):
            """Prints the variable data of the trend line"""
            print('Starting Point: \n\tTime: {0}\n\tPrice: {1}'.format(self.start['Timestamp'], self.start['Price']))
            print('Anchor Point: \n\tTime: {0}\n\tPrice: {1}'.format(self.anchor['Timestamp'], self.anchor['Price']))
            print('End Point: \n\tTime: {0}\n\tPrice: {1}'.format(self.end['Timestamp'], self.end['Price']))
            print('Ascension Rate: {0}'.format(self.ascension_rate))
            print('Length of Line: {0} candles'.format(self.length))

    class PriceActionBoxes:
        """Creates boxes around a group of candles, essentially creating a larger candle. The intended purpose is to
        scan through a list of candles, create a boxes, then compare the price ranges of each box to try and understand
        what the current price trend is."""

        def __init__(self, candles, empty=False):

            # Check data for proper formatting
            if not isinstance(candles, list):
                if not isinstance(candles[0], dict):
                    string = '''Pass candle data as a list of candles, where each candle is a dictionary. Use the
                    get_candle_data() function to grab data and candle_packaging() for proper formatting'''
                    raise TypeError(string)

            open_ = float
            high = float
            low = float
            close = float
            volume = int
            start = int
            end = int
            color = str
            _range = float

            if empty:
                self.open = open_
                self.high = high
                self.low = low
                self.close = close
                self.volume = volume
                self.start = start
                self.end = end
                self.range = _range

            elif not empty:
                max_index = int
                length = int
                if candles is not None:
                    length = len(candles)
                    if length == 1:
                        raise Exception("Must pass more than 1 candle to create a price action box.")
                    max_index = length - 1
                elif candles is None:
                    raise TypeError("Candle data is None type, expected a list of candle dictionaries.")

                # Loop through list of candles
                for candle in candles:
                    if candles.index(candle) == 0:
                        open_ = candle['Open']
                        high = candle['High']
                        low = candle['Low']
                        volume = candle['Volume']
                        start = candle['Timestamp']
                    elif candles.index(candle) > 0:
                        volume += candle['Volume']
                        if candle['High'] > high:
                            high = candle['High']
                        if candle['Low'] < low:
                            low = candle['Low']
                        if candles.index(candle) == max_index:
                            end = candle['Timestamp']
                            close = candle['Close']
                            if close < open_:
                                color = 'Red'
                            elif close > open_:
                                color = 'Green'

                self.length = length
                self.open = open_
                self.high = high
                self.low = low
                self.close = close
                self.volume = volume
                self.start = start
                self.end = end
                self.color = color
                self.range = self.close - self.open

        def set_attributes(self, _open=None, high=None, low=None, close=None, volume=None, start=None, end=None):
            """Set box attributes. Useful if constructing an empty box to manually set data."""
            if _open is not None:
                self.open = _open
            if high is not None:
                self.high = high
            if low is not None:
                self.low = low
            if close is not None:
                self.close = close
            if volume is not None:
                self.volume = volume
            if start is not None:
                self.start = start
            if end is not None:
                self.end = end
            if _open is not None and close is not None:
                if _open <= close:
                    self.color = 'Green'
                elif _open > close:
                    self.color = 'Red'
            if self.close is None or self.open is None:
                self.range = None
            elif self.close is not None and self.open is not None:
                self.range = self.close - self.open

        def print_box(self):
            print("=========================")
            print("Open: {0}\nHigh: {1}\nLow: {2}\nClose: {3}".format(self.open, self.high, self.low, self.close))
            print("Volume: {0}\nStart: {1}\nEnd: {2}".format(self.volume, self.start, self.end))
            print("=========================\n")


def update_time():
    """Updates global unix timestamp data."""
    logging.info('Updating global unix time')
    global now
    global unix_time
    now = dt.utcnow()
    unix_time = calendar.timegm(now.utctimetuple())


def unix_tool(time_frame, length=0, milli_conversion=None, update=False):
    """Takes a time frame such as '1m', '15m', '1h', '4h', '1d', '1w' and returns the most recent candle open
    timestamp for the given time frame. The length= keyword determines how many periods back you want to go.
    Example: unix_tool('4h', length=10) would return the timestamp in milliseconds from 40 hours ago. A length
     of 0 will return the most recent candle opening timestamp. Pass a unix timestamp as an argument with the
     milli_conversion parameter to return the unix timestamp in milliseconds."""

    # Update "now" and "unix_time" objects with current data. Declare any other variables.
    if update:
        update_time()
    current_unix_time = unix_time  # For iterating and manipulating without changing the global variable again.
    key = unix_dict_key[time_frame]

    if milli_conversion is not None:
        milli_conversion = milli_conversion * 1000
        return milli_conversion

    # Subtract 1 from the current unix time value until the value divided by time_frame has a remainder of 0.
    # effectively converting the unix_time variable into the most recent candle open price of the given time frame.
    while True:
        if not current_unix_time % key == 0:
            current_unix_time -= 1
        elif current_unix_time % key == 0:
            if length == 0:
                current_unix_time = current_unix_time * 1000  # Convert to milliseconds.
                return current_unix_time
            elif length > 0:
                for _ in range(length):
                    current_unix_time -= key
                current_unix_time = current_unix_time * 1000  # Convert to milliseconds.
                return current_unix_time


def get_candle_data(ticker, time_frame=DEFAULT_TIME, candle_limit=250,
                    crypto_exchange='Binance', since=None):
    """Takes a ticker symbol and returns a dictionary of candle data containing open, high, low, and close prices
    as well as volume and timestamps. This function is the foundation of every other function in this script. If the
    given exchange is not supported, data will be fetched from Binance by default."""

    # Initialize local variables.
    exchange = set_exchange(crypto_exchange)
    token = name_tag_constructor(ticker, time_frame, crypto_exchange)
    candle_dict = {
        'Exchange': crypto_exchange,
        'Timestamp': [],
        'Open': [],
        'High': [],
        'Low': [],
        'Close': [],
        'Volume': []
    }

    # Determine if data can be gathered from exchange or not.
    if exchange == 'Unsupported':
        logging.info('Unsupported exchange. Using Binance as default.')
        exchange = set_exchange('Binance')
        crypto_exchange = 'Binance'

    logging.info('Gathering {0} price data for {1} from {2}.'.format(time_frame, ticker, crypto_exchange))
    candle_data = exchange.fetch_ohlcv(ticker, timeframe=time_frame, limit=candle_limit, since=since)
    logging.info(crypto_exchange + ' data returned')

    # Record all open/high/low/close candle data.
    logging.info('Building candle dictionary for {0}'.format(token))
    for candle in candle_data:
        lock.acquire()
        candle_dict['Timestamp'].append(candle[0])
        candle_dict['Open'].append(round(candle[1], 2))
        candle_dict['High'].append(round(candle[2], 2))
        candle_dict['Low'].append(round(candle[3], 2))
        candle_dict['Close'].append(round(candle[4], 2))
        candle_dict['Volume'].append(round(candle[5]))
        lock.release()

    return candle_dict


def get_candle_data_chunks(ticker, time_frame, chunks=1, candle_limit=1000, exchange='Binance', since=None, until=None):
    """Calls get_candle_data() multiple times to build larger candle dictionaries than the limitations set by the
    exchange API request limits."""

    # Local variables
    # Most exchanges will only send back 100 candles at a time. If not Binance, then set limit to 100.
    update_time()
    if exchange != 'Binance' and candle_limit > 100:
        candle_limit = 100
    chunk_timestamps = []
    log_counter = 0
    candle_dict = {'Open': [], 'High': [], 'Low': [], 'Close': [], 'Volume': [],
                   'Timestamp': [], 'Exchange': exchange}

    if since is None:
        # Determine which timestamps to smoothly parse chunks without overlap
        for chunk in range(chunks, 0, -1):
            block_start = (chunk * candle_limit) - 1
            time_stamp = unix_tool(time_frame, length=block_start)
            chunk_timestamps.append(time_stamp)

        for stamp in chunk_timestamps:
            log_counter += 1
            logging.info("Calculating candle data chunk {}".format(log_counter))

            data = get_candle_data(ticker, candle_limit=candle_limit, time_frame=time_frame,
                                   since=stamp, crypto_exchange=exchange)
            for k, v in data.items():
                if k == 'Exchange':
                    pass
                else:
                    for num in v:
                        candle_dict[k].append(num)

    elif since is not None:
        # Start from earliest timestamp
        num_candles = calculate_num_candles(since, time_frame=time_frame)
        chunks = 1
        if num_candles > 1000:
            while num_candles > 1000:
                chunks += 1
                num_candles -= 1000
        remainder = num_candles

        for i in range(chunks):
            if chunks > 1:
                data = get_candle_data(ticker, candle_limit=candle_limit, time_frame=time_frame,
                                       since=since, crypto_exchange=exchange)
                since = data['Timestamp'][-1] + int((unix_dict_key[time_frame] * 1000))
                for k, v in data.items():
                    if k == 'Exchange':
                        pass
                    else:
                        for num in v:
                            candle_dict[k].append(num)

            elif chunks <= 1:
                data = get_candle_data(ticker, candle_limit=remainder, time_frame=time_frame,
                                       since=since, crypto_exchange=exchange)
                for k, v in data.items():
                    if k == 'Exchange':
                        pass
                    else:
                        for num in v:
                            candle_dict[k].append(num)

        if until is not None:
            indices = []
            for i in candle_dict['Timestamp']:
                if i > until:
                    x = candle_dict['Timestamp'].index(i)
                    indices.append(x)

            for num in range(len(indices) - 1, -1, -1):
                del candle_dict['Timestamp'][num]
                del candle_dict['Open'][num]
                del candle_dict['High'][num]
                del candle_dict['Low'][num]
                del candle_dict['Close'][num]
                del candle_dict['Volume'][num]

    return candle_dict


def get_current_price(ticker, exchange='Binance'):
    """Uses get_candle_data function to look at current candle and determine current price."""

    logging.info("Fetching current price of {0} from {1}.".format(ticker, exchange))
    data = get_candle_data(ticker, candle_limit=1, crypto_exchange=exchange, time_frame='1m')
    price = data['Close'][0]

    return price


def name_tag_constructor(ticker, time, exchange):
    """Constructs a simple name tag for storing data in the close_prices global variable. Formatted as
    Symbol-TimeFrame-Exchange Such as ETH-4h-Binance"""

    # Define variable
    elements = [ticker, time, exchange]
    name_tag = '-'.join(elements)
    return name_tag


def set_exchange(crypto_exchange):
    """Converts a string of a crypto exchange name into the appropriate CCXT method. Used in the get_candle_data and
    if_can_trade functions."""

    exchange = None

    # Determine which exchange the data request will go to.
    if not (crypto_exchange == 'Binance'):
        if crypto_exchange == 'OKX':
            exchange = ccxt.okex()
        elif crypto_exchange == 'Bitfinex':
            exchange = ccxt.bitfinex2()
        elif crypto_exchange == 'FTX':
            exchange = ccxt.ftx()
        elif crypto_exchange == 'Huobi':
            exchange = ccxt.huobi()
        elif crypto_exchange == 'KuCoin':
            exchange = ccxt.kucoin()
        elif crypto_exchange == 'Bitstamp':
            exchange = ccxt.bitstamp()
        elif crypto_exchange == 'Kraken':
            exchange = ccxt.kraken()
        elif crypto_exchange == 'Phemex':
            exchange = ccxt.phemex()
        elif crypto_exchange == 'Bybit':
            exchange = ccxt.bybit()
        else:
            exchange = 'Unsupported'
    elif crypto_exchange == 'Binance':
        exchange = ccxt.binance()

    return exchange


def moving_average(ma_length, data=None, mode='ema', data_type='Close'):
    """By default, returns an exponential moving average of specified period length in dictionary or data frame format.
     To easily return multiple moving averages, use the ema_ribbon function instead. Setting the parameter 'ema' to
     false returns a simple moving average instead. Set mode to 'vol' if passing volume data as an argument to generate
     the appropriate dictionary key tag."""

    # Initialize local variables.
    token = ''
    mode = mode.lower()
    data_type = data_type.capitalize()
    if data_type == 'Twap':
        data_type = data_type.upper()
    if mode == 'ema':
        token = 'EMA' + str(ma_length)
    elif mode == 'sma':
        token = 'SMA' + str(ma_length)
    ma_data = None

    if data_type != 'Close':
        token = data_type + '_' + token

    if type(data) != list:
        raise TypeError('Data format incorrect. Send list of candle data.')
    if type(data) == list and type(data[0]) == dict:
        new_data = []
        for candle in data:
            new_data.append(candle[data_type])
        data = new_data

    df = pd.DataFrame()
    df['MA'] = data
    if mode == 'ema':
        ma_data = EMAIndicator(close=df['MA'], window=ma_length)
    elif mode == 'sma':
        ma_data = SMAIndicator(close=df['MA'], window=ma_length)

    # Builds data frame
    ma_df = pd.DataFrame()
    if mode == 'ema':
        ma_df[token] = ma_data.ema_indicator()
    elif mode == 'sma':
        ma_df[token] = ma_data.sma_indicator()

    # Return data
    ma_dict = {token: []}
    for i in ma_df[token]:
        r = round(i, 2)
        ma_dict[token].append(r)
    return ma_dict


def ma_ribbon(ribbon_inputs=None, mode='ema', data=None):
    """Returns a ribbon of EMA's derived from a user specified ticker and list of time intervals. Data can be returned
    as a dataframe by setting df_return to True. By default a dictionary is returned. Pass a list of moving average
    lengths to the ribbon_inputs parameter if you want to construct a custom EMA ribbon. By default, 6 moving averages
    of lengths 13, 21, 34, 55, 200, and 233 are returned."""

    # Initialize local variables.
    mode = mode.lower()
    if ribbon_inputs is None:
        ribbon_inputs = (13, 21, 34, 55, 200, 233)
    ma_df = pd.DataFrame()
    ma_rib_dict = {}

    # Checks if required data has already been gathered. If not, the data is requested.
    if type(data) != list:
        logging.warning('Data format incorrect. Send list of candle closing prices.')
        return data
    df = pd.DataFrame()
    df['MA-Ribbon'] = data

    # Loop to build EMA ribbon data frame or dictionary.
    if mode == 'ema':
        logging.info('Constructing EMA ribbon...')
    elif mode == 'sma':
        logging.info('Constructing SMA ribbon...')
    for i in ribbon_inputs:
        token = ''
        if mode == 'ema':
            token = 'EMA' + str(i)
        elif mode == 'sma':
            token = 'SMA' + str(i)
        ma_data = moving_average(i, mode=mode, data=data)
        ma_rib_dict[token] = []  # Populate dictionary keys and empty lists as values
        ma_df[token] = ma_data[token]

        # Add EMA data to dictionary value lists
        for j in ma_df[token]:
            ma_rib_dict[token].append(j)

    # Return dictionary
    return ma_rib_dict


def bollinger_bands(data=None):
    """Returns Bollinger Band data of specified ticker and time interval as a dictionary or pandas data frame. Data
    can be returned as a dataframe by setting df_return to True. By default a dictionary is returned."""

    # Initialize local variables.
    df = pd.DataFrame()
    if data is not None:
        df['Close'] = data
    elif type(data) != list:
        if data is None:
            logging.warning('No data detected. Add candle close data in data= parameter.')
            logging.warning('Inappropriate data type')
        return None

    # Build data frame containing BBand features.
    logging.info('Constructing Bollinger Bands...')
    bb_indicator = BollingerBands(df['Close'])
    h_band = round(bb_indicator.bollinger_hband(), 2)
    l_band = round(bb_indicator.bollinger_lband(), 2)
    ma = round(bb_indicator.bollinger_mavg(), 2)

    # Construct dictionary from existing data frame if requested by df_return kwarg.
    bb_dict = {'High-BBand': [], 'Mid-BBand': [], 'Low-BBand': []}
    for i in h_band:
        bb_dict['High-BBand'].append(i)

    for j in ma:
        bb_dict['Mid-BBand'].append(j)

    for k in l_band:
        bb_dict['Low-BBand'].append(k)
    return bb_dict


def r_strength_index(data=None):
    """Returns RSI data of given ticker and time interval. Data can be returned as a dataframe by setting df_return
    to True. By default a dictionary is returned."""

    rsi_dict = {'RSI': []}
    logging.info('Calculating RSI')

    # Checks if required data has already been gathered. If not, the data is requested.
    df = pd.DataFrame()
    df['Close-Prices'] = data
    r_index = rsi(df['Close-Prices'])

    # Store dictionary values.
    for i in r_index:
        r = round(i, 2)
        rsi_dict['RSI'].append(r)

    # Return dictionary or data frame.
    return rsi_dict


def stoch_rsi(data=None):
    """Returns stochastic RSI data of the given ticker symbol and time frame as a dictionary or dataframe. """

    # Initialize variables
    srsi_dict = {'Stoch-RSI-Data': [], 'Stoch-RSI-%K': [], 'Stoch-RSI-%D': []}
    logging.info('Calculating Stochastic RSI')

    # Checks if required data has already been gathered. If not, the data is requested.
    df = pd.DataFrame()
    df['SRSI'] = data
    r_index = stochrsi(df['SRSI'])

    # Add raw data to dictionary.
    for i in r_index:
        srsi_dict['Stoch-RSI-Data'].append(i)

    # Build %K values from raw data.
    for j in range(len(srsi_dict['Stoch-RSI-Data'])):
        if isnan(srsi_dict['Stoch-RSI-Data'][j]):
            srsi_dict['Stoch-RSI-%K'].append(float('nan'))
        elif not isnan(srsi_dict['Stoch-RSI-Data'][j]):
            if isnan(srsi_dict['Stoch-RSI-Data'][j - 1]) or isnan(srsi_dict['Stoch-RSI-Data'][j - 2]):
                srsi_dict['Stoch-RSI-%K'].append(float('nan'))
            elif not isnan(srsi_dict['Stoch-RSI-Data'][j - 1]) or isnan(srsi_dict['Stoch-RSI-Data'][j - 2]):
                n1 = srsi_dict['Stoch-RSI-Data'][j]
                n2 = srsi_dict['Stoch-RSI-Data'][j - 1]
                n3 = srsi_dict['Stoch-RSI-Data'][j - 2]
                avg = ((n1 + n2 + n3) / 3) * 100
                value = round(avg, 2)
                srsi_dict['Stoch-RSI-%K'].append(value)

    # Build %D values from %K values.
    for j in range(len(srsi_dict['Stoch-RSI-%K'])):
        if isnan(srsi_dict['Stoch-RSI-%K'][j]):
            srsi_dict['Stoch-RSI-%D'].append(float('nan'))
        elif not isnan(srsi_dict['Stoch-RSI-%K'][j]):
            if isnan(srsi_dict['Stoch-RSI-%K'][j - 1]) or isnan(srsi_dict['Stoch-RSI-%K'][j - 2]):
                srsi_dict['Stoch-RSI-%D'].append(float('nan'))
            elif not isnan(srsi_dict['Stoch-RSI-%K'][j - 1]) or isnan(srsi_dict['Stoch-RSI-%K'][j - 2]):
                n1 = srsi_dict['Stoch-RSI-%K'][j]
                n2 = srsi_dict['Stoch-RSI-%K'][j - 1]
                n3 = srsi_dict['Stoch-RSI-%K'][j - 2]
                avg = (n1 + n2 + n3) / 3
                value = round(avg, 2)
                srsi_dict['Stoch-RSI-%D'].append(value)

    # Remove raw data from the dictionary.
    del srsi_dict['Stoch-RSI-Data']

    # Return dictionary or data frame.
    return srsi_dict


def candle_aggregator(ticker, time=DEFAULT_TIME, length=50, exchanges_csv='Binance,FTX,Huobi,OKX'):
    """Combines candle data from multiple exchanges and returns an average of the combined OHLCV data. Keep in mind
    that some exchanges such as Bybit will return a max of 200 candles. Some may cap even lower at 100."""

    # Initialize variables. Create a list by splitting provided names of exchanges in comma separated value string.
    # Create lists to store aggregated data in. A dictionary will be built from these lists.
    exchanges = exchanges_csv.split(',')
    candle_close = []
    candle_open = []
    candle_high = []
    candle_low = []
    total_volume = []
    agg_timestamps = []
    agg_dict = {}
    candle_data_threads = []
    market_data_threads = []

    # Initialize and store market fetching threads.
    for name in exchanges:
        market_thread = api_request_threading(ticker, name, length, time, 'markets')
        market_data_threads.append(market_thread)

    # Launch and close market fetching threads.
    logging.info('Checking exchanges for tradeable assets.')
    for market in market_data_threads:
        market.start()

    for market in market_data_threads:
        market.join()

    # Check for value in can_trade global variable. If not tradeable, remove the exchange from the list of exchanges
    # and delete temporarily stored values in can_trade global variable.
    new_copy = exchanges.copy()
    for name in new_copy:
        token = ticker + '-' + name + '-True'
        if token not in can_trade:
            exchanges.remove(name)

    # Initialize candle data threads.
    logging.info('Threading candle data calls.')
    for name in exchanges:
        candle_data = api_request_threading(ticker, name, length, time, 'candles')
        candle_data_threads.append(candle_data)

    # Launch candle data threads.
    for candle_thread in candle_data_threads:
        candle_thread.start()
    # Close threads.
    for candle_thread in candle_data_threads:
        candle_thread.join()

    # Loop through list of exchanges.
    logging.info('Aggregating price data.')
    for name in exchanges:

        # Declare local variables.
        candle_data = get_candle_data(ticker, time_frame=time, crypto_exchange=name)

        # Loop through candle_data dictionary items.
        for key, data in candle_data.items():

            # Declare local variables.
            count = 0

            # Build list of candle close data.
            if key == 'Close' and len(candle_close) == 0:
                for j in data:
                    candle_close.append(j)
            elif key == 'Close' and len(candle_close) > 0:
                for j in data:
                    candle_close[count] = round((candle_close[count] + j) / 2, 2)
                    count += 1
                count = 0

            # Build list of candle open data.
            if key == 'Open' and len(candle_open) == 0:
                for j in data:
                    candle_open.append(j)
            elif key == 'Open' and len(candle_open) > 0:
                for j in data:
                    candle_open[count] = round((candle_open[count] + j) / 2, 2)
                    count += 1
                count = 0

            # Build list of candle high data.
            if key == 'High' and len(candle_high) == 0:
                for j in data:
                    candle_high.append(j)
            elif key == 'High' and len(candle_high) > 0:
                for j in data:
                    candle_high[count] = round((candle_high[count] + j) / 2, 2)
                    count += 1
                count = 0

            # Build list of candle low data.
            if key == 'Low' and len(candle_low) == 0:
                for j in data:
                    candle_low.append(j)
            elif key == 'Low' and len(candle_low) > 0:
                for j in data:
                    candle_low[count] = round((candle_low[count] + j) / 2, 2)
                    count += 1
                count = 0

            # Combine volume
            if key == 'Volume' and len(total_volume) == 0:
                for j in data:
                    total_volume.append(j)
            elif key == 'Volume' and len(total_volume) > 0:
                for j in data:
                    total_volume[count] = round(total_volume[count] + j)
                    count += 1

            # Build timestamp list.
            if key == 'Timestamp':
                for j in data:
                    agg_timestamps.append(j)

    agg_dict['Open'] = candle_open
    agg_dict['High'] = candle_high
    agg_dict['Low'] = candle_low
    agg_dict['Close'] = candle_close
    agg_dict['Volume'] = total_volume
    agg_dict['Timestamp'] = agg_timestamps

    return agg_dict


def api_request_threading(ticker, exchange_name, candle_limit, time, job):
    """Creates new threads to gather candle data from more than one exchange at once. Mostly used in the
    candle_aggregator method. The job parameter is used to set which functions are to be threaded. Use 'candles'
    for gathering price data, and 'markets' for seeing if an asset is trading on a particular exchange."""

    # If not trying to check available markets, then create a thread for grabbing candle data.
    if job == 'candles':
        # Declare keyword argument variables.
        k_words = {
            'time_frame': time,
            'candle_limit': candle_limit,
            'crypto_exchange': exchange_name,
            'close_only': False
        }

        # Initialize and return thread object.
        candle_data_thread = Thread(target=get_candle_data, args=(ticker,), kwargs=k_words)
        return candle_data_thread

    # If trying to check for trading pair availability, execute this branch.
    elif job == 'markets':
        # Declare keyword argument variables
        k_words = {
            'exchange_name': exchange_name,
            'threading': True
        }

        # Create and return thread object.
        if_trading_thread = Thread(target=if_can_trade, args=(ticker,), kwargs=k_words)
        return if_trading_thread


def if_can_trade(ticker, exchange_name='Binance', threading=False):
    """Gets the available markets to be traded on the given exchange. Returns False if the given exchange is not
    supported."""
    # Declare local variables
    ticker_combos = get_ticker_combos(ticker)

    # Set which exchange will be called.
    logging.info('Checking for {0} on {1}'.format(ticker, exchange_name))
    exchange = set_exchange(exchange_name)

    # In case a requested exchange is not supported, return False.
    if exchange == 'Unsupported':
        return False

    # If data already exists, return data.
    for i in can_trade:
        if (ticker in i) and (exchange_name in i):
            if 'True' in i:
                return True
            elif 'False' in i:
                return False

    # Load market data from exchange.
    markets = exchange.fetch_markets()
    for coins in markets:
        for assets in ticker_combos:
            if (assets in coins['id']) or (assets in coins['symbol']):
                logging.info('Asset {0} is tradeable on {1}'.format(ticker, exchange_name))
                if threading:
                    lock.acquire()
                    can_trade.append(ticker + '-' + exchange_name + '-True')
                    lock.release()
                elif not threading:
                    can_trade.append(ticker + '-' + exchange_name + '-True')
                return True
            else:
                pass

    if threading:
        lock.acquire()
        logging.info('Asset {0} is not tradeable on {1}'.format(ticker, exchange_name))
        can_trade.append(ticker + '-' + exchange_name + '-False')
        lock.release()
    elif not threading:
        logging.info('Asset {0} is not tradeable on {1}'.format(ticker, exchange_name))
        can_trade.append(ticker + '-' + exchange_name + '-False')
    return False


def get_ticker_combos(ticker):
    """Takes a ticker and returns a list of similar tickers and symbols. Useful for quickly searching if a given
    ticker is being traded on an exchange."""

    # Define variables.
    split_ticker = []
    new_tickers = []
    traded_asset = ''
    base_asset = ''

    # Split ticker by asset and base currency
    if '/' in ticker:
        split_ticker = ticker.split('/')
        traded_asset = split_ticker[0]
    elif '-' in ticker:
        split_ticker = ticker.split('-')
        traded_asset = split_ticker[0]
    elif ('-' not in ticker) and ('/' not in ticker):
        if ('USDT' in ticker) or ('USD' in ticker):
            if 'USDT' in ticker:
                replace_ticker = ticker.replace('USDT', '')
                traded_asset = replace_ticker
            elif 'USD' in ticker:
                replace_ticker = ticker.replace('USD', '')
                traded_asset = replace_ticker
        else:
            traded_asset = ticker

    if len(split_ticker) > 1:
        base_asset = split_ticker[1]
    elif len(split_ticker) <= 1:
        base_asset = 'USDT'
    token = traded_asset + base_asset
    new_tickers.append(token)

    # Ensure that if base currency is a USD pegged instrument, then both USD and USDT pairs are included.
    if base_asset == 'USDT':
        new_tickers.append(traded_asset + 'USD')
        new_tickers.append(traded_asset + '-' + 'USD')
        new_tickers.append(traded_asset + '/' + 'USD')
        new_tickers.append(traded_asset + '-' + base_asset)
        new_tickers.append(traded_asset + '/' + base_asset)
    elif base_asset == 'USD':
        new_tickers.append(traded_asset + 'USDT')
        new_tickers.append(traded_asset + '-' + 'USD')
        new_tickers.append(traded_asset + '/' + 'USD')
        new_tickers.append(traded_asset + '-' + base_asset)
        new_tickers.append(traded_asset + '/' + base_asset)

    return new_tickers


def candle_packaging(candle_data, extra_data=True):
    """Wraps candle data in a list of dictionaries that's easier to read and work with."""
    length = len(candle_data['Timestamp'])
    candle_list = []

    if extra_data:
        for i in range(length):
            color = ""
            if candle_data['Open'][i] > candle_data['Close'][i]:
                color = 'Red'
            elif candle_data['Open'][i] < candle_data['Close'][i]:
                color = 'Green'
            change_percent = tools.percentage_difference(candle_data['Open'][i], candle_data['Close'][i])
            if change_percent is None:
                change_percent = 0.0
            change_amount = round(candle_data['Close'][i] - candle_data['Open'][i])

            # Candle variables. TWAP is the time weighted average price.
            twap = (candle_data['High'][i] + candle_data['Low'][i] + candle_data['Open'][i] + candle_data['Close'][
                i]) / 4
            candle_range = candle_data['High'][i] - candle_data['Low'][i]
            candle_body = abs(candle_data['Open'][i] - candle_data['Close'][i])
            bottom_wick = 0
            top_wick = 0

            if color == 'Green':
                bottom_wick = candle_data['Open'][i] - candle_data['Low'][i]
                top_wick = candle_data['High'][i] - candle_data['Close'][i]
            elif color == 'Red':
                bottom_wick = candle_data['Close'][i] - candle_data['Low'][i]
                top_wick = candle_data['High'][i] - candle_data['Open'][i]

            # Candle attributes measured as a % of the total body size
            body_percent = round(tools.percent_of(candle_body, candle_range), 2)
            top_wick_percent = round(tools.percent_of(top_wick, candle_range), 2)
            bottom_wick_percent = round(tools.percent_of(bottom_wick, candle_range), 2)

            # Candle dictionary
            candle = {'Timestamp': candle_data['Timestamp'][i],
                      'Open': candle_data['Open'][i],
                      'High': candle_data['High'][i],
                      'Low': candle_data['Low'][i],
                      'Close': candle_data['Close'][i],
                      'Volume': candle_data['Volume'][i],
                      'Color': color,
                      'Change%': change_percent,  # Total price change of candle from open to close
                      'Change$': change_amount,  # Total dollar value of price change for candle period
                      'Candle-Body%': body_percent,  # Size of body as a percent of the total price range
                      'Top-Wick%': top_wick_percent,  # Size of top wick as a percent of the total price range
                      'Bottom-Wick%': bottom_wick_percent,  # Size of bottom wick as percent of the price range
                      'TWAP': round(twap, 2),  # Time weighted average price value
                      'Pivot': round((candle_data['Open'][i] + candle_data['Close'][i]) / 2, 2),
                      'Pivot-Wicks': round((candle_data['Low'][i] + candle_data['High'][i]) / 2, 2)
                      }

            candle = candle_type_analyzer(candle)
            candle_list.append(candle)

    if not extra_data:
        for i in range(len(candle_data['Timestamp'])):
            candle = {'Timestamp': candle_data['Timestamp'][i],
                      'Open': candle_data['Open'][i],
                      'High': candle_data['High'][i],
                      'Low': candle_data['Low'][i],
                      'Close': candle_data['Close'][i],
                      'Volume': candle_data['Volume'][i]
                      }
            candle_list.append(candle)

    return candle_list


def candle_type_analyzer(candle, tolerance=10):
    """Pass a packaged candle as an argument to get a candle type in return. To get packaged candles, get candle data
    with get_candle_data(), and pass the candle data into candle_packaging(). After packaging, pass the candles one at
    at a time into this function to get a body type added into the candle dictionary."""

    if type(candle) == dict:
        # Local variables
        # Taken from parameter data
        top_wick = candle['Top-Wick%']
        bottom_wick = candle['Bottom-Wick%']
        body = candle['Candle-Body%']
        color = candle['Color']
        candle_type = ''
        tol = range(0, tolerance + 1)  # For calculating plus or minus x%

        # Name tag generation variables
        bear_full_body = 'Bear-Full-Body'
        bear_large_body = 'Bear-Large-Body'
        bull_full_body = 'Bull-Full-Body'
        bull_large_body = 'Bull-Large-Body'
        bear_hammer = 'Bear-Hammer'
        bull_hammer = 'Bull-Hammer'
        strong_bear_hammer = 'Strong-Bear-Hammer'
        strong_bull_hammer = 'Strong-Bull-Hammer'
        neutral = 'Neutral'

        # Determine if candle is red or green, then if there is a specific pattern
        if color == 'Red':
            if body > ((top_wick + bottom_wick) - max(tol)):
                candle_type = bear_large_body
                if body > ((top_wick + bottom_wick) * 2):
                    candle_type = bear_full_body

        elif color == 'Green':
            if body > ((top_wick + bottom_wick) - max(tol)):
                candle_type = bull_large_body
                if body > ((top_wick + bottom_wick) * 2):
                    candle_type = bull_full_body

        # Bear hammer and reversal
        if top_wick > ((body + bottom_wick) - max(tol)):
            candle_type = bear_hammer
            if top_wick > ((body + bottom_wick) * 2):
                candle_type = strong_bear_hammer

        # Bull hammer and reversal
        if bottom_wick > ((body + top_wick) - max(tol)):
            candle_type = bull_hammer
            if bottom_wick > ((body + top_wick) * 2):
                candle_type = strong_bull_hammer

        # If the the body, top wick, and bottom wick are 33% plus or minus tolerance%, pattern is neutral
        if 20 < body < 50:
            if 10 < top_wick < 45 and 10 < bottom_wick < 45:
                candle_type = neutral

        # Doji candles. Characterized by small bodies and long wicks of similar size.
        if abs(top_wick - bottom_wick) <= 40:
            if top_wick > (body * 1.5) and bottom_wick > (body * 1.5):
                candle_type = 'Doji'

        # Dragonfly (bull) and Gravestone (bear) doji candles
        if (body + top_wick) < 12:
            candle_type = 'Bull-Doji'

        if (body + bottom_wick) < 12:
            candle_type = 'Bear-Doji'

        candle['Type'] = candle_type
        return candle

    elif type(candle) == list:
        logging.info('Analyzing candle body types...')
        for i in candle:
            candle_type_analyzer(i)
        return candle

    else:
        logging.warning('Must pass single candle dictionary or list of candle dictionaries as argument.')


def bar_patterns(candles, bars):
    """Pass a set of packaged candles as an argument and if they match a known reversal pattern, return the pattern
    name. Get packaged candles by passing candle data into the candle_packing() function. Get candle data with
    get_candle_data(). Pass a single digit into the bars= parameter to get 2-bar, 3-bar, or 4-bar patterns. Pass a
    tuple with 2, 3, or 4 in it to get multiple bar patterns per candle."""

    if type(bars) == int:
        # Only support 2, 3, and 4 bar patterns
        if not 1 < bars < 5:
            logging.warning('Only 2, 3, and 4 bar patterns supported')
            return candles

        bull_reversals = ('Bull-Hammer', 'Strong-Bull-Hammer', 'Bull-Doji', 'Doji')
        bear_reversals = ('Bear-Hammer', 'Strong-Bear-Hammer', 'Bear-Doji', 'Doji')

        # If the function argument is not a list of dictionaries, exit.
        if not type(candles) == list or 'Open' not in candles[0].keys():
            logging.warning('Must pass list of dictionaries as candle data')
            return candles

        # If there aren't enough candles in the list, then do not proceed.
        if not len(candles) >= bars:
            logging.info('Not enough candles to analyze bar patterns')
            return candles

        # 2 bar patterns
        if bars == 2:

            key = '2bar'

            # Loop through list of candles
            for i in range(len(candles) - (bars - 1)):
                # Variables
                first_candle = candles[i]
                second_candle = candles[i + 1]

                # Bullish engulfing candle
                if first_candle['Color'] == 'Red':
                    if second_candle['Close'] > first_candle['Open']:
                        second_candle[key] = 'Bullish-Engulfing'

                # Bearish engulfing candle
                elif first_candle['Color'] == 'Green':
                    if second_candle['Close'] < first_candle['Open']:
                        second_candle[key] = 'Bearish-Engulfing'

                # Possible top
                elif first_candle['Color'] == 'Green':
                    if first_candle['Type'] == 'Bull-Full-Body' or first_candle['Type'] == 'Bull-Large-Body':
                        if second_candle['Type'] in bear_reversals:
                            second_candle[key] = 'Top'

                # Possible bottom
                elif first_candle['Color'] == 'Red':
                    if first_candle['Type'] == 'Bear-Full-Body' or first_candle['Type'] == 'Bear-Large-Body':
                        if second_candle['Type'] in bull_reversals:
                            second_candle[key] = 'Bottom'

                # Possible reversals
                elif first_candle['Color'] == 'Green':
                    if first_candle['Type'] == 'Bull-Full-Body' or first_candle['Type'] == 'Bull-Large-Body':
                        if second_candle['Close'] < first_candle['Pivot']:
                            second_candle[key] = 'Possible-Top'

                elif first_candle['Color'] == 'Red':
                    if first_candle['Type'] == 'Bear-Full-Body' or first_candle['Type'] == 'Bear-Large-Body':
                        if second_candle['Close'] > first_candle['Pivot']:
                            second_candle[key] = 'Possible-Bottom'

        # 3 bar patterns
        if bars == 3:

            key = '3bar'

            # Loop through list of candles
            for i in range(len(candles) - (bars - 1)):

                # Variables
                first_candle = candles[i]
                second_candle = candles[i + 1]
                third_candle = candles[i + 2]
                first_range = abs(candles[i]['Change$'])
                second_range = abs(candles[i + 1]['Change$'])
                third_range = abs(candles[i + 2]['Change$'])

                # Bullish engulfing candle
                if first_candle['Color'] == 'Red' and second_candle['Color'] == 'Red':
                    if second_range < third_range:
                        if third_candle['Close'] > first_candle['Open']:
                            third_candle[key] = 'Bullish-Engulfing'

                # Bearish engulfing candle
                elif first_candle['Color'] == 'Green' and second_candle['Color'] == 'Green':
                    if second_range < third_range:
                        if third_candle['Close'] < first_candle['Open']:
                            third_candle[key] = 'Bearish-Engulfing'

                # Possible end of pump
                elif first_candle['Color'] == 'Green' and first_range > second_range:
                    if second_candle['Color'] == 'Green' and second_range > third_range:
                        if third_candle['Type'] in bear_reversals:
                            third_candle[key] = 'Top'

                # Possible end of sell off
                elif first_candle['Color'] == 'Red' and first_range > second_range:
                    if second_candle['Color'] == 'Red' and second_range > third_range:
                        if third_candle['Type'] in bull_reversals:
                            third_candle[key] = 'Bottom'

                # Evening-Star bearish reversal
                elif first_candle['Color'] == 'Green':
                    if first_candle['Type'] == 'Bull-Full-Body' or first_candle['Type'] == 'Bull-Large-Body':
                        if second_range * 2 < first_range or second_candle['Type'] in bear_reversals:
                            if third_candle['Close'] < first_candle['Pivot']:
                                third_candle[key] = 'Evening-Star'

                # Morning-Star bullish reversal
                elif first_candle['Color'] == 'Red':
                    if first_candle['Type'] == 'Bear-Full-Body' or first_candle['Type'] == 'Bear-Large-Body':
                        if second_range * 2 < first_range or second_candle['Type'] in bull_reversals:
                            if third_candle['Close'] > first_candle['Pivot']:
                                third_candle[key] = 'Morning-Star'

                # Three white soldiers (bullish)
                elif first_candle['Color'] == 'Green' and second_candle['Color'] == 'Green':
                    if third_candle['Color'] == 'Green':
                        if first_range <= second_range <= third_range:
                            third_candle[key] = 'Bullish-Momentum'

                # Three black crows (bearish)
                elif first_candle['Color'] == 'Red' and second_candle['Color'] == 'Red':
                    if third_candle['Color'] == 'Red':
                        if first_range <= second_range <= third_range:
                            third_candle[key] = 'Bearish-Momentum'

        # 4 bar patterns
        if bars == 4:

            key = '4bar'

            # Loop through list of candles
            for i in range(len(candles) - (bars - 1)):

                # Variables
                first_candle = candles[i]
                second_candle = candles[i + 1]
                third_candle = candles[i + 2]
                fourth_candle = candles[i + 3]

                # Bullish engulfing candle
                if first_candle['Color'] == 'Red' and second_candle['Color'] == 'Red':
                    if third_candle['Color'] == 'Red' and third_candle['Low'] < second_candle['Low']:
                        if fourth_candle['Color'] == 'Green' and fourth_candle['Close'] > first_candle['Open']:
                            fourth_candle[key] = 'Bullish-Engulfing'

                # Bearish engulfing candle
                elif first_candle['Color'] == 'Green' and second_candle['Color'] == 'Green':
                    if third_candle['Color'] == 'Green' and third_candle['Low'] > second_candle['Low']:
                        if fourth_candle['Color'] == 'Red' and fourth_candle['Close'] < first_candle['Open']:
                            fourth_candle[key] = 'Bearish-Engulfing'

                # Round bottom
                elif first_candle['Color'] == 'Red' and second_candle['Low'] < first_candle['Low']:
                    if second_candle in bull_reversals and third_candle in bull_reversals:
                        if fourth_candle['Color'] == 'Green':
                            if fourth_candle['Close'] > first_candle['Pivot']:
                                fourth_candle[key] = 'Bottom'

                # Round top
                elif first_candle['Color'] == 'Green' and second_candle['Low'] > first_candle['Low']:
                    if second_candle in bear_reversals and third_candle in bear_reversals:
                        if fourth_candle['Color'] == 'Red':
                            if fourth_candle['Close'] < first_candle['Pivot']:
                                fourth_candle[key] = 'Top'

                # Failed bullish engulfing candle
                elif first_candle['Color'] == 'Red' and second_candle['Color'] == 'Red':
                    if abs(second_candle['Change%']) < abs(third_candle['Change%']):
                        if third_candle['Close'] > first_candle['Open']:
                            if fourth_candle['Close'] < first_candle['Close']:
                                fourth_candle[key] = 'Failed-Bullish-Engulfing'

                # Failed bearish engulfing candle
                elif first_candle['Color'] == 'Green' and second_candle['Color'] == 'Green':
                    if abs(second_candle['Change%']) < abs(third_candle['Change%']):
                        if third_candle['Close'] < first_candle['Open']:
                            if fourth_candle['Close'] > first_candle['Close']:
                                fourth_candle[key] = 'Failed-Bearish-Engulfing'

    elif type(bars) == tuple:
        for num in bars:
            bar_patterns(candles, bars=num)

    return candles


def calculate_num_candles(timestamp_a, timestamp_b=None, time_frame='1m'):
    """Pass a timestamp from a candle dictionary as an argument to determine how many candles of given time_frame
    will be needed to get from timestamp A to timestamp B. If timestamp B is not provided then the current time
    is assumed."""

    num_candles = 1
    timestamp_a = int(timestamp_a / 1000)
    if timestamp_b is None:
        most_recent_candle = unix_tool(time_frame, update=True) / 1000
        # Loop until timestamp A is greater than the most recent candle timestamp
        while timestamp_a <= most_recent_candle:
            timestamp_a += unix_dict_key[time_frame]
            if timestamp_a <= most_recent_candle:
                num_candles += 1

    elif timestamp_b is not None:
        timestamp_b = int(timestamp_b / 1000)
        # Loop until timestamp A is greater than timestamp B
        while timestamp_a <= timestamp_b:
            timestamp_a += unix_dict_key[time_frame]
            if timestamp_a <= timestamp_b:
                num_candles += 1

    return num_candles


def plot_data(data, slider=False, log_scale=True, color='dark', plots='ema,volume,rsi,stoch_rsi', window_size=None):
    """Pass a list of candle data as an argument. Each element of the list should be a dictionary containing candle
    data. Use indicators.get_candle_data() to grab data, and indicators.candle_packaging() to format the data. Change
    the plots= parameter to ema for EMA ribbon data, bbands for Bollinger Band data, or all for everything."""

    logging.info('Building chart data.')
    # Setup local variables
    plots = plots.lower()
    if not isinstance(data, Chart):
        raise TypeError('Data must be of type Chart in order to plot.')

    asset_name = data.symbol
    plots = plots.lower()
    indicators = None
    fig = None
    count = 1
    row_heights = [1]
    if not plots == 'all':
        indicators = plots.split(",")
    elif plots == 'all':
        indicators = ['ema', 'bbands', 'volume', 'rsi', 'stoch_rsi', 'pivots', 'trend_lines']
    num_subplots = len(indicators) + 1
    for name in indicators:  # Edit this loop when adding VPVR functionality later.
        if name == 'ema':
            num_subplots -= 1
        if name == 'bbands':
            num_subplots -= 1
        if name == 'vpvr':
            num_subplots -= 1
        if name == 'trend_lines':
            num_subplots -= 1
        if name == 'twap':
            num_subplots -= 1
        elif name != 'ema' and name != 'bbands' and name != 'vpvr' and name != 'trend_lines':
            row_heights[0] = round(row_heights[0] - 0.1, 1)
            row_heights.append(0.1)
    df = None
    if isinstance(data, pd.DataFrame):
        df = data
    elif not isinstance(data, pd.DataFrame):
        df = format_data(data, window=window_size)

    # Format chart style
    colors = {'dark': 'plotly_dark', 'white': 'simple_white', 'default': 'plotly', 'light': 'plotly_white',
              'grey': 'ggplot2'}
    if num_subplots == 1:
        fig = go.Figure()
    elif num_subplots > 1:
        fig = make_subplots(rows=num_subplots, cols=1, vertical_spacing=0.02, row_heights=row_heights)

    # Add candles
    if log_scale:
        if num_subplots > 1:
            fig.update_yaxes(type='log', row=1, col=1)
        elif num_subplots == 1:
            fig.update_yaxes(type='log')
    fig.add_trace(go.Candlestick(x=df['Date'], open=df['Open'], high=df['High'],
                                 low=df['Low'], close=df['Close'], showlegend=False))

    # Plot pivot points
    if 'pivots' in indicators:
        green_markers = dict(color='#00e100', size=8, line=dict(width=2, color='#267f00'))
        red_markers = dict(color='#de021f', size=8, line=dict(width=2, color='#a00000'))
        top_pivots = {'Price': [], 'Date': []}
        bottom_pivots = {'Price': [], 'Date': []}
        candles = None
        title = go.scatter.Legendgrouptitle(text='Pivots')
        if window_size is None:
            candles = data.candles
        elif window_size is not None:
            candles = data.candles[window_size * -1:]
        for candle in candles:
            if 'Pivot-Bottom' in candle.keys():
                bottom_pivots['Price'].append(candle['Pivot-Bottom'])
                bottom_pivots['Date'].append(dt.fromtimestamp(int(candle['Timestamp']) / 1000))
            elif 'Pivot-Top' in candle.keys():
                top_pivots['Price'].append(candle['Pivot-Top'])
                top_pivots['Date'].append(dt.fromtimestamp(int(candle['Timestamp']) / 1000))
        top_df = pd.DataFrame(top_pivots)
        bottom_df = pd.DataFrame(bottom_pivots)
        fig.add_trace(go.Scatter(x=top_df['Date'], y=top_df['Price'], name='Top Pivots', mode='markers',
                                 marker=red_markers, legendgroup='Pivots', legendgrouptitle=title), row=1, col=1)
        fig.add_trace(go.Scatter(x=bottom_df['Date'], y=bottom_df['Price'], name='Bottom Pivots', mode='markers',
                                 marker=green_markers, legendgroup='Pivots', legendgrouptitle=title), row=1, col=1)

    # Draw trend lines
    if 'trend_lines' in indicators:
        lines = data.trend_lines
        title = go.scatter.Legendgrouptitle(text='Trend Lines')
        if len(lines) > 0:
            for line in lines:
                d = {'Date': [], 'Price': []}
                d['Date'].append(dt.fromtimestamp(int(line.start['Timestamp'] / 1000)))
                d['Price'].append(line.start['Price'])
                d['Date'].append(dt.fromtimestamp(int(line.end['Timestamp'] / 1000)))
                d['Price'].append(line.end['Price'])
                df = pd.DataFrame(d)
                if num_subplots > 1:
                    fig.add_trace(go.Scatter(x=d['Date'], y=d['Price'], name='Trend', legendgroup='Trend Lines',
                                             legendgrouptitle=title, line=dict(color='#fff300')), row=1, col=1)
                elif num_subplots == 1:
                    fig.add_trace(go.Scatter(x=d['Date'], y=d['Price'], name='Trend', legendgroup='Trend Lines',
                                             legendgrouptitle=title, line=dict(color='#fff300')))

    # EMA lines
    if 'ema' in indicators:
        title = go.scatter.Legendgrouptitle(text='EMA Ribbon')
        fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA13'], line=dict(color='#00FF0E'), name='13 EMA',
                                 legendgroup='EMA Ribbon', legendgrouptitle=title))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA21'], line=dict(color='#FFF900'), name='21 EMA',
                                 legendgroup='EMA Ribbon', legendgrouptitle=title,
                                 fill='tonexty', fillcolor='rgba(0,255,14,0.300)'))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA34'], line=dict(color='#FF8400'), name='34 EMA',
                                 legendgroup='EMA Ribbon', legendgrouptitle=title,
                                 fill='tonexty', fillcolor='rgba(255,249,0,0.300)'))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA55'], line=dict(color='#FF0000'), name='55 EMA',
                                 legendgroup='EMA Ribbon', legendgrouptitle=title,
                                 fill='tonexty', fillcolor='rgba(255,132,0,0.300)'))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA200'], line=dict(color='#0075FF'), name='200 EMA',
                                 legendgroup='EMA Ribbon', legendgrouptitle=title, ))
        fig.add_trace(go.Scatter(x=df['Date'], y=df['EMA233'], line=dict(color='#000BFF'), name='233 EMA',
                                 legendgroup='EMA Ribbon', legendgrouptitle=title,
                                 fill='tonexty', fillcolor='rgba(0,117,255,0.300)'))

    # Bollinger bands
    if 'bbands' in indicators:
        if 'ema' not in indicators:
            title = go.scatter.Legendgrouptitle(text='Bollinger Bands')
            fig.add_trace(go.Scatter(x=df['Date'], y=df['High_BBand'], line=dict(color='#B200FF'),
                                     name='Upper Bollinger Band', legendgroup='Bollinger Bands',
                                     legendgrouptitle=title))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Low_BBand'], line=dict(color='#B200FF'),
                                     name='Lower Bollinger Band', legendgroup='Bollinger Bands',
                                     legendgrouptitle=title, fill='tonexty', fillcolor='rgba(178,0,255,0.300)'))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Mid_BBand'], line=dict(color='#FF00FE'),
                                     name='Middle Bollinger Band', legendgroup='Bollinger Bands',
                                     legendgrouptitle=title))
        elif 'ema' in indicators:
            title = go.scatter.Legendgrouptitle(text='Bollinger Bands')
            fig.add_trace(go.Scatter(x=df['Date'], y=df['High_BBand'], line=dict(color='#B200FF'),
                                     name='Upper Bollinger Band', legendgroup='Bollinger Bands',
                                     legendgrouptitle=title))
            fig.add_trace(go.Scatter(x=df['Date'], y=df['Low_BBand'], line=dict(color='#B200FF'),
                                     name='Lower Bollinger Band', legendgroup='Bollinger Bands',
                                     legendgrouptitle=title))

    # Volume bars
    if 'volume' in indicators:
        title = go.bar.Legendgrouptitle(text='Volume')
        count += 1
        key = None
        for col in df.columns:
            if 'Volume_' in col:
                key = col
        if key is None:
            raise Exception('Volume dictionary key not found in data frame.')

        fig.add_trace(go.Bar(x=df['Date'], y=df['Volume'], name='', legendgroup='Volume',
                             legendgrouptitle=title, marker=dict(color='#10E5BC')), row=count, col=1)
        fig.add_trace(go.Scatter(x=df['Date'], y=df[key], name='Volume Moving Average', legendgroup='Volume',
                                 line=dict(color='#FF4900')), row=count, col=1)
        fig.update_yaxes(type='linear', row=count, title_text='Volume')

    # TWAP
    if 'twap' in indicators:
        title = go.scatter.Legendgrouptitle(text='Time Weighted Average')
        count += 1
        key = None
        for col in df.columns:
            if 'TWAP_' in col:
                key = col
        if key is None:
            raise Exception('TWAP dictionary key not found')

        fig.add_trace(go.Scatter(x=df['Date'], y=df[key], name='Time Weighted Average', legendgroup='TWAP',
                                 legendgrouptitle=title, line=dict(color='#FF4900')), row=1, col=1)

    # RSI plot
    if 'rsi' in indicators:
        title = go.scatter.Legendgrouptitle(text='RSI')
        count += 1
        fig.add_trace(go.Scatter(x=df['Date'], y=df['RSI'], name='', legendgroup='RSI', legendgrouptitle=title,
                                 line=dict(color='#FF4900')),
                      row=count, col=1)
        fig.update_yaxes(type='linear', row=count, title_text='RSI')

    # Stochastic RSI
    if 'stoch_rsi' in indicators:
        title = go.scatter.Legendgrouptitle(text='Stochastic RSI')
        count += 1
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Stoch-RSI-%K'], name='K Line', line=dict(color='#FF4900'),
                                 legendgroup='Stochastic RSI', legendgrouptitle=title), row=count, col=1)
        fig.add_trace(go.Scatter(x=df['Date'], y=df['Stoch-RSI-%D'], name='D Line', line=dict(color='#10E5BC'),
                                 legendgroup='Stochastic RSI', legendgrouptitle=title, ), row=count, col=1)
        fig.update_yaxes(type='linear', row=count, title_text='Stoch-RSI')

    # Chart layout configuration
    if asset_name is None:
        fig.update_layout(xaxis_rangeslider_visible=slider, template=colors[color], yaxis_title='Asset Price')
    elif asset_name is not None:
        title = asset_name + ' Price'
        fig.update_layout(xaxis_rangeslider_visible=slider, template=colors[color], yaxis_title=title)

    if num_subplots > 1:
        fig.update_xaxes(showticklabels=False)
        fig.update_xaxes(showticklabels=True, row=(num_subplots - 1), col=1)
    fig.show()


def format_data(data, window=None):
    """Can reformat candles to be a list of dictionaries or a dictionary of lists."""

    # Format data
    if type(data) == list:
        dct = {'Date': [], 'Timestamp': [], 'Open': [], 'High': [], 'Low': [], 'Close': [], 'Volume': []}
        for i in data:
            timestamp = int(i['Timestamp'] / 1000)
            dct['Date'].append(dt.fromtimestamp(timestamp))
            dct['Timestamp'].append(timestamp)
            dct['Open'].append(i['Open'])
            dct['High'].append(i['High'])
            dct['Low'].append(i['Low'])
            dct['Close'].append(i['Close'])
            dct['Volume'].append(i['Volume'])
        df = pd.DataFrame(dct)

    elif type(data) == dict:
        keys = ['Timestamp', 'Open', 'High', 'Low', 'Close']
        dct_keys = data.keys()
        for key in keys:
            if key in dct_keys:
                if type(data[key]) == list:
                    continue
                else:
                    raise TypeError('Received data does not resemble candlestick data')
            else:
                raise TypeError('Received data does not resemble candlestick data')

        data['Date'] = []
        for timestamp in data['Timestamp']:
            date = dt.fromtimestamp(int(timestamp / 1000))
            data['Date'].append(date)
        df = pd.DataFrame(data)

    elif isinstance(data, Chart):
        dct = {}

        # Format candle data first
        candles = format_data(data.candles)
        dct['Timestamp'] = candles['Timestamp']
        dct['Date'] = candles['Date']
        dct['Open'] = candles['Open']
        dct['Close'] = candles['Close']
        dct['High'] = candles['High']
        dct['Low'] = candles['Low']
        dct['Volume'] = candles['Volume']

        # EMA Data
        ema = data.ema_ribbon
        dct['EMA13'] = ema.ema13
        dct['EMA21'] = ema.ema21
        dct['EMA34'] = ema.ema34
        dct['EMA55'] = ema.ema55
        dct['EMA200'] = ema.ema200
        dct['EMA233'] = ema.ema233

        # Volume Moving Average
        v = data.volume_moving_average.volume_ma
        key = data.volume_moving_average.key
        dct[key] = v

        # TWAP Moving Average
        twap = data.time_weighted_average.twap_moving_average
        key = data.time_weighted_average.key
        dct[key] = twap

        # Bollinger Band Data
        bbands = data.bbands
        dct['High_BBand'] = bbands.high_band
        dct['Mid_BBand'] = bbands.mid_band
        dct['Low_BBand'] = bbands.low_band

        # RSI data
        _rsi = data.rsi
        dct['RSI'] = _rsi.rsi

        # Stochastic RSI
        srsi = data.stoch_rsi
        dct['Stoch-RSI-%K'] = srsi.k
        dct['Stoch-RSI-%D'] = srsi.d

        # Convert to data frame
        df = pd.DataFrame(dct)

    else:
        raise TypeError('Received data does not resemble candlestick data')

    if window is not None:
        df2 = df.iloc[window * -1:]
        return df2
    else:
        return df


def log_string(string, level='info'):
    """Pass a string to add it to the run log. Most useful if accessing indicators.py from another script."""
    if level == 'info':
        logging.info(string)
    elif level == 'warning':
        logging.warning(string)
