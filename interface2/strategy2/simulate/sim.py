from configparser import ConfigParser

from trading_calendars import get_calendar

from se.domain2.engine.engine import Engine, Scope
from se.infras.ib import IBAccount
from se.strategies.strategy import TestStrategy3
from se import config

engine = Engine()
scope = Scope(["GSX_STK_USD_SMART"], trading_calendar=get_calendar("NYSE"))
strategy = TestStrategy3(scope)

# 实盘测试
# acc = IBAccount("ib_test1", 10000)
# #
# # # acc_repo: AccountRepo = BeanContainer.getBean(AccountRepo)
# # # acc = acc_repo.find_one("ib_test1")
# # #
# acc.with_order_callback(strategy).with_client(config.get('ib', 'host'), config.getint('ib', 'port'),
#                                               config.getint("ib", "client_id"))
# #
# def mocked_event_generator(event_definition: EventDefinition):
#     if isinstance(event_definition.time_rule, MarketOpen):
#         return [Event(event_definition, visible_time=Timestamp("2021-01-21 22:30:00", tz='Asia/Shanghai'), data={}),
#                 Event(event_definition, visible_time=Timestamp("2021-01-22 22:30:00", tz='Asia/Shanghai'), data={}),
#                 ]
#
#     elif isinstance(event_definition.time_rule, MarketClose):
#         if event_definition.time_rule.minute_offset == 0:
#             t = Timestamp("2021-01-22 05:00:00", tz='Asia/Shanghai')
#             return [Event(event_definition, visible_time=t, data={})]
#         elif event_definition.time_rule.minute_offset == 30:
#             t = Timestamp("2021-01-22 05:30:00", tz='Asia/Shanghai')
#             return [Event(event_definition, visible_time=t, data={})]
# #
# #
# mocked_current_prices = {
#     Timestamp("2021-01-21 22:30:00", tz='Asia/Shanghai'): {"GSX_STK_USD_SMART": 108},
#     Timestamp("2021-01-22 05:00:00", tz='Asia/Shanghai'): {"GSX_STK_USD_SMART": 109},
#     Timestamp("2021-01-22 05:30:00", tz='Asia/Shanghai'): {"GSX_STK_USD_SMART": 109},
#     Timestamp("2021-01-22 22:30:00", tz='Asia/Shanghai'): {"GSX_STK_USD_SMART": 108},
#
# engine.run(strategy, acc, is_realtime_test=True, mocked_events_generator=mocked_event_generator,
#            mocked_current_prices=mocked_current_prices)
# 实盘

acc = IBAccount("ib_real2", 10000)
acc.with_order_callback(strategy).with_client(config.get('ib', 'host'), config.getint('ib', 'port'),
                                              config.getint('ib', 'client_id'))
engine.run(strategy, acc)
