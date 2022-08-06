import logging
import indicators as ind
from sys import argv

PORTFOLIO = ['BTC', 'ETH', 'EGLD', 'SOL', 'LUNA']
TIME_FRAMES = ['3m', '5m', '15m', '1h', '4h', '1d', '1w']
TIME = '4h'
args = argv
del args[0]


def main():
    """Main program: Write schedule and instructions here."""
    # Get data for tickers in the watchlist
    asset_list = get_watchlist_data(PORTFOLIO)
    asset_objects = []

    # Scan charts for trades
    for crypto in asset_list:
        asset_obj = ind.Asset(crypto)
        asset_objects.append(asset_obj)


def test():
    """For testing functions without needing to change the main program."""
    ind.monitor(asset='EGLD', upper_limit=65.3, lower_limit=64.75)


def get_watchlist_data(watchlist):
    """Pass in a list of ticker symbols to generate a list of crypto objects."""

    asset_list = []

    # Loop through watch list and instantiate new asset objects from watchlist symbols.
    logging.info('Building objects from assets in watchlist...')
    for crypto in watchlist:
        obj = ind.Asset(crypto)
        asset_list.append(obj)
    return asset_list


if __name__ == "__main__":
    if len(args) > 0:
        if args[0].lower() == 'monitor':
            if len(args) < 4:
                raise Exception("Missing arguments: ticker, upper limit, or lower limit.")
            elif args[1].lower() == 'help':
                print('Pass ticker name, upper limit, and lower limit as arguments. Such as ETH 1000 1200')
            else:
                asset = args[1]
                upper = args[2]
                lower = args[3]
                ind.monitor(asset=asset, upper_limit=upper, lower_limit=lower)
    else:
        test()
