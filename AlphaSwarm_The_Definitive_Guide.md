# AlphaSwarm: The Definitive Engineering Guide & Interview Handbook

Welcome to the AlphaSwarm study guide. This document is written like a textbook specifically to prepare you for technical interviews, architectural deep-dives, and seed-funding pitches. It breaks down every single technology used, *why* it was chosen, how the system actually works under the hood, the brutal bugs we squashed, and whether our setup is truly "production-grade."

---

## Chapter 1: The Vision & High-Level Architecture

### What is AlphaSwarm?
AlphaSwarm is a production-grade, multi-tenant algorithmic trading SaaS. It bridges the gap between retail traders (who want to describe a strategy in plain English) and quantitative developers (who want to write Python code). 

The core business thesis is **BYOB (Bring Your Own Broker)**. AlphaSwarm never holds or custodies user funds. Users connect their Alpaca, Upstox, or Zerodha accounts via API keys. Because we don't hold money, we avoid the massive regulatory and legal overhead of acquiring money transmission licenses, making this a highly fundable startup MVP.

### The Stack at a Glance
- **Frontend:** Next.js 14 (React), TailwindCSS, TradingView Lightweight Charts.
- **Backend:** FastAPI (Python 3.11).
- **Database:** PostgreSQL 16 (Relational data) accessed via `asyncpg`.
- **Workers & Message Queue:** Celery and Redis.
- **AI Orchestration:** Microsoft AutoGen and Claude Sonnet 4.6.
- **Infrastructure:** Docker & Docker Compose, deployed on Hetzner with Nginx.

---

## Chapter 2: The Infrastructure (Docker & "No Download" Magic)

You asked: *"How are we using Postgres, Celery, and Redis without downloading them? Is Docker Compose production-grade?"*

### How Docker Works
You didn't have to go to the PostgreSQL website, download an `.exe`, run an installer, and configure ports. Instead, you ran `docker compose up -d`. 
Docker is a containerization engine. It packages an application and all its dependencies (OS libraries, binaries, configurations) into a standardized unit called a **Container**. 
When you ran Docker Compose, Docker reached out to Docker Hub (the app store for containers), downloaded the official, pre-configured Linux environments for PostgreSQL and Redis, and spun them up in isolated bubbles on your machine. 

### Are we using Kafka?
**No.** You mentioned Kafka in your prompt, but AlphaSwarm actually uses **Redis** as its message broker. Kafka is an event-streaming platform designed for massive, durable logs (like tracking every click of 10 million users on Netflix). For our use case—distributing background trading tasks to workers—Kafka would be massive overkill and introduce unnecessary latency and maintenance. Redis is lightning fast, runs entirely in RAM, and handles our Celery task queueing and WebSocket Pub/Sub perfectly. This is a great point to bring up in an interview to show you understand *when* not to use trendy tech!

### Is Docker Compose Production Grade?
**Yes and No.** 
- **Local Docker Compose** (what you run on your Desktop) is ephemeral. If you delete the container, the data might disappear unless explicitly mapped.
- **Production Docker Compose** (the `docker-compose.prod.yml` file) *is* production-grade for a seed-stage startup. It mounts **Persistent Volumes** (so if the DB container restarts, the hard drive data remains safe). It scales via commands like `--scale worker=2`, and delegates load-balancing and SSL to Nginx. While massive enterprises use Kubernetes (K8s), a bootstrapped startup running on Hetzner servers is perfectly fine—and actually smarter—using Docker Compose to keep DevOps overhead near zero.

---

## Chapter 3: The Asynchronous Brain (FastAPI, Celery, & Redis)

### FastAPI vs. Django/Flask
Traditional Python frameworks like Django use WSGI (Web Server Gateway Interface), which is synchronous. If a request takes 2 seconds to execute, that thread is blocked. AlphaSwarm uses **FastAPI**, an ASGI (Asynchronous Server) framework. It uses Python's `async/await` syntax. While the API is waiting for the database or an external broker to respond, the event loop pauses that request and serves hundreds of other users simultaneously.

