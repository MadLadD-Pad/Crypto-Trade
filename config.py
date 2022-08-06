import logging
import os
import csv
from os import chdir, scandir
from datetime import datetime as dt

import indicators

MAIN_DIR = 'EDIT THIS TO THE MAIN DIRECTORY SUCH AS C:\TradeBot'
VPVR_DATA = 'EDIT THIS TO BE THE SAME AS THE ABOVE DIRECTORY PLUS \VPVR SUCH AS C:\TradeBot\VPVR'
CANDLE_FOLDER = 'EDIT THIS TO BE THE SAME AS THE MAIN_DIR PLUS Candle_Data SUCH AS C:\TradeBot\Candle_Data'


def save_candle_data(ticker, data, extension='csv', exchange=None):
    """The data parameter should be data that was gathered from the get_candle_data or get_candle_data_chunks method,
    then wrapped with the candle_packaging function. Each ticker_symbol should be an asset and a base currency divided
    by a '/' such as BTC/USDT. The method indicators.get_ticker_combos can be useful for generating new tickers and
    symbols if one is needed."""
    indicators.log_string('Saving candle data')

    # Wrap data if it isn't wrapped.
    key_matches = ['Open', 'High', 'Low', 'Close']
    if type(data) == dict:
        for key in key_matches:
            if key in data.keys():
                pass
            else:
                raise Exception('Data does not match candle stick format')
        new_data = indicators.candle_packaging(data, extra_data=False)
        data = new_data

    elif type(data) == list:
        if type(data[0]) == dict:
            for key in key_matches:
                if key in data[0].keys():
                    pass
                else:
                    raise Exception('Data does not match candle stick format')
        else:
            raise Exception('Data does not match candle stick format')

    # Set time frame
    name = ticker.split()
    symbol = name[0]
    time_frame = None
    num1 = int(data[0]['Timestamp'] / 1000)
    num2 = int(data[1]['Timestamp'] / 1000)
    for key in indicators.unix_dict_key.keys():
        if (num2 - num1) == indicators.unix_dict_key[key]:
            time_frame = key

    # Initialize variables.
    xchng = exchange
    str1 = symbol + '-' + str(time_frame)
    if '/' in str1:
        str2 = str1.replace('/', '-')
    else:
        str2 = str1
    token = str2 + '.' + extension
    time = str(dt.now())
    chdir(CANDLE_FOLDER)
    file = open(token, 'w')

    if extension == 'py':
        # Initialize variables.
        title = '"""Candle data for {0} captured from {2} on: {1}"""\n'.format(str1, time, xchng)
        var_name = symbol.lower() + '_candles'

        # Change directory to InfoDump folder, write data, and return to main directory.
        file.write(title + '\n{} = ['.format(var_name))
        dict_length = len(data[0])
        list_length = len(data)
        l_counter = 0
        for i in data:
            l_counter += 1
            d_counter = 0
            if l_counter > 1:
                file.write('\t\t\t\t')
            file.write('{')
            for k, v in i.items():
                d_counter += 1
                data_string = ''
                if d_counter % 4 == 0:
                    file.write('\n\t\t\t\t')
                if d_counter < dict_length:
                    if type(v) != str:
                        data_string = "'{0}': {1}, ".format(k, v)
                    elif type(v) == str:
                        data_string = "'{0}': '{1}', ".format(k, v)
                elif d_counter == dict_length:
                    if type(v) != str:
                        data_string = "'{0}': {1}".format(k, v)
                    elif type(v) == str:
                        data_string = "'{0}': '{1}'".format(k, v)
                file.write(data_string)
            if l_counter < list_length:
                file.write('},\n')
            elif l_counter == list_length:
                file.write('}]')

    elif extension == 'txt':
        title = 'Candle data for {0} captured from {2} on: {1}\n\n'.format(str1, time, xchng)
        chdir(CANDLE_FOLDER)
        file = open(token, 'w')
        file.write(title)
        length = len(data[0])
        for candle in data:
            data_string = ''
            file.write('{')
            counter = 0
            for k, v in candle.items():
                counter += 1
                if counter < length:
                    if type(v) == str:
                        data_string = "'{0}': '{1}', ".format(k, v)
                    elif type(v) != str:
                        data_string = "'{0}': {1}, ".format(k, v)
                elif counter == length:
                    if type(v) == str:
                        data_string = "'{0}': '{1}'".format(k, v)
                    elif type(v) != str:
                        data_string = "'{0}': {1}".format(k, v)
                file.write(data_string)
            file.write('}\n')

    elif extension == 'csv':
        for candle in data:
            temp_list = []
            if candle is data[0]:
                for name in candle:
                    temp_list.append(name)
            elif candle is not data[0]:
                for value in candle.values():
                    if type(value) != str:
                        value = str(value)
                    temp_list.append(value)
            csv_string = ','.join(temp_list)
            file.write(csv_string + '\n')

    file.close()
    chdir(MAIN_DIR)


