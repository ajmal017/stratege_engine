from __future__ import annotations

import time
import uuid
from abc import ABCMeta, abstractmethod

from se2.domain.common import *
from se2.domain.time_series import CurrentPrice, Bar, TimeSeries


class OrderStatusCallback(metaclass=ABCMeta):
    @abstractmethod
    def order_status_change(self, order):
        pass


class OrderDirection(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    FAILED = "FAILED"
    PARTIAL_FILLED = "PARTIAL_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"


class ExecutionFrom(object):
    """
    表示一个执行详情来自于哪里，可以是回测引擎、盈透或者德美利等
    """

    def __init__(self):
        pass


class Execution(object):

    def __init__(self, id: str, version: int, quantity: float, price: float, time: Timestamp, fee: float,
                 real_order_id: str):
        self.id = id
        self.version = version
        self.quantity = quantity
        self.price = price
        self.time = time
        self.fee = fee
        self.real_order_id = real_order_id


class Order(metaclass=ABCMeta):

    def __init__(self, code, direction, quantity, place_time, reason, ideal_price):
        self.code = code
        self.direction = direction
        self.quantity = quantity
        self.place_time = place_time
        self.status = OrderStatus.CREATED
        self.executions: Mapping[str, Execution] = {}
        self.account_name = None
        self.reason = reason
        self.remark = None
        self.real_order_id = None
        self.ideal_price = ideal_price
        # 成交数据
        self.filled_start_time = None
        self.filled_end_time = None
        self.filled_quantity = 0
        self.filled_avg_price = 0
        self.fee = 0
        # 成交数据
        self.order_status_callback: OrderStatusCallback = None
        self.failed_reason = None
        self.cancel_reason = None
        # 是否允许延长时段交易
        self.extended_time = False

    def with_order_status_callback(self, order_status_callback: OrderStatusCallback):
        self.order_status_callback = order_status_callback
        return self

    def submitted(self):
        if self.status in [OrderStatus.CANCELED, OrderStatus.FAILED, OrderStatus.SUBMITTED]:
            raise RuntimeError("非法的订单状态")
        elif self.status in [OrderStatus.FILLED, OrderStatus.PARTIAL_FILLED]:
            # do nothing
            pass
        elif self.status == OrderStatus.CREATED:
            self.status = OrderStatus.SUBMITTED
            if self.order_status_callback:
                self.order_status_callback.order_status_change(self)

    def failed(self, reason):
        if self.status == OrderStatus.CREATED:
            self.failed_reason = reason
            self.status = OrderStatus.FAILED
            if self.order_status_callback:
                self.order_status_callback.order_status_change(self)
            self.save()
        else:
            raise RuntimeError("非法的订单状态")

    def cancelled(self, reason):
        if self.status in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED]:
            self.cancel_reason = reason
            self.status = OrderStatus.CANCELED
            if self.order_status_callback:
                self.order_status_callback.order_status_change(self)
            self.save()
        else:
            raise RuntimeError("非法的订单状态")

    @abstractmethod
    def bar_match(self, bar: Bar) -> Execution:
        pass

    @abstractmethod
    def current_price_match(self, current_price: CurrentPrice) -> Execution:
        pass

    def order_filled(self, execution: Execution):
        if not execution.real_order_id.startswith("bt") and self.real_order_id != execution.real_order_id:
            raise RuntimeError('非法的执行详情:{}'.format(execution.__dict__))
        if execution.id in self.executions:
            old_exec = self.executions[execution.id]
            if execution.version > old_exec.version:
                self.executions[execution.id] = execution
        else:
            self.executions[execution.id] = execution

        self._re_compute_filled_data()

    def replace_order_filled(self, new_executions: List[Execution]):
        self.executions = {}
        for execution in new_executions:
            self.executions[execution.id] = execution

        self._re_compute_filled_data()

    def _re_compute_filled_data(self):
        total_filled_quantity = 0
        total_net_value = 0
        filled_start_time = None
        filled_end_time = None
        total_fee = 0

        for execution in self.executions.values():
            total_fee += execution.fee
            total_net_value = execution.price * execution.quantity
            total_filled_quantity += execution.quantity
            if not filled_start_time or execution.time < filled_start_time:
                filled_start_time = execution.time
            if not filled_end_time or execution.time > filled_end_time:
                filled_end_time = execution.time

        self.filled_quantity = total_filled_quantity
        self.filled_avg_price = total_net_value / total_filled_quantity
        self.fee = total_fee
        self.filled_start_time = filled_start_time
        self.filled_end_time = filled_end_time

        if self.filled_quantity > self.quantity:
            raise RuntimeError("非法的成交数量")
        elif self.filled_quantity == self.quantity:
            if self.status in [OrderStatus.CREATED, OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED]:
                self.status = OrderStatus.FILLED
                if self.order_status_callback:
                    self.order_status_callback.order_status_change(self)
                self.save()
            else:
                raise RuntimeError("非法的订单状态")
        elif self.filled_quantity > 0:
            if self.status in [OrderStatus.CREATED, OrderStatus.SUBMITTED]:
                self.status = OrderStatus.PARTIAL_FILLED
                if self.order_status_callback:
                    self.order_status_callback.order_status_change(self)
            else:
                raise RuntimeError("非法的订单状态")

    def cash_cost(self):
        """
        该笔订单消耗的现金，如果是负的，表示这笔订单增加了现金
        :return:
        """
        cost = self.fee
        if self.direction == OrderDirection.BUY:

            cost += self.filled_quantity * self.filled_avg_price
        else:
            cost = cost - self.filled_quantity * self.filled_avg_price
        return cost

    def with_status_callback(self, order_status_callback):
        self.order_status_callback = order_status_callback
        return self

    def with_account(self, account_name):
        self.account_name = account_name
        return self

    def set_real_order_id(self, real_order_id):
        self.real_order_id = real_order_id

    def save(self):
        order_repo: OrderRepo = BeanContainer.getBean(OrderRepo)
        order_repo.save(self)


