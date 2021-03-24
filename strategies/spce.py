import logging

from se.domain2.account.account import AbstractAccount, MKTOrder, OrderDirection, LimitOrder
from se.domain2.engine.engine import AbstractStrategy, Engine, EventDefinition, EventDefinitionType, MarketOpen, \
    MarketClose, Event, DataPortal
from se.domain2.time_series.time_series import HistoryDataQueryCommand


class SPCEStrategy(AbstractStrategy):
    """
    该策略会在收盘的时候，检查今天收盘是否大于昨日收盘，如果大于，则以市价买入，并持有到下一个开盘卖出
    会在开盘的时候判断，如果昨天日内上涨，则在开盘的时候进行卖空，并且在收盘的时候平仓
    交易标的： SPCE
    回测结果：
        最大回撤:-0.2359915731707678
        胜率:0.6387434554973822
        年化夏普:4.571345500751706
        平均盈利:0.049463270533594325, 平均亏损:-0.037356983399675504
    """

    def do_initialize(self, engine: Engine, data_portal: DataPortal):
        if engine.is_backtest:
            market_close = EventDefinition(ed_type=EventDefinitionType.TIME, time_rule=MarketClose())
            market_open = EventDefinition(ed_type=EventDefinitionType.TIME, time_rule=MarketOpen())
        else:
            market_open = EventDefinition(ed_type=EventDefinitionType.TIME, time_rule=MarketOpen(second_offset=5))
            market_close = EventDefinition(ed_type=EventDefinitionType.TIME, time_rule=MarketClose(second_offset=-60))
            market_close_set_price = EventDefinition(ed_type=EventDefinitionType.TIME,
                                                     time_rule=MarketClose())
            engine.register_event(market_close_set_price, self.set_close_price)

        engine.register_event(market_open, self.market_open)
        engine.register_event(market_close, self.market_close)

        # 初始化昨日开盘价和收盘价
        self.last_open = None
        self.last_close = None
        if not engine.is_backtest:
            command = HistoryDataQueryCommand(None, None, self.scope.codes, window=1)
            command.with_calendar(trading_calendar=self.scope.trading_calendar)
            df = data_portal.history_data("ibAdjustedDailyBar", command)
            if len(df) >= 1:
                self.last_open = df.iloc[-1]['open']
                self.last_close = df.iloc[-1]['close']
                logging.info("初始化数据成功，昨日开盘价:{}, 昨日收盘价:{}, bar的开始时间:{}"
                             .format(self.last_open, self.last_close, df.iloc[-1]['start_time']))
            else:
                raise RuntimeError("没有获取到昨日开盘价和收盘价")
            # self.last_open = 35.17
            # self.last_close = 33.77

        if len(self.scope.codes) != 1:
            raise RuntimeError("wrong codes")
        self.code = self.scope.codes[0]

    def market_open(self, event: Event, account: AbstractAccount, data_portal: DataPortal):
        dest_position = 0
        current_position = 0
        net_value = None

        # 等待直到获取到最新的股票价格
        current_price = None
        try:
            current_price = data_portal.current_price([self.code], event.visible_time)[self.code].price
        except:
            logging.error("没有获取到当天的开盘价,code:{}".format(self.code))
        if current_price:
            net_value = account.net_value({self.code: current_price})

        current_bid_ask = None
        try:
            current_bid_ask = data_portal.current_bid_ask([self.code])[self.code]
        except:
            logging.error("没有获取到最新的买卖价,code:{}".format(self.code))

        if len(account.positions) > 0:
            current_position = account.positions[self.code]

        if current_price and self.last_open and self.last_close and self.last_close > self.last_open:
            dest_position = - int(net_value / current_price)

        change = dest_position - current_position
        if change != 0:
            direction = OrderDirection.BUY if change > 0 else OrderDirection.SELL
            reason = "时间:{}, 当前持仓:{}, 总市值：{}, 目标持仓:{}, 昨日开盘价:{}, 昨日收盘价:{}, 今日开盘价：{}, 最新买卖价:{}, strategy:{}" \
                .format(event.visible_time, current_position, net_value, dest_position, self.last_open, self.last_close,
                        current_price, current_bid_ask.__dict__ if current_bid_ask else None, SPCEStrategy.__doc__)
            if current_bid_ask:
                delta = 0.01
                limit_price = (current_bid_ask.bid_price + delta) if direction == OrderDirection.BUY else (
                        current_bid_ask.ask_price - delta)
                order = LimitOrder(self.code, direction, abs(change), event.visible_time, limit_price)
                order.with_reason(reason)
                account.place_order(order)
                # self.ensure_order_filled(account, data_portal, order, 30, 3)
                self.ensure_order_filled_v2(account, data_portal, order, duration=60, delta=delta)
            else:
                order = MKTOrder(self.code, direction, abs(change), event.visible_time)
                order.with_reason(reason)
                account.place_order(order)
        else:
            msg = "不需要下单, 时间:{}, 当前持仓:{}, 总市值：{}, 目标持仓:{}, 昨日开盘价:{}, 昨日收盘价:{}, 今日开盘价：{}". \
                format(event.visible_time, current_position, net_value, dest_position, self.last_open, self.last_close,
                       current_price)
            logging.info(msg)

        self.last_open = current_price

    def set_close_price(self, event: Event, account: AbstractAccount, data_portal: DataPortal):
        current_price = data_portal.current_price([self.code], event.visible_time)[self.code].price
        self.last_close = current_price
        logging.info("设置收盘价为:{}".format(current_price))

    def market_close(self, event: Event, account: AbstractAccount, data_portal: DataPortal):
        dest_position = 0
        current_position = 0
        net_value = None

        # 等待直到获取到最新的股票价格
        current_price = None
        try:
            current_price = data_portal.current_price([self.code], event.visible_time)[self.code].price
        except:
            logging.error("没有获取到当天的开盘价,code:{}".format(self.code))
        if current_price:
            net_value = account.net_value({self.code: current_price})

        current_bid_ask = None
        try:
            current_bid_ask = data_portal.current_bid_ask([self.code])[self.code]
        except:
            logging.error("没有获取到最新的买卖价,code:{}".format(self.code))

        if current_price and self.last_close and current_price > self.last_close:
            dest_position = int(net_value / current_price)

        if len(account.positions) > 0:
            current_position = account.positions[self.code]

        change = dest_position - current_position
        if change != 0:
            direction = OrderDirection.BUY if change > 0 else OrderDirection.SELL
            reason = "时间:{}, 当前持仓:{}, 总市值：{}, 目标持仓:{}, 昨日收盘价:{}, 今日收盘价:{}, " \
                     "买卖价:{}, strategy:{}".format(event.visible_time,
                                                  current_position,
                                                  net_value, dest_position,
                                                  self.last_close,
                                                  current_price,
                                                  current_bid_ask.__dict__ if current_bid_ask else None,
                                                  SPCEStrategy.__doc__)
            if current_bid_ask:
                delta = 0.01
                limit_price = (current_bid_ask.bid_price + delta) if direction == OrderDirection.BUY else (
                        current_bid_ask.ask_price - delta)
                order = LimitOrder(self.code, direction, abs(change), event.visible_time, limit_price)
                order.with_reason(reason)
                account.place_order(order)
                # self.ensure_order_filled(account, data_portal, order, 40, 1)
                self.ensure_order_filled_v2(account, data_portal, order, 40, delta)
            else:
                order = MKTOrder(self.code, direction, abs(change), event.visible_time)
                order.with_reason(reason)
                account.place_order(order)
        else:
            logging.info("不需要下单, 时间:{}, 当前持仓:{}, 总市值：{}, 目标持仓:{}, 今日开盘价:{}, 今日收盘价:{}".
                         format(event.visible_time,
                                current_position,
                                net_value, dest_position,
                                self.last_open,
                                current_price))

        self.last_close = current_price

    def do_order_status_change(self, order, account):
        pass
