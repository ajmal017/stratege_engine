from trading_calendars import get_calendar

from se import config, AccountRepo, BeanContainer
from se.domain2.engine.engine import Engine, Scope
from se.infras.ib import IBAccount
from strategies.strategy import TestStrategy3

engine = Engine()
scope = Scope(["GSX_STK_USD_SMART"], trading_calendar=get_calendar("NYSE"))
strategy = TestStrategy3(scope)

account_name = "ib_real2"
repo: AccountRepo = BeanContainer.getBean(AccountRepo)
acc = repo.find_one(account_name)
if not acc:
    acc = IBAccount(account_name, 10000)
acc.start_save_thread()
acc.start_sync_order_executions_thread()

acc.with_order_callback(strategy).with_client(config.get('ib_account', 'host'), config.getint('ib_account', 'port'),
                                              config.getint('ib_account', 'client_id'))
engine.run(strategy, acc)