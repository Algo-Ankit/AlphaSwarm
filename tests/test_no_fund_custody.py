"""
Guard test — the platform NEVER handles funds.

AlphaSwarm is a SaaS for testing/verifying strategies. Execution is always
dry_run/paper or routed through the user's OWN broker credentials; there is no
custody, wallet, deposit, or withdrawal logic anywhere. This test fails the
build if such code is reintroduced, so the product invariant can't silently rot.

The only sanctioned money field is portfolio_snapshots.cash_balance — a display
snapshot inserted NULL — so "cash_balance" / "balance" are NOT flagged.

Runnable with pytest OR directly:  python tests/test_no_fund_custody.py
"""
import re
from pathlib import Path

_APP_DIR = Path(__file__).resolve().parent.parent / "app"

# Terms that imply the platform itself moves or holds user money. Each is a
# whole-word match (case-insensitive). Add a term here, not a one-off exception.
_FORBIDDEN = [
    r"deposit",
    r"withdraw\w*",
    r"custody",
    r"custodian",
    r"wallet",
    r"escrow",
    r"payout",
    r"cash[_-]?out",
    r"top[_-]?up",
    r"transfer[_ ]+funds",
]
_PATTERN = re.compile(r"\b(" + "|".join(_FORBIDDEN) + r")\b", re.IGNORECASE)


def _scan() -> list[str]:
    violations: list[str] = []
    for path in _APP_DIR.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), 1):
            if _PATTERN.search(line):
                violations.append(f"{path.relative_to(_APP_DIR.parent)}:{lineno}: {line.strip()}")
    return violations


def test_no_fund_custody_code():
    violations = _scan()
    assert not violations, (
        "Fund-custody code detected — the platform must never handle funds.\n"
        + "\n".join(violations)
    )


if __name__ == "__main__":
    found = _scan()
    if found:
        print("FAIL  test_no_fund_custody_code")
        for v in found:
            print("  " + v)
        print(f"\n0/1 passed")
        raise SystemExit(1)
    print("PASS  test_no_fund_custody_code")
    print("\n1/1 passed")
    raise SystemExit(0)
