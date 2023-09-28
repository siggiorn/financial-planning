from collections import defaultdict
from typing import Protocol
import math
import dataclasses
from datetime import date as Date
from dateutil import relativedelta

_DAYS_IN_YEAR = (4 * 365 + 1) / 4.0
_MONTHS_IN_YEAR = 12.0
_DAYS_IN_MONTH = _DAYS_IN_YEAR / _MONTHS_IN_YEAR


class AnnualFixedRate:
    def __init__(self, rate: float):
        assert (
            rate >= 0 and rate <= 1.0
        ), "Rate must be in [0, 1] (it is a ratio, not a %)"
        self.rate = rate

    def multiplier(self, start_date: Date, date: Date) -> float:
        rate = self.rate if date >= start_date else 0.0
        months = _months_between(start_date, date)
        return math.pow(1.0 + rate / _MONTHS_IN_YEAR, months)


class Source(Protocol):
    def monthly_amount(self, date: Date) -> float:
        ...


class DateRangeSource(Source):
    def __init__(
        self,
        initial_monthly: float,
        *,
        start_date: Date,
        end_date: Date | None = None,
        growth: AnnualFixedRate | None = None,
    ):
        self._initial_monthly = initial_monthly
        self._start_date = start_date
        self._end_date = end_date
        self._growth = growth or AnnualFixedRate(rate=0.0)

    def monthly_amount(self, date: Date) -> float:
        if date < self._start_date or (
            self._end_date is not None and date > self._end_date
        ):
            return 0.0
        return self._initial_monthly * self._growth.multiplier(self._start_date, date)



class OneTimeSource(Source):
    def __init__(self, amount: float, date: Date):
        assert date.day == 1
        self._amount = amount
        self._date = date

    def monthly_amount(self, date: Date) -> float:
        if date == self._date:
            return self._amount
        return 0.0


class FinancialInstrument:
    def __init__(self, value: float, start_date: Date, rate: AnnualFixedRate) -> None:
        self._start_value = value
        self._value = value
        self._start_date = start_date
        self._value_date = start_date
        self._rate = rate

    def reset(self) -> None:
        self._value = self._start_value
        self._value_date = self._start_date

    def value(self, date: Date) -> float:
        if date < self._start_date:
            return 0.0
        if date < self._value_date:
            raise ValueError(
                "Can't ask for value for a date prior than previous query date."
            )
        if date == self._value_date:
            return self._value
        return self._value * self._rate.multiplier(self._value_date, date)

    def _transact(self, amount: float, date: Date) -> None:
        self._value = self.value(date) + amount
        self._value_date = date


class Asset(FinancialInstrument):
    def __init__(self, value: float, start_date: Date, rate: AnnualFixedRate) -> None:
        super().__init__(value, start_date, rate)
        assert value >= 0.0

    def transact(self, amount: float, date: Date) -> float:
        """Returns remainder if transaction is a withdrawal and there isn't enough value."""
        remainder = 0.0
        if amount < 0.0:
            value = self.value(date)
            can_withdraw = max(-value, amount)
            remainder = amount - can_withdraw
            amount = can_withdraw

        self._transact(amount, date)
        return remainder


class Liability(FinancialInstrument):
    def __init__(
        self,
        value: float,
        start_date: Date,
        duration_months: int,
        rate: AnnualFixedRate,
    ) -> None:
        super().__init__(value, start_date, rate)
        assert value < 0.0
        self._end_date = start_date + relativedelta.relativedelta(
            months=duration_months
        )
        self._minimum_monthly = _minimum_payment(
            principal=value,
            interval_rate=self._rate.rate / _MONTHS_IN_YEAR,
            remaining_intervals=duration_months,
        )

    def minimum_monthly(self, date: Date) -> float:
        return min(self._minimum_monthly, -self.value(date))

    def make_payment(self, payment: float, date: Date) -> float:
        """Returns the remainder in case the value is less than the contribution."""
        assert payment >= 0.0
        if date < self._start_date:
            return payment
        value = self.value(date)
        actual_payment = min(-value, payment)
        self._transact(actual_payment, date)
        return payment - actual_payment


class CashHandler(Protocol):
    def handle_cash(self, cash: float, date: Date) -> float:
        """Accepts available cash as input, returns cash that is left over."""


class BasicCashHandler(CashHandler):
    def __init__(self, asset: Asset) -> None:
        self._asset = asset

    def handle_cash(self, cash: float, date: Date) -> float:
        remainder = self._asset.transact(cash, date)
        return remainder


class MaxValueCashHandler(CashHandler):
    def __init__(self, asset: Asset, max_value: float) -> None:
        self._asset = asset
        self._max_value = max_value

    def handle_cash(self, cash: float, date: Date) -> float:
        remainder = 0.0
        if cash > 0.0:
            value = self._asset.value(date)
            can_contribute = max(0, self._max_value - value)
            contribution = min(can_contribute, cash)
            remainder = cash - contribution
            cash = contribution
        return self._asset.transact(cash, date) + remainder