class PriceChange(object):
    def __init__(self, time: Timestamp, pre_price: float, after_price: float, current_price: CurrentPrice):
        self.time = time
        self.pre_price = pre_price
        self.after_price = after_price
        self.current_price = current_price


class LimitOrder(Order):

    def __init__(self, code, direction, quantity, place_time, reason, ideal_price, limit_price: float,
                 bargin_algo: BarginAlgo = None):
        super().__init__(code, direction, quantity, place_time, reason, ideal_price)
        self.limit_price = limit_price
        self.bargin_algo: BarginAlgo = bargin_algo
        if self.limit_price and bargin_algo:
            raise RuntimeError("不能同时制定limit_price和bargin_algo")
        if not self.limit_price and not bargin_algo:
            raise RuntimeError("limit price和bargin_algo必须指定一个")
        if self.bargin_algo:
            self.bargin_algo.bind_order(self)
            # self.limit_price = self.bargin_algo.initial_limit_price()

    # def add_price_change(self, price_change: PriceChange):
    #     self.price_change_history.append(price_change)

    def bar_match(self, bar: Bar) -> Execution:
        if self.direction == OrderDirection.BUY:
            if bar.low <= self.limit_price:
                return Execution(str(uuid.uuid1()), 0, self.quantity, self.limit_price,
                                 bar.visible_time, 0, 'bt')
        else:
            if bar.high >= self.limit_price:
                return Execution(str(uuid.uuid1()), 0, self.quantity, self.limit_price,
                                 bar.visible_time, 0, 'bt')
        return None

    def current_price_match(self, current_price: CurrentPrice) -> Execution:
        if self.direction == OrderDirection.BUY:
            if current_price.price <= self.limit_price:
                return Execution(str(uuid.uuid1()), 0, self.quantity, current_price.price,
                                 current_price.visible_time, 0, 'bt')
        else:
            if current_price.price >= self.limit_price:
                return Execution(str(uuid.uuid1()), 0, self.quantity, current_price.price,
                                 current_price.visible_time, 0, 'bt')
        return None


class MKTOrder(Order):
    def bar_match(self, bar: Bar) -> Execution:
        # 以开盘价成交
        return Execution(str(uuid.uuid1()), 0, self.quantity, bar.open, bar.visible_time,
                         0, "bt")

    def current_price_match(self, current_price: CurrentPrice) -> Execution:
        return Execution(str(uuid.uuid1()), 0, self.quantity, current_price.price, current_price.visible_time,
                         0, "bt")

    def __init__(self, code, direction, quantity, place_time, reason, ideal_price):
        super().__init__(code, direction, quantity, place_time, reason, ideal_price)


class StopOrder(Order):

    def bar_match(self, bar: Bar) -> Execution:
        if self.direction == OrderDirection.BUY:
            if bar.high >= self.stop_price:
                return Execution(str(uuid.uuid1()), 0, self.quantity, self.stop_price, bar.visible_time,
                                 0, "bt")
        else:
            if bar.low <= self.stop_price:
                return Execution(str(uuid.uuid1()), 0, self.quantity, self.stop_price, bar.visible_time,
                                 0, "bt")
        return None

    def current_price_match(self, current_price: CurrentPrice) -> Execution:
        pass

    def __init__(self, code, direction, quantity, place_time, reason, ideal_price, stop_price: float):
        super().__init__(code, direction, quantity, place_time, reason, ideal_price)
        self.stop_price = stop_price


