import os
import requests
import json
import sys

# Your GitHub Repository (username/repo)
REPO = "Algo-Ankit/AlphaSwarm"

# Securely read the token from the environment variable
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

ISSUES = [
    {
        "title": "Bug: AutoGen LLM model name configuration is invalid",
        "body": "**Location:** `app/services/strategy_builder.py`\n\n**Description:** The AutoGen `llm_config` is hardcoded to use `claude-sonnet-4-6`. This is not a valid model identifier for the Anthropic API (e.g., it should be `claude-3-5-sonnet-20241022`). As a result, the `StrategyWriterAgent` fails to communicate with the Anthropic API on every attempt, preventing agent creation."
    },
    {
        "title": "Bug: Strategy compiler silently swallows generation errors",
        "body": "**Location:** `app/services/strategy_compiler.py`\n\n**Description:** The `compile_strategy_prompt` function catches all exceptions (including the invalid model name error mentioned above) and silently returns a `_PLACEHOLDER` string instead of propagating the error to the user. This makes the frontend think the strategy was deployed successfully (returning a 201), but it actually deploys a broken/empty strategy."
    },
    {
        "title": "Bug: Market hours check blocks agent runs & causes terminal errors",
        "body": "**Location:** `app/domain/risk.py` and `app/worker/tasks.py`\n\n**Description:** The strategy runner creates a `MarketState` based on the current real-time session status. If the agent is run outside of regular NASDAQ trading hours, `verify_order_intent` immediately rejects all generated signals. This causes the terminal to show a bunch of 'REJECTED' errors and no orders are executed."
    },
    {
        "title": "Bug: Sandbox environment lacks mathematical & datetime utilities",
        "body": "**Location:** `app/services/strategy_sandbox.py`\n\n**Description:** The `RestrictedPython` sandbox injects a very limited set of globals. While `max` and `int` are available via `safe_builtins`, common modules like `math` and `datetime` are entirely blocked. If the AutoGen LLM generates a strategy that attempts to use `math.sqrt` or `datetime.timedelta`, the strategy will crash during compilation or at runtime."
    }
]

def create_issues():
    if not GITHUB_TOKEN:
        print("❌ Error: GITHUB_TOKEN environment variable is not set.")
        print("Please set it in your terminal using: $env:GITHUB_TOKEN=\"your_token_here\"")
        sys.exit(1)

    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }

    for issue in ISSUES:
        url = f"https://api.github.com/repos/{REPO}/issues"
        response = requests.post(url, headers=headers, data=json.dumps(issue))
        if response.status_code == 201:
            print(f"✅ Successfully created issue: {issue['title']}")
            print(f"   URL: {response.json().get('html_url')}")
        else:
            print(f"❌ Failed to create issue: {issue['title']}")
            print(f"   Error: {response.status_code} - {response.text}")

if __name__ == "__main__":
    create_issues()
