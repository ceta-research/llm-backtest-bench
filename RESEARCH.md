# LLM Backtest Bench: Existing Work Research

## Summary of Landscape

Every major benchmark (FINSABER, StockBench, AI-Trader) is **US-only, equities-only, daily-only**. Nobody has tested LLM signal generation on LSE, NSE, FOREX, or commodities. This is our primary gap.

---

## 1. FINSABER (Edinburgh, KDD 2026)

**Paper**: [arXiv:2505.07078](https://arxiv.org/abs/2505.07078)
**Code**: [github.com/waylonli/FINSABER](https://github.com/waylonli/FINSABER)
**License**: Apache 2.0

### What It Does
- 20-year backtest (2004-2024) of LLM timing strategies on S&P 500 stocks
- Two LLM agents: FinMem (memory-based) and FinAgent (multi-stage prompting with 5 LLM calls/day)
- Compares against traditional baselines (SMA, Bollinger, ARIMA, XGBoost) and RL (PPO, SAC, TD3)

### Signal Generation
- **FinMem**: Hierarchical memory (short=news, mid=10-Q, long=10-K, reflection=prior reasoning). Retrieves top-3 similar memories via embeddings. Single LLM call returns `{"investment_decision": "buy"|"sell"|"hold"}`
- **FinAgent**: 5 sequential LLM calls per day (market intelligence, past intelligence, low-level reflection, high-level reflection, decision). Uses FAISS for diverse memory retrieval. Also feeds 4 technical strategy signals (MACD, KDJ/RSI, Stochastic Bollinger, Mean Reversion)

### Data
- **US only**: S&P 500 constituents
- Sources: Alpaca News API, SEC 10-K/10-Q, FMP for FinAgent
- Pickle format: `{date: {"price": {ticker: float}, "news": {ticker: [str]}, "filing_k": ..., "filing_q": ...}}`
- Stock selectors: random N per year, momentum top-N, low-volatility top-N, hardcoded 5

### Backtest Engine
- **Traditional**: Backtrader (bt.Cerebro)
- **LLM**: Custom Python engine
- Commission: $0.0049/share, min $0.99, max 1% of txn
- Single-stock per window, $100k cash, long-only, no slippage
- Rolling windows: 1-2 year windows, 1 year step

### Metrics
Total return, CAGR, annual volatility, Sharpe, Sortino, max drawdown, API cost tracking

### Key Finding
**LLM advantages deteriorate at scale.** Overly conservative in bull markets, overly aggressive in bear markets. Previously reported advantages disappear with broader stock selection and longer evaluation periods.

### Limitations / Our Gaps
- US-only (no LSE, NSE, FOREX)
- Only tested gpt-4o-mini (no Claude, no Gemini, no open-source)
- Single-stock backtesting (no portfolio construction)
- All-or-nothing positions (no sizing)
- No anonymized data approach
- No structured financial ratios fed to LLM (only raw SEC filings)
- Training phase has look-ahead bias (shows future price deltas)
- No slippage modeling
- Debug artifacts left in code (pdb.set_trace)

---

## 2. StockBench (Tsinghua, Oct 2025)

**Paper**: [arXiv:2510.02209](https://arxiv.org/abs/2510.02209)
**Code**: [github.com/ChenYXxxx/stockbench](https://github.com/ChenYXxxx/stockbench)
**License**: Apache 2.0

### What It Does
- 82-day evaluation (Mar-Jun 2025) on 20 DJIA mega-caps
- Dual-agent architecture: Fundamental Filter Agent + Decision Agent
- Contamination-free: evaluation period after all models' training cutoffs

### Signal Generation
- **Agent 1 (Filter)**: Decides which stocks need expensive fundamental analysis (triggers: unusual vol, earnings, concentration risk)
- **Agent 2 (Decision)**: Receives market data + fundamentals + news + position state + history. Outputs structured JSON: action (increase/decrease/close/hold) + target_cash_amount + reasons + confidence
- System prompt: "Professional portfolio strategist with 15+ years high-frequency trading expertise"
- Same prompt for all models (no model-specific optimization)

### Data
- **US only**: Top 20 DJIA stocks
- Sources: Polygon.io (prices, fundamentals, news), Finnhub (news, profiles)
- 7-day price history window, 5 news items/day
- Multi-layer caching (Parquet per ticker)

### Models Tested (ranked by Sortino)
| Rank | Model | Return | MDD | Sortino |
|------|-------|--------|-----|---------|
| 1 | Kimi-K2 | +1.9% | -11.8% | 0.042 |
| 2 | Qwen3-235B | +2.4% | -11.2% | 0.030 |
| 7 | Claude-4-Sonnet | +2.2% | -14.2% | 0.025 |
| 9 | GPT-5 | +0.3% | -13.1% | 0.013 |
| 12 | **Passive Baseline** | **+0.4%** | **-15.2%** | **0.016** |

### Backtest Engine
- Commission: 1 bp (0.01%), Slippage: 2 bp (0.02%)
- Next-day open execution, 100% fill, no partial fills
- $100k initial capital, max 20 positions
- TWAP order slicing

### Key Finding
**Most LLMs barely beat buy-and-hold.** Financial knowledge benchmarks don't predict trading ability. Return spread is tiny (+2.5% best vs +0.4% baseline over 82 days).

### Limitations / Our Gaps
- US-only, mega-cap only (20 stocks)
- Only 82 trading days (single market regime)
- 7-day price window (extremely short)
- 5 news items/day (massive info loss)
- No technical indicators computed for agent
- No short selling, no leverage
- Same prompt for all models
- Only 3 runs averaged (statistical significance questionable)

---

## 3. AI-Trader (HKU, Dec 2025)

**Paper**: [arXiv:2512.10971](https://arxiv.org/abs/2512.10971)
**Code**: [github.com/HKUDS/AI-Trader](https://github.com/HKUDS/AI-Trader)

### What It Does
- ReAct-style autonomous agent with MCP tools (buy, sell, get_price, search, math)
- Multi-market: US (NASDAQ-100), China A-shares (SSE-50), Crypto (BITWISE-10)
- Both daily and hourly frequency

### Signal Generation
- Agent receives system prompt with portfolio state + prices + stock universe
- ReAct loop: up to 30 iterations of tool-calling per day
- LLM decides everything: what data to look up, when to trade, how much
- No pre-programmed indicators or rules

### Data
- Alpha Vantage (US/crypto), Tushare + efinance (China)
- Anti-look-ahead: masks current-day high/low/close/volume, news filtered by date
- Price renamed: open = "buy price", close = "sell price"

### Models Tested
DeepSeek-v3.1, MiniMax-M2, Claude-3.7-Sonnet, GPT-5, Qwen3-Max, Gemini-2.5-Flash

### Key Finding
"General intelligence does not automatically translate to effective trading capability."

### Limitations / Our Gaps
- No transaction costs or slippage (all returns inflated)
- News NOT cached (non-reproducible backtests)
- Sequential JSONL scanning for prices (slow)
- No portfolio-level risk management
- File-based everything (no database)
- Only one non-US market (China A-shares, not LSE/NSE/FOREX)
- Trivial math tool (only add and multiply)

---

## 4. TradingAgents (UCLA/MIT, 30k stars)

**Code**: [github.com/TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)

### What It Does
- Multi-agent debate system on LangGraph
- 10+ agents: 4 analysts, bull/bear researchers, research manager, trader, 3 risk debators, risk judge
- Signal: BUY/SELL/HOLD for single stock on single date

### Architecture
```
Analysts (Market, Social, News, Fundamentals)
  -> Bull/Bear Debate -> Research Manager
    -> Trader -> Risk Debate (Aggressive/Conservative/Neutral) -> Risk Judge
```

### Why NOT To Adopt
- **No backtesting included** (paper's eval code not open-sourced)
- 12-15 LLM calls per signal (extremely expensive)
- yfinance fundamentals have look-ahead bias (returns latest, not as-of date)
- LangChain/LangGraph dependency (heavyweight)
- Output is just text parsed into BUY/SELL/HOLD (no position sizing)
- US only, single-stock only

### What To Steal
- Bull/bear debate as a **prompt technique** (not as a framework): ask one prompt for bull case, bear case, and synthesis
- Data vendor abstraction pattern

---

## 5. Anonymization Research

### Key Papers

| Paper | Method | Data | Finding |
|-------|--------|------|---------|
| **Perlin et al. 2025** (Finance Research Letters) | Strip tickers, use relative dates, standardized Compustat format | 1,522 US companies, 20 years, Gemini Flash | Gemini does NOT beat naive portfolio. Performance degrades at longer horizons |
| **Kim et al. 2024** (Chicago Booth) | Anonymized Compustat statements, t/t-1/t-2 dates | 15,401 US firms, 1968-2021, GPT-4 | GPT-4 achieves 60.35% earnings direction accuracy (vs 52.71% humans). Higher Sharpe |
| **Engelberg et al. 2025** (Entity Neutering) | Iterative LLM masking + paraphrasing until judge LLM can't identify | 250k US news articles, GPT-4 | Post-neutering: identification drops to random chance for ~90% of articles. Sentiment preserved 95%+ |
| **Wu, Yang & Ying 2025** | Compared spaCy (CNN), spaCy (RoBERTa), GPT-4o-mini anonymization | 7,382 earnings calls + 52,716 headlines, US | GPT-4o-mini best (19.32% recognition). Numbers are biggest leak AND biggest signal. 67% signal loss |
| **Didisheim et al. 2025** (AI's Predictable Memory) | Direct recall prompts | US stocks | Smaller models have negligible memorization bias. Use smaller models to minimize look-ahead |
| **Cao et al. 2025** (When LLMs Go Abroad, Harvard) | US + China stock predictions | ChatGPT vs DeepSeek | ChatGPT more optimistic about Chinese firms than DeepSeek. Training data asymmetry drives bias |

### What Works for Anonymization
1. **Standardized financial statements** (Compustat-style, strip labels, relative dates) -- easy, high signal preservation
2. **Price/return series** (pure numeric, no labels needed) -- easy, no identity leakage
3. **Entity neutering** (iterative LLM masking + paraphrasing) -- effective for text, but 67% signal loss
4. **Ratio-only presentation** (P/E, ROE, D/E as numbers without context) -- untested in literature, our opportunity

### What Breaks Anonymization
1. Financial numbers (simultaneously most identifying AND most signal-bearing)
2. Product uniqueness (describable products narrow identification)
3. CEO speaking patterns on earnings calls
4. Temporal markers (specific dates, quarterly patterns)
5. Industry jargon

### The Critical Gap: Non-US Markets
**ZERO published work** tests anonymized financial data + LLMs on:
- London Stock Exchange (LSE)
- National Stock Exchange of India (NSE/BSE)
- Tokyo Stock Exchange
- European exchanges
- Forex markets
- Commodities

Cao et al. found systematic LLM bias for non-US markets driven by training data gaps. This means anonymization might actually **help more** for non-US stocks (removing company identity also removes training-data-driven bias).

---

## 6. What We Can Do Differently

### Market Coverage (nobody has done this)
- **LSE** (less LLM training data than US, different regulatory environment)
- **NSE/BSE** (even less training data, different market microstructure)
- **FOREX** (no company identity at all, pure macro/numerical data)
- **Cross-market comparison** (same methodology, different markets)

### Methodology Improvements
1. **Structured numerical data only** -- feed ratios/returns as tables, no text, no tickers. Avoids the anonymization signal-loss problem entirely
2. **Multi-model comparison with Claude CLI** -- test Claude (Opus, Sonnet, Haiku) via `claude -p`, plus GPT, Gemini, DeepSeek via their APIs. No one has compared Claude models specifically
3. **Portfolio-level signals** -- "given these 20 anonymized stocks, allocate weights" instead of single-stock buy/sell/hold
4. **Position sizing via confidence** -- LLM outputs confidence score, size accordingly
5. **Regime-aware prompting** -- two-stage: classify market regime first, then trade within regime rules
6. **Our data advantage** -- CR API gives us FMP warehouse with TTM metrics, historical financials, 72 exchanges. Nobody else has this as a data source for LLM benchmarking
7. **Cost-performance Pareto** -- which model gives best Sharpe per dollar of API spend?
8. **Full reproducibility** -- pin model IDs, temperature=0, log every prompt/response, share via CR API

### What Framework To Use
**Don't adopt any existing framework.** Build lean, reuse components:
- Shared utilities: `metrics.py`, `ts_client.py`, `costs.py`, `cli_utils.py`
- Conceptual pattern: 4-step methodology (scan, signal, execute, evaluate)
- New: model runner (claude CLI + API wrappers), anonymization pipeline, prompt templates

### Why Not Existing Frameworks
| Framework | Why Not |
|-----------|---------|
| FINSABER | Heavy deps, only tested gpt-4o-mini, US-only data baked in, debug artifacts |
| StockBench | Polygon/Finnhub dependency, 20-stock universe, 82-day eval, heavyweight |
| TradingAgents | No backtesting, 12+ LLM calls/signal, LangChain lock-in, US-only |
| AI-Trader | No transaction costs, non-reproducible, file-based, LangChain dependency |

---

## Sources

### Papers
- [FINSABER - arXiv:2505.07078](https://arxiv.org/abs/2505.07078)
- [StockBench - arXiv:2510.02209](https://arxiv.org/abs/2510.02209)
- [AI-Trader - arXiv:2512.10971](https://arxiv.org/abs/2512.10971)
- [TradingAgents - arXiv:2412.20138](https://arxiv.org/abs/2412.20138)
- [Kim et al. - Financial Statement Analysis with LLMs - arXiv:2407.17866](https://arxiv.org/html/2407.17866v1)
- [Perlin et al. - Can AI beat a naive portfolio? - SSRN:4954881](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4954881)
- [Engelberg et al. - Entity Neutering - SSRN:5182756](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5182756)
- [Wu et al. - Anonymization and Information Loss - arXiv:2511.15364](https://arxiv.org/html/2511.15364v1)
- [Didisheim et al. - AI's Predictable Memory - SSRN:5331177](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5331177)
- [Cao et al. - When LLMs Go Abroad - Harvard WP:26-013](https://www.hbs.edu/faculty/Pages/item.aspx?num=67903)
- [HKUST Survey - From Deep Learning to LLMs - arXiv:2503.21422](https://arxiv.org/pdf/2503.21422v1)

### Repos
- [FINSABER](https://github.com/waylonli/FINSABER)
- [StockBench](https://github.com/ChenYXxxx/stockbench)
- [AI-Trader](https://github.com/HKUDS/AI-Trader)
- [TradingAgents](https://github.com/TauricResearch/TradingAgents)
- [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT)
- [R&D-Agent-Quant](https://github.com/microsoft/RD-Agent)
- [Awesome-LLM-Quantitative-Trading-Papers](https://github.com/Tom-roujiang/Awesome-LLM-Quantitative-Trading-Papers)