### What is Celery and Why Do We Use It?
Imagine a user clicks "Deploy Strategy." Generating the AI code, backtesting 5 years of historical data, and evaluating market indicators takes maybe 30 seconds to 2 minutes. If we did this inside the FastAPI route, the user's browser would just spin and eventually timeout, and our web server would be blocked.

**Celery** is an asynchronous task queue. 
1. FastAPI receives the user's request, immediately says *"Got it, I'm working on it,"* and returns an HTTP 200 Success.
2. FastAPI sends a message to **Redis** (the message broker) saying: *"Hey, someone needs to run Strategy X."*
3. A **Celery Worker** (a completely separate Python process running in the background) is constantly watching Redis. It grabs the task, spends 2 minutes crunching the data and executing the trades, and saves the result to the database.

### The WebSocket Fan-Out
To make the UI feel alive, we need to push updates to the browser without the user hitting refresh. When a Celery worker finishes a trade, it publishes a message to Redis Pub/Sub. Our FastAPI WebSocket endpoint listens to Redis and instantly "fans out" (broadcasts) that message to the user's browser, updating the live P&L dashboard instantly.

---

## Chapter 4: Data Storage & Integrity (Postgres)

### Why asyncpg over an ORM?
Most projects use an ORM (Object-Relational Mapper) like SQLAlchemy to write Python instead of SQL. However, financial data access patterns require fetching hundreds of thousands of historical OHLCV (Open, High, Low, Close, Volume) bars in milliseconds. ORMs add massive overhead. We chose `asyncpg`, which is raw, asynchronous SQL. It is 3-5x faster than SQLAlchemy async. 

### Alembic for Migrations
When you change the database schema (e.g., adding a new column to the `orders` table), you don't do it manually in the DB. You use **Alembic**, a migration tool. It writes a version-controlled Python script of the change. This ensures that when you deploy to a fresh server, the database structure is built identically every single time.

---

## Chapter 5: AI & The Restricted Sandbox

### AutoGen over LangChain
You specifically banned LangChain in favor of Microsoft AutoGen. Why? LangChain is notorious for shipping breaking API changes that destroy production apps. AutoGen provides a highly stable, multi-agent conversational framework (where an AI developer agent and an AI critic agent can talk to each other to refine a trading strategy before finalizing it). 

### The Sandbox & The Security Bugs We Fixed
Users (and the AI) submit Python code to run trading strategies. If we just ran `exec(user_code)`, a malicious user could write `os.system("rm -rf /")` or steal our database passwords. 
We use **RestrictedPython** to sandbox the code. However, in Phase 7, we found brutal vulnerabilities:
- **String Subclassing RCE:** Attackers could bypass our dunder `_` checks by creating a custom string class where `startswith('_')` returned False, giving them access to CPython internals. We fixed this by enforcing strict `type(name) is str` checks.
- **The iter() DoS Attack:** We had an AST (Abstract Syntax Tree) parser that banned `while` loops to prevent users from freezing the server with infinite loops. But attackers could bypass this using the two-argument form of Python's `iter()` function (e.g., `for _ in iter(int, 1): pass`). We fixed this by stripping `iter` from the allowed builtins.

---

## Chapter 6: The Risk Engine & Concurrency (The Hardest Problem)

The absolute most critical file in AlphaSwarm is `app/domain/risk.py`. It houses `verify_order_intent()`, a function that runs 6 non-negotiable checks (Market open? Symbol allowed? Order size limits? Daily capital limits? Total position limits? Paper-trading gate?) before *any* broker API is touched.

### The Brutal TOCTOU Bug (Interview Goldmine)
**TOCTOU** stands for *Time-Of-Check to Time-Of-Use*. 
In Phase 6, we had a bug: A user has a strict limit of "Maximum 1 Open Position."
1. Signal A and Signal B arrive at the exact same millisecond. 
2. Worker A queries the DB: *"Open positions? 0."*
3. Worker B queries the DB: *"Open positions? 0."*
4. Worker A says: *"0 is less than 1. Allowed!"* and executes the trade.
5. Worker B says: *"0 is less than 1. Allowed!"* and executes the trade.
Result: The user now has 2 open positions, blowing past their risk limits.

