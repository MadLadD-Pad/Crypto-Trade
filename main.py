import logging
# import config
import indicators as ind
# import schedule
# import tools
# import tools

PORTFOLIO = ['BTC', 'ETH', 'EGLD', 'SOL', 'LUNA']
TIME_FRAMES = ['3m', '5m', '15m', '1h', '4h', '1d', '1w']
TIME = '4h'


def main():
    """Main program: Write schedule and instructions here."""
    # Get data for tickers in the watchlist
    asset_list = get_watchlist_data(PORTFOLIO)
    asset_objects = []

    # Scan charts for trades
    for asset in asset_list:
        asset_obj = ind.Asset(asset)
        asset_objects.append(asset_obj)


def test():
    """For testing functions without needing to change the main program."""
    egld = ind.Asset('EGLD', time_frames='4h')
    ind.plot_data(egld.chart_4h, plots='ema,volume,rsi')


def get_watchlist_data(watchlist):
    """Pass in a list of ticker symbols to generate a list of crypto objects."""

    asset_list = []

    # Loop through watch list and instantiate new asset objects from watchlist symbols.
    logging.info('Building objects from assets in watchlist...')
    for asset in watchlist:
        obj = ind.Asset(asset)
        asset_list.append(obj)
    return asset_list


if __name__ == "__main__":
    test()
