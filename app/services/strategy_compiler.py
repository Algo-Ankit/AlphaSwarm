from app.domain.models import StrategyCreateRequest


def compile_strategy_prompt(request: StrategyCreateRequest) -> str:
    symbols = ", ".join(symbol.upper() for symbol in request.symbols)
    return (
        f"Monitor {symbols} on {request.timeframe}. "
        "Convert the user's natural-language strategy into deterministic signals. "
        "Before each simulated order, call centralized risk verification."
    )