class BarginAlgo(metaclass=ABCMeta):
    """
    议价算法，该模型不仅仅持有议价算法，且持有一次议价过程中的价格变化历史，用于后续的分析
    """

    @abstractmethod
    def name(self):
        pass

    @abstractmethod
    def bargin(self, cp: CurrentPrice) -> PriceChange:
        pass

    def initial_limit_price(self) -> float:
        cp = self.current_price_ts.current_price([self.order.code])[self.order.code]
        price: float = self.do_get_initial_limit_price(cp)
        self.price_change_history.append(PriceChange(cp.visible_time, -1, price, cp))
        self.latest_price = price
        return price

    @abstractmethod
    def do_get_initial_limit_price(self, cp: CurrentPrice) -> float:
        pass

    def __init__(self, account: AbstractAccount, current_price_ts: TimeSeries, freq: int):
        self.current_price_ts = current_price_ts
        self.current_price_history: List[CurrentPrice] = []
        self.price_change_history: List[PriceChange] = []
        self.account = account
        self.order: LimitOrder = None
        self.freq = freq
        self.latest_price = None

    def bind_order(self, order: LimitOrder):
        self.order = order

    def start_bargin(self):
        def do_start():
            while True:
                if self.order.status in [OrderStatus.SUBMITTED, OrderStatus.PARTIAL_FILLED]:
                    try:
                        cp:CurrentPrice = self.current_price_ts.current_price([self.order.code])[self.order.code]
                        self.current_price_history.append(cp)
                        price_change: PriceChange = self.bargin(cp)
                        if price_change:
                            # 由于订单执行详情是在异步的线程中更新的，所以这个时候订单可能已经成交的
                            # 在任何跟订单状态有关系的操作之前，都进行这个判断是合理的
                            if self.order.status != OrderStatus.FILLED:
                                self.account.update_order_price(self.order, price_change.after_price)
                                self.price_change_history.append(price_change)
                                self.latest_price = price_change.after_price

                        time.sleep(self.freq)
                    except:
                        import traceback
                        logging.error("议价异常{}".format(traceback.format_exc()))
                else:
                    logging.info("议价结束")
                    break

        threading.Thread(target=do_start, name='bargin thread').start()


class DefaultBarginAlgo(BarginAlgo):

    def do_get_initial_limit_price(self, cp: CurrentPrice) -> float:
        if self.order.direction == OrderDirection.BUY:
            return round(cp.bid_price + self.delta, 2)
        elif self.order.direction == OrderDirection.SELL:
            return round(cp.ask_price - self.delta, 2)
        else:
            raise RuntimeError("wrong direction")

    def __init__(self, account: AbstractAccount, current_price_ts: TimeSeries, freq: int, delta=0.01):
        super().__init__(account, current_price_ts, freq)
        self.delta = delta

    def name(self):
        return 'default'

    def bargin(self, cp: CurrentPrice) -> PriceChange:
        if self.order.direction == OrderDirection.BUY:
            # 小数的相减是有误差的，比如32.92-0.01=32.910000000000004
            if round(cp.bid_price + self.delta, 2) > self.latest_price:
                new_price = round(cp.bid_price + self.delta, 2)
                return PriceChange(cp.visible_time, self.latest_price, new_price, cp)
        elif self.order.direction == OrderDirection.SELL:
            if round(cp.ask_price-self.delta, 2) < self.latest_price:
                new_price = round(cp.ask_price - self.delta, 2)
                return PriceChange(cp.visible_time, self.latest_price, new_price, cp)
        return None


