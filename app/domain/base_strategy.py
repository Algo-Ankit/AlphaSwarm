"""
BaseStrategy — the contract every strategy (AI-generated or developer-written) must fulfill.
This interface is used for both live execution and backtesting via BacktestRunner.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, TYPE_CHECKING
import pandas as pd

if TYPE_CHECKING:
    from app.domain.models import OrderIntent, StrategyRiskConfig


class ReadOnlyIloc:
    def __init__(self, data: list[dict]):
        self._data = data
        
    def __getitem__(self, idx: int) -> dict:
        # Return a fresh dict so mutation by strategy code doesn't corrupt state
        return dict(self._data[idx])
        
    def __len__(self) -> int:
        return len(self._data)

class ReadOnlyDataFrame:
    """
    Safe wrapper around pd.DataFrame that completely seals the sandbox boundary.
    No pandas or numpy objects are kept or returned. Data is converted to pure
    Python native types upon initialization to prevent sandbox escapes.
    """
    def __init__(self, df: pd.DataFrame):
        records = []
        if not df.empty:
            # Convert pandas index to native python datetime objects
            timestamps = df.index.to_pydatetime() if hasattr(df.index, 'to_pydatetime') else df.index
            
            # Using tolist() on Series converts numpy scalars to pure Python float/int
            opens = df['open'].tolist()
            highs = df['high'].tolist()
            lows = df['low'].tolist()
            closes = df['close'].tolist()
            volumes = df['volume'].tolist()
            
            for i in range(len(df)):
                records.append({
                    "timestamp": timestamps[i],
                    "open": float(opens[i]),
                    "high": float(highs[i]),
                    "low": float(lows[i]),
                    "close": float(closes[i]),
                    "volume": int(volumes[i]),
                })
        self._data = records
        self._iloc = ReadOnlyIloc(self._data)

    @property
    def iloc(self) -> ReadOnlyIloc:
        return self._iloc
        
    def __len__(self) -> int:
        return len(self._data)


@dataclass
class StrategyContext:
    """
    Passed to BaseStrategy on every bar. Contains everything a strategy needs
    to make a trading decision — no external API calls needed inside on_bar().
    """
    strategy_id: str     # UUID string — required for OrderIntent construction inside on_bar()
    symbol: str
    exchange: str        # NASDAQ | NYSE | NSE | BSE | CRYPTO
    timeframe: str       # 1m | 5m | 15m | 1h | 4h | 1d
    bars: ReadOnlyDataFrame   # Safe wrapper to prevent RCE via pandas
                         # Sorted ascending. Latest bar is bars.iloc[-1].
    indicators: dict     # Computed by indicators.py. Keys use pandas-ta naming convention:
                         # e.g. {"RSI_14": 42.3, "MACD_12_26_9": 0.12, "BBU_20_2.0": 185.4}
    position: Optional[float]  # Current held quantity. None or 0 = flat. Positive = long.
    avg_cost: Optional[float]  # Average cost basis of current position. None if flat.
    risk: "StrategyRiskConfig"

    # Multi-symbol support: peer symbols populated if strategy.symbols has > 1 entry
    peers: dict[str, "StrategyContext"] = field(default_factory=dict)


class BaseStrategy(ABC):
    """
    All strategies subclass this. The on_bar() method is the only required implementation.

    Example (no-code generated):
        class RSIMomentum(BaseStrategy):
            def on_bar(self):
                rsi = self.indicators.get("RSI_14")
                if rsi is None:
                    return None
                if rsi < 30 and self.position is None:
                    return OrderIntent(
                        strategy_id=self.ctx.risk.strategy_id,
                        symbol=self.ctx.symbol,
                        side=OrderSide.buy,
                        quantity=1,
                        order_type=OrderType.market,
                        estimated_price=float(self.bars.iloc[-1]["close"]),
                    )
                if rsi > 70 and self.position and self.position > 0:
                    return OrderIntent(...)
                return None
    """

    def __init__(self, context: StrategyContext):
        self.ctx = context

    @abstractmethod
    def on_bar(self) -> Optional["OrderIntent"]:
        """
        Called once per bar close during live execution and backtesting.
        Return an OrderIntent to place an order. Return None to hold.
        Must not make any external API calls, network requests, or file I/O.
        Must not have side effects beyond returning an OrderIntent.
        Must complete in < 100ms.
        """
        ...

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def bars(self) -> ReadOnlyDataFrame:
        """Full OHLCV history up to and including the current bar."""
        return self.ctx.bars

    @property
    def indicators(self) -> dict:
        """Computed indicator values for the current bar."""
        return self.ctx.indicators

    @property
    def position(self) -> Optional[float]:
        """Current held quantity. None or 0.0 = flat."""
        return self.ctx.position

    @property
    def avg_cost(self) -> Optional[float]:
        """Average entry price of current position. None if flat."""
        return self.ctx.avg_cost

    @property
    def close(self) -> float:
        """Current bar's closing price."""
        return float(self.ctx.bars.iloc[-1]["close"])

    @property
    def is_flat(self) -> bool:
        """True if no open position."""
        return self.ctx.position is None or self.ctx.position == 0.0

    @property
    def is_long(self) -> bool:
        return self.ctx.position is not None and self.ctx.position > 0

    @property
    def is_short(self) -> bool:
        return self.ctx.position is not None and self.ctx.position < 0
