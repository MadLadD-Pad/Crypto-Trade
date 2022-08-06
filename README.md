# Crypto-Trade
Tools for automated crypto trading. Most of the funcionatlity is in the indicators.py script. Within that script, there are a few functions that do most of the work. The first one, **get_candle_data()**, simply pulls candle data from a variety of different crypto exchanges. The function stores the data as a dicitonary with candle elements Open, High, Low, Close, Volume, and Timestamp as the dicitonary keys. The values of the dictionary are lists of data points. For example, {'Close': [100, 98, 102]} would be the closing prices of 3 candles. It's best to use Binance as the exchange of chouice because they allow 1000 candles at a time while most other supported exchanges support a maximum of 100-200 candles per API request. Below I will highlight a few functions from different scripts and explain what they're used for.

**indicators.py**

**get_candle_data()**: Pulls candle data from exchanges and stores them in a dictionary, limited to 1,000 candles on Binance per API request, and 100-200 candles per request on other exchanges.

**get_candle_data_chunks()**: This is perhaps the most useful function in the script. It can send multiple API requests to get as much candle data as you desire. You can specify how many "chunks" of data to get and the size of each chunk. For example, 
get_candle_data_chunks("ETH/USDT", "4h", chunks=3, candle_limit=1000) would get the 3,000 most recent 4 hour ETH candles. The fuction can be used in another way as well if you want to look back at a specific window of time. You can use unix timestamps in milliseconds to specify a start time and an end time such as get_candle_data_chunks("ETH/USDT", "1h", since=1652173200000, until=1652191200000) would return each 1 hour ETH candle that has occured between those two timestamps.

**candle_packaging()**: This function takes data gathered from get_candle_data() or get_candle_data_chunks() and wraps them into a list of dicionaries where each dictionary is 1 candle. Such as [{'Open': 100, 'High': 105, 'Low': 97, 'Close': 101, 'Volume': 100000, 'Timestamp': 1652173200000}]. There is an optional parameter that can be used to generate a lot of other useful information about the candle such as the color (red or green), the total percentage change from open to close or the total dollar amount change, what type of candle it is (doji, bullish-engulphing, etc.), and a lot more.

**class Chart**: Generating an object of class Chart will get the most recent 2,000 candles and calculate several indicators of your choice. For example,
eth = Chart("ETH", "4h", exchange="Binance") will build a 4 hour ETH chart with data pulled from Binance and build exponential moving averages, bollinger bands, time weighted average prices, VPVR volume profile, RSI, and Stochastic-RSI.

**class Asset**: An Asset class object simply creates multiple chart objects and stores them in the Asset object for ease of access. Some other data that is stored in the Asset object class are things such as which exchanges the asset is trading on, and a variety of ticker symbols.