class AbstractAccount(metaclass=ABCMeta):

    def __init__(self, name: str, initial_cash: float):
        self.name = name
        self.cash = initial_cash
        self.initial_cash = initial_cash
        self.positions = {}
        self.history_net_value: Mapping[Timestamp, float] = {}
        self.order_status_callback = None
        # 记录该账户自初始化后新下的订单
        self.new_placed_orders = []
        self.real_order_id_to_order: Dict[str, Order] = {}

    def get_order_by_real_order_id(self, real_order_id: str):
        try:
            return self.real_order_id_to_order[real_order_id]
        except KeyError:
            return None

    @abstractmethod
    def match(self, data):
        """
        撮合订单，只有回测账户需要实现
        :param data:
        :return:
        """
        pass

    def get_new_placed_orders(self) -> List[Order]:
        """
        获取当前账户
        :return:
        """
        return self.new_placed_orders

    def with_order_callback(self, order_callback: OrderStatusCallback):
        self.order_status_callback = order_callback
        return self

    @do_log(target_name='下单', escape_params=[EscapeParam(index=0, key='self')])
    @alarm(target='下单', escape_params=[EscapeParam(index=0, key='self')])
    def place_order(self, order: Order):
        try:
            order.with_status_callback(self.order_status_callback).with_account(self.name)
            self.do_place_order(order)
            order.submitted()
            self.new_placed_orders.append(order)
            self.real_order_id_to_order[order.real_order_id] = order
            if isinstance(order, LimitOrder) and order.bargin_algo:
                order.bargin_algo.start_bargin()

        except Exception as e:
            # import traceback
            # logging.error("{}".format(traceback.format_exc()))
            order.failed(str(e.args))
            raise e

    @abstractmethod
    def do_place_order(self, order: Order):
        """
        由子类实现，约定为如果成功，则方法正常结束，如果失败则抛出异常
        :param order:
        :return:
        """
        pass

    @do_log(target_name='取消订单', escape_params=[EscapeParam(index=0, key='self')])
    @alarm(target='取消订单', escape_params=[EscapeParam(index=0, key='self')])
    def cancel_order(self, order: Order, reason: str):
        try:
            self.do_cancel_order(order)
            order.cancelled(reason)
        except Exception as e:
            raise e

    @abstractmethod
    def do_cancel_order(self, order: Order):
        """
        由子类实现，约定为如果成功，则方法正常结束，如果失败则抛出异常
        :param order:
        :return:
        """
        pass

    @do_log(target_name='更新订单', escape_params=[EscapeParam(index=0, key='self')])
    @alarm(target='更新订单', escape_params=[EscapeParam(index=0, key='self')])
    def update_order_price(self, order, new_price: float):
        if not isinstance(order, LimitOrder):
            raise RuntimeError("只适用于限价单")
        try:
            self.do_update_order_price(order, new_price)
        except Exception as e:
            raise e

    @abstractmethod
    def do_update_order_price(self, order, new_price):
        """
        由子类实现，约定为如果成功，则方法正常结束，如果失败则抛出异常
        :param new_price:
        :param order:
        :return:
        """
        pass

    def order_filled(self, order: Order, executions: List[Execution], replaced=False):
        pre_cash_cost = order.cash_cost()
        pre_position = order.filled_quantity if order.direction == OrderDirection.BUY else -order.filled_quantity

        if not replaced:
            for execution in executions:
                order.order_filled(execution)
        else:
            order.replace_order_filled(executions)

        after_cash_cost = order.cash_cost()
        after_position = order.filled_quantity if order.direction == OrderDirection.BUY else -order.filled_quantity

        self.cash -= after_cash_cost - pre_cash_cost
        self.update_position(order.code, after_position - pre_position)
        self.save()

    @abstractmethod
    def valid_scope(self, codes: List[str]):
        """
        校验code是否有效
        :param codes:
        :return:
        """
        pass

    def save(self):
        account_repo: AccountRepo = BeanContainer.getBean(AccountRepo)
        account_repo.save(self)

    def calc_net_value(self, current_prices: Mapping[str, float], current_time: Timestamp):
        net_value = 0
        net_value += self.cash
        for code in self.positions.keys():
            net_value += current_prices[code] * self.positions[code]
        self.history_net_value[current_time] = net_value

    def update_position(self, code, position_change):
        if code in self.positions:
            self.positions[code] = self.positions[code] + position_change
        else:
            self.positions[code] = position_change

        if self.positions[code] == 0:
            self.positions.pop(code)

    def net_value(self, current_prices: Dict[str, float]):
        """
        计算该账户的资产净值
        :param param:
        :return:
        """
        net_value = 0
        net_value += self.cash
        for code in self.positions.keys():
            if code not in current_prices:
                raise RuntimeError("缺少价格数据")
            net_value += self.positions[code] * current_prices[code]
        return net_value


class AccountRepo(metaclass=ABCMeta):
    @abstractmethod
    def save(self, account: AbstractAccount):
        pass

    @abstractmethod
    def find_one(self, account_name):
        pass


class OrderRepo(metaclass=ABCMeta):

    @abstractmethod
    def find_by_account_name(self, account_name):
        pass

    def save(self, order: Order):
        pass
