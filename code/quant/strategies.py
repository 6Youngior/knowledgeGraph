"""Small portfolio policy; orders, cash, costs and execution stay in Qlib."""
from qlib.contrib.strategy.signal_strategy import WeightStrategyBase


class EqualWeightUniverse(WeightStrategyBase):
    """Rebalance the same eligible universe on the same sparse decision days."""

    def generate_target_weight_position(self, score, current, trade_start_time, trade_end_time):
        if getattr(score, "ndim", 1) == 2:
            score = score.iloc[:, 0]
        symbols = score.dropna().index
        return {symbol: 1.0 / len(symbols) for symbol in symbols}