class SequentialCashHandler(CashHandler):
    def __init__(self, handlers: list[CashHandler]) -> None:
        self._handlers = handlers

    def handle_cash(self, cash: float, date: Date) -> float:
        remaining = cash
        for handler in self._handlers:
            remaining = handler.handle_cash(remaining, date)
        return remaining


def _list_dict() -> dict[str, list]:
    return defaultdict(list)


@dataclasses.dataclass
class Output:
    incomes: dict[str, list[float]] = dataclasses.field(default_factory=_list_dict)
    incomes_total: list[float] = dataclasses.field(default_factory=list)
    expenses: dict[str, list[float]] = dataclasses.field(default_factory=_list_dict)
    expenses_total: list[float] = dataclasses.field(default_factory=list)
    liabilities: dict[str, list[float]] = dataclasses.field(default_factory=_list_dict)
    liabilities_total: list[float] = dataclasses.field(default_factory=list)
    assets: dict[str, list[float]] = dataclasses.field(default_factory=_list_dict)
    assets_total: list[float] = dataclasses.field(default_factory=list)
    cashflow: list[float] = dataclasses.field(default_factory=list)
    cash_balance: list[float] = dataclasses.field(default_factory=list)
    net_worth: list[float] = dataclasses.field(default_factory=list)


def monthly_date_range(
    start_date: Date,
    end_date: Date,
) -> list[Date]:
    assert start_date.day == 1
    assert end_date.day == 1
    date = start_date
    output = []
    while date <= end_date:
        output.append(date)
        date += relativedelta.relativedelta(months=1)

    return output


def process(
    dates: list[Date],
    incomes: dict[str, Source] | None = None,
    expenses: dict[str, Source] | None = None,
    liabilities: dict[str, Liability] | None = None,
    assets: dict[str, Asset] | None = None,
    cash_handler: CashHandler | None = None,
) -> Output:
    incomes = incomes or {}
    expenses = expenses or {}
    liabilities = liabilities or {}
    assets = assets or {}
    output = Output()
    cash_balance = 0.0

    for instr in (*liabilities.values(), *assets.values()):
        instr.reset()

    for date in dates:
        cash = 0.0

        incomes_total = 0.0
        for name, income in incomes.items():
            amount = income.monthly_amount(date)
            assert amount >= 0
            output.incomes[name].append(amount)
            cash += amount
            incomes_total += amount

        output.incomes_total.append(incomes_total)

        expenses_total = 0.0
        for name, expense in expenses.items():
            amount = expense.monthly_amount(date)
            assert amount <= 0
            output.expenses[name].append(amount)
            cash += amount
            expenses_total += amount

        # Make all loan minimum payments and subtract them from cashflow.
        for name, loan in liabilities.items():
            target_payment = loan.minimum_monthly(date)
            remainder = loan.make_payment(target_payment, date)
            payment = target_payment - remainder
            assert payment >= 0
            output.expenses[name].append(-payment)
            cash -= payment
            expenses_total -= payment

        output.expenses_total.append(expenses_total)

        output.cashflow.append(cash)
        remaining_cash = cash

        # If the cash balance is negative then the cash is first applied to that.
        if remaining_cash > 0.0 and cash_balance < 0.0:
            remainder = max(0.0, cash + cash_balance)
            cash_balance += remaining_cash - remainder
            remaining_cash = remainder

        if cash_handler is not None:
            remaining_cash = cash_handler.handle_cash(remaining_cash, date)

        cash_balance += remaining_cash
        output.cash_balance.append(cash_balance)

        liabilities_total = 0.0
        for name, loan in liabilities.items():
            value = loan.value(date)
            assert value <= 0
            output.liabilities[name].append(value)
            liabilities_total += value

        output.liabilities_total.append(liabilities_total)

        assets_total = 0.0
        for name, asset in assets.items():
            value = asset.value(date)
            assert value >= 0
            output.assets[name].append(value)
            assets_total += value

        output.assets_total.append(assets_total)
        output.net_worth.append(assets_total + liabilities_total + cash_balance)

    return output


def _months_between(first: Date, second: Date) -> float:
    delta = relativedelta.relativedelta(second, first)
    return delta.years * 12.0 + delta.months + delta.days / _DAYS_IN_MONTH


def _minimum_payment(principal: float, interval_rate: float, remaining_intervals: int) -> float:
    assert principal <= 0
    if interval_rate == 0.0:
        return -principal / remaining_intervals

    return (
        -principal
        * interval_rate
        * math.pow(1 + interval_rate, remaining_intervals)
        / (math.pow(1 + interval_rate, remaining_intervals) - 1)
    )
