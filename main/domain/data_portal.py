from datetime import datetime
from typing import *

import requests
from pandas import Timestamp, DataFrame
from abc import *

from pandas import Timedelta
from trading_calendars import TradingCalendar


class HistoryDataLoader(object):
    """
    该加载器是用来获取历史的时序数据的，由于每种时序数据获取历史数据的方法都一样，所以把供应商名和时序类型名作为该加载起的属性，用户需要
    加载某个时序数据的话，只需要指定对应的时序类型名即可。 因为不同数据数据供应航
    对于每一个时序类型， 需要提供一个在回测中获取历史数据的方法以及一个在实盘的时候获取历史数据方法，实盘的时候获取历史数据是以当前时间
    从券商获取的。
    """

    def __init__(self, data_provider_name: str, ts_type_name: str):
        self.data_provider_name = data_provider_name
        self.ts_type_name = ts_type_name
        self.ts_data_reader: TSDataReader = TSDataReader(data_provider_name, ts_type_name)

    def history_data_in_backtest(self, codes: List[str], end_time: Timestamp,
                                 count=100) -> DataFrame:
        return self.ts_data_reader.history_data(codes, end=end_time, count=count)

    def history_data(self, codes: List[str], count=100):
        return self.ts_data_reader.recent_history_data(codes, count)


class CurrentPriceLoader(metaclass=ABCMeta):
    @abstractmethod
    def current_price(self, codes, end_time):
        pass


class BarCurrentPriceLoader(CurrentPriceLoader):

    def current_price(self, codes, end_time):
        if end_time in (self.calendar.opens - Timedelta(minutes=1)):
            # 获取下一个bar的开盘价
            df: DataFrame = self.bar_loader.history_data_in_backtest(codes, end_time + self.freq, count=1)
            return df.iloc[0]['open']
        else:
            df: DataFrame = self.bar_loader.history_data_in_backtest(codes, end_time, count=1)
            return df.iloc[0]['close']

    def __init__(self, bar_loader: HistoryDataLoader, calendar: TradingCalendar, freq: Timedelta):
        self.bar_loader = bar_loader
        self.calendar = calendar
        self.freq = freq


class IBRealtimeCurrentPriceLoader(CurrentPriceLoader):

    def current_price(self, codes, end_time):
        raise NotImplemented("")


class TSData(object):
    def __init__(self, visible_time: Timestamp, code: str, data: Dict):
        self.visible_time = visible_time
        self.code = code
        self.data = data


class StreamDataCallback(metaclass=ABCMeta):
    @abstractmethod
    def on_data(self, data: TSData):
        pass


class TSDataReader(object):
    """
    这个类负责读取时序数据，包括历史数据，截止到当前时间的历史数据以及实时数据流
    """

    def __init__(self, data_provider_name: str, ts_type_name: str):
        self.data_provider_name = data_provider_name
        self.ts_type_name = ts_type_name

    def history_data(self, codes: List[str], start: Timestamp = None,
                     end: Timestamp = Timestamp.now(tz='Asia/Shanghai'),
                     count=100) -> DataFrame:
        """
        获取时序数据，优先按照开始和结束时间查询。 其次按照结束时间和数量进行查询
        这里的所有时间都是针对visible_time
        :param count:
        :param codes:
        :param start:
        :param end:
        :return: DataFrame, 索引为visible_time + code
        """
        if len(codes) <= 0:
            raise RuntimeError("code不能为空")
        if start:
            start = start.tz_convert("Asia/Shanghai")
        end = end.tz_convert("Asia/Shanghai")
        pattern = '%Y-%m-%d %H:%M:%S'
        if start and end:
            params = {
                "providerName": self.data_provider_name,
                "tsTypeName": self.ts_type_name,
                "codes": ",".join(codes),
                "startTime": datetime.strftime(start, pattern),
                "endTime": datetime.strftime(end, pattern)
            }
        else:
            params = {
                "providerName": self.data_provider_name,
                "tsTypeName": self.ts_type_name,
                "codes": ",".join(codes),
                "endTime": datetime.strftime(end, pattern),
                "count": count
            }
        url = "http://localhost:32900/queryData"
        resp = requests.get(url, params)
        if resp.status_code == 200:
            result = resp.json()
            if not result['success']:
                raise RuntimeError("下载数据出错，错误信息：" + result['errorMsg'])
            else:
                df_data = []
                for single_data in result['data']:
                    m_data = {'visible_time': Timestamp(single_data['visiableTime']), 'code': single_data['code']}
                    m_data.update(single_data['values'])
                    df_data.append(m_data)
                df = DataFrame(df_data)
                df.set_index(['visible_time', 'code'], inplace=True)
                return df

    def recent_history_data(self, codes, count=100):
        pass

    def listen(self, subscriber: StreamDataCallback):
        """
        当有实时数据流时，会调用subscriber的on_stream_data的方法
        :param subscriber:
        :return:
        """
        pass


class DataPortal(object):
    """
    在回测或者实盘中，策略要获取实时数据或者历史数据都从这里获取。 实时数据跟历史数据的区别已经被数据中心封装了，数据中心会接收实时数据流，
    并将其保存下来
    """

    def __init__(self, is_real_time: bool = False, backtest_current_price_loader: CurrentPriceLoader = None,
                 realtime_current_price_loader: CurrentPriceLoader = None):
        self.current_dt = None
        self.is_real_time = is_real_time
        self.backtest_current_price_loader = backtest_current_price_loader
        self.realtime_current_price_loader = realtime_current_price_loader

    def set_current_dt(self, dt: Timestamp):
        if dt.second != 0:
            raise RuntimeError("当前时间只能是分钟的开始")
        self.current_dt = dt

    def history(self, provider_name: str, ts_type_name: str, codes: List[str], window: int):
        ts_data_loader = HistoryDataLoader(data_provider_name=provider_name, ts_type_name=ts_type_name)
        if self.is_real_time:
            return ts_data_loader.history_data(codes, count=window)
        else:
            if not self.current_dt:
                raise RuntimeError("当前时间没有设置")
            return ts_data_loader.history_data_in_backtest(codes, end_time=self.current_dt, count=window)

    def current_price(self, codes: List[str]):
        if self.is_real_time:
            return self.realtime_current_price_loader.current_price(codes, Timestamp.now())
        else:
            if not self.current_dt:
                raise RuntimeError("当前时间没有设置")
            return self.backtest_current_price_loader.current_price(codes, self.current_dt)