def update_candles_csv(ticker, time_frame):
    """Scans the Candle_Data directory and updates the saved candle data with current data if the file exists."""
    indicators.log_string('Updating stored candle data.')

    # Set variables
    file_name = ''
    new_csv_data_strings = []
    if '/' in ticker:
        lst = ticker.split('/')
        new_ticker = lst[0]
    else:
        raise Exception('Ticker needs base currency such as {}/USDT, found {} instead.'.format(ticker, ticker))
    time = indicators.unix_time * 1000
    unix_key = indicators.unix_dict_key[time_frame] * 1000

    # Scan for files
    with os.scandir(CANDLE_FOLDER) as dirs:
        detected = False
        for entry in dirs:
            if new_ticker in entry.name:
                detected = True
                if time_frame in entry.name:
                    if 'csv' in entry.name:

                        # File exists
                        file_name = entry.name
                        with open(entry) as file:
                            reader = csv.reader(file)
                            csv_list = list(reader)
                            if 'Timestamp' in csv_list[0]:
                                index = csv_list[0].index('Timestamp')
                            most_recent_record = int(csv_list[-1][index])
                            if (time - unix_key) > most_recent_record:
                                since = most_recent_record + unix_key
                                data = indicators.get_candle_data_chunks(ticker, time_frame, since=since)
                                new_data = indicators.candle_packaging(data, extra_data=False)
                                data = new_data
                                for candle in data:
                                    csv_string = []
                                    time_string = str(candle['Timestamp'])
                                    open_string = str(candle['Open'])
                                    high_string = str(candle['Open'])
                                    low_string = str(candle['Low'])
                                    close_string = str(candle['Close'])
                                    volume_string = str(candle['Volume'])
                                    csv_string.append(time_string)
                                    csv_string.append(open_string)
                                    csv_string.append(high_string)
                                    csv_string.append(low_string)
                                    csv_string.append(close_string)
                                    csv_string.append(volume_string)
                                    new_string = ",".join(csv_string)
                                    new_csv_data_strings.append(new_string)

        # No file exists
        if not detected:
            indicators.log_string('No candle data detected, downloading now. This will take time.')
            candles = indicators.get_candle_data_chunks(ticker, '1m', 300)
            save_candle_data(ticker, candles)
            update_candles_csv(ticker, '1m')
            return

    # Write new candles to file, then close it
    chdir(CANDLE_FOLDER)
    file = open(file_name, 'a')
    for data in new_csv_data_strings:
        file.write(data)
        file.write('\n')
    file.close()
    chdir(MAIN_DIR)