**How we fixed it:** 
We used PostgreSQL's `pg_advisory_xact_lock`. This is a database-level lock. When Worker A wants to trade Strategy X, it acquires a lock using a 64-bit MD5 hash of the Strategy ID. Worker B arrives a millisecond later, sees the lock, and is forced to wait in line. We then moved the database queries *inside* the transaction block. So Worker A finishes trading, commits the transaction (releasing the lock). Only then is Worker B allowed to proceed and query the database. Worker B now correctly sees *"Open positions? 1,"* and safely rejects the trade!

---

## Chapter 7: The Frontend Terminal

We built the frontend using **Next.js 14 App Router**. 
For the charting, we rejected Chart.js and Recharts because they cannot handle drawing 10,000 candlesticks without lagging the browser. We integrated **TradingView Lightweight Charts v4**, which uses HTML5 Canvas to render massive datasets in milliseconds, providing a true Bloomberg-terminal feel.

**The React Race Condition Fix:**
When the dashboard loaded, we fired an HTTP request to get the user's historical P&L. At the exact same time, we opened a WebSocket connection to listen for live trades. If a live trade happened *while* the HTTP request was still loading, the WebSocket would update the UI. But a second later, the HTTP request would finish loading, overwrite the state, and erase the live trade! We fixed this state-clobbering bug by ensuring the UI properly merges incoming WS data with the initial HTTP payload.

---

## Chapter 8: Final Polish & DevOps Metrics

### Financial Math Edge Cases
Writing a backtester is mathematically complex. During our Phase 7 audit, we caught major flaws:
1. **CAGR Overflow:** Compound Annual Growth Rate uses the formula `(Final / Initial) ^ (1 / Years)`. If a user backtested a strategy over just 2 minutes of data, `Years` became a fraction so small (e.g., 0.000001) that `(1 / Years)` resulted in an exponent of 1,000,000. Python threw an `OverflowError` and crashed. We added strict limits and exception handling.
2. **Sortino Ratio:** We fixed the math to correctly calculate the Root-Mean-Square (RMS) of downside deviations relative to zero, rather than just the standard deviation of negative numbers.
3. **Calmar Ratio:** If a strategy had a perfect run with absolutely 0 drawdowns, our math divided by zero or defaulted to 0.0 (making it look like a terrible strategy). We introduced a `999.0` sentinel value to reward mathematically perfect strategies.

### Cryptography (Algorithmic DoS)
We securely store user broker API keys in the database using Fernet Envelope Encryption. Initially, we used `PBKDF2HMAC` with 390,000 iterations to derive the encryption keys. This is designed for human passwords to prevent brute-forcing. But since our master secret is a 32-byte high-entropy string, hashing it 390,000 times per trade was exhausting the server's CPU (Algorithmic DoS). We refactored the crypto engine to use **HKDF**, dropping CPU overhead to near zero while maintaining military-grade security.

---

## Summary for Interviews

If an interviewer asks you about AlphaSwarm, tell them:

> *"I built a multi-tenant algorithmic trading SaaS that converts natural language to executable Python strategies. It features a proprietary RestrictedPython sandbox to prevent RCE attacks, a zero-bypass risk engine protected against TOCTOU race conditions via 64-bit PostgreSQL advisory locks, and an asynchronous execution pipeline powered by FastAPI, Celery, and Redis. The frontend is a Next.js terminal leveraging TradingView canvas charts and real-time WebSocket Pub/Sub fan-outs. It's fully containerized via Docker Compose and deployed on raw Linux infrastructure to maximize margins."* 

You have built an absolute powerhouse. Use this document to study the *"whys"* behind the architecture, and you will ace any engineering interview.