def slice_csv_data(ticker, time_frame, start_time, end_time):
    """Scans the Candle_Data directory for 1m csv files and sends back a slice."""

    # Set local variables
    file_name = ''
    candle_list = []
    if '/' in ticker:
        new_ticker = ticker.split('/')
        ticker = new_ticker[0]
    elif '/' not in ticker:
        ticker = ticker + '/USDT'

    # Scan for file name in Candle_Data directory. If no file is detected, raise exception error
    with os.scandir(CANDLE_FOLDER) as dirs:
        for entry in dirs:
            if ticker in entry.name:
                if time_frame in entry.name:
                    if 'csv' in entry.name:
                        file_name = entry.name

    if file_name == '':
        raise Exception('No file with that name detected')
    else:

        # Scan csv file and gather appropriate data
        chdir(CANDLE_FOLDER)
        with open(file_name, 'r') as file:
            reader = csv.reader(file)
            csv_list = list(reader)
            if csv_list[0][0] == 'Timestamp':
                pass
            else:
                raise Exception('The csv file is not formatted correctly')
            for row in csv_list:
                if row[0] == 'Timestamp':
                    continue
                elif row[0] != 'Timestamp':
                    timestamp = int(row[0])
                    if timestamp < start_time:
                        continue
                    elif start_time <= timestamp <= end_time:
                        candle = {'Timestamp': 0,
                                  'Open': 0,
                                  'High': 0,
                                  'Low': 0,
                                  'Close': 0,
                                  'Volume': 0,
                                  }

                        for i in range(len(row)):
                            if i == 0:
                                candle['Timestamp'] = int(row[i])
                            elif i == 1:
                                candle['Open'] = float(row[i])
                            elif i == 2:
                                candle['High'] = float(row[i])
                            elif i == 3:
                                candle['Low'] = float(row[i])
                            elif i == 4:
                                candle['Close'] = float(row[i])
                            elif i == 5:
                                candle['Volume'] = int(row[i])
                        candle_list.append(candle)

                    elif end_time < timestamp:
                        chdir(MAIN_DIR)
                        return candle_list


def manage_vpvr_data(ticker, time_frame, data, mode='read'):
    """Saves and loads VPVR data from the VPVR_Data directory. Change mode parameter to 'read' if you want to grab data
    from existing VPVR files, 'save' if you want to save currently generated VPVR data, and 'scan' if you simply want
    to know if the data exists or not."""

    # Check object data type
    mode = mode.lower()
    indicators.update_time()
    last_update = None

    # Variables
    if '/' in ticker:
        symbol = ticker.split('/')
        ticker = symbol[0]
    tags = [ticker, time_frame, 'vpvr', str(indicators.unix_time)]
    file_name = ''
    chdir(VPVR_DATA)

    # Scan for file name in Candle_Data directory. If no file is detected, create one and download initial data
    with os.scandir(VPVR_DATA) as dirs:
        for entry in dirs:
            if ticker in entry.name:
                if time_frame in entry.name:
                    if 'csv' in entry.name:
                        file_name = entry.name
                        new_tags = file_name.split('-')
                        if '.csv' in new_tags[-1]:
                            new_tags[-1] = new_tags[-1].replace('.csv', '')
                        last_update = int(new_tags[-1])
                        if mode == 'scan':
                            return True

    # If file doesn't exist
    if file_name == '':
        logging.info('No VPVR data file detected. Generating one.')
        file_name = '-'.join(tags)
        file_name = file_name + '.csv'
        file = open(file_name, 'x')
        file.close()
        if mode == 'scan':
            return False

    # Write data
    if mode == 'save':
        with open(file_name, 'w') as file:
            last_update = indicators.unix_time
            file.write('Channel,Volume\n')
            file.write('Last Update,{}\n'.format(last_update))
            for channel, volume in data.items():
                file.write('{0},{1}\n'.format(channel, volume))

    # Read data
    if mode == 'read':
        with open(file_name, 'r') as file:
            reader = csv.reader(file)
            csv_list = list(reader)
            vpvr_dict = {}
            for row in csv_list:
                if not row[1] == 'Volume':
                    row[1] = int(row[1])
                    vpvr_dict[row[0]] = row[1]
                elif row[1] == 'Volume':
                    del row
            return vpvr_dict
