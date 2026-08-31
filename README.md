# Multi-Agent Research Pipeline — crashproof, hand-wired, zero framework

> **Warning: agents don't behave.**
>
> Every tutorial shows you the happy path — three agents, one prompt, flawless output.
> Nobody shows you the second run. That's where it all falls apart.
>
> This is the pipeline I run in production. Four agents, wired by hand.
> No framework. No hidden retries. Every failure stays visible.

## What this is

A research pipeline that takes any topic and returns a **grounded, structured briefing**:

```json
{
  "title": "Impact of AI Agents on Developer Workflows",
  "keyPoints": ["...", "...", "..."],
  "takeaway": "...",
  "iterations": 1,
  "verdict": "APPROVED"
}
```

One command. ~15 seconds. No LangChain, no CrewAI, no orchestration dependencies —
just an HTTP client, a search library, and a strict quality gate.

## The four agents

```
topic ──▶ [researcher] ──▶ raw notes (with sources)
              │
notes ──▶ [summarizer] ──▶ structured JSON {title, keyPoints[3], takeaway}
              │
notes + summary ──▶ [evaluator] ──▶ "APPROVED" or "REVISE"
              │
[coordinator] runs the chain, checks every handoff,
              retries weak output (max 5 iterations), returns the best result
```

| Agent | Job | Failure mode if removed |
|---|---|---|
| **researcher** | Real web search → raw notes. No summary, no conclusions. | You summarize your own bias. |
| **summarizer** | Notes → strict JSON. 3 key points, one takeaway. | Unstructured prose nobody can use. |
| **evaluator** | Reads notes AND summary. Grounded? **APPROVED / REVISE**. | Polished wrong answers ship silently. |
| **coordinator** | Wires the three, owns the retry loop, caps at 5. | One weak pass and you're done. |

## Why no framework?

Because frameworks hide retries. A pipeline that *looks* like it worked is worse
than one that crashes — it hands you a **polished wrong answer** and nobody logged why.

Hand-wired agents fail loudly. You want loud. Logs are cheap; silent confidence isn't.

## The five crashproof rules

1. **Logging first.** Every agent call *and every handoff* is logged to a per-run JSONL
   file. Failures hide in handoffs, not in the agents — so we log the handoffs.
2. **Retry with backoff.** 429 / 5xx / network blips → exponential backoff + jitter.
3. **Hard timeouts.** One stuck upstream call can never hang the pipeline.
4. **Validate everything.** Empty topic → clean 400, not a stack trace.
5. **Cap the loop.** The evaluator can say REVISE forever; we cap at 5 and ship the best.

## Quickstart

```bash
git clone https://github.com/Amz34/multi-agent-research-pipeline.git
cd multi-agent-research-pipeline
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # add your DEEPSEEK_API_KEY (any OpenAI-compatible endpoint works)
python cli.py "impact of AI agents on developer workflows"
```

Machine-readable? Logs go to stderr, the result is pure JSON on stdout:

```bash
python cli.py "your topic" > briefing.json
```

## Run it as a service

Crashproof also means *it comes back*:

```bash
sudo bash deploy.sh
# systemd unit: Restart=always, starts on boot, memory-capped

curl -X POST localhost:8088/run \
  -H "Content-Type: application/json" \
  -d '{"topic": "Saudi Arabia facilities management market"}'
curl localhost:8088/health   # {"status":"ok"}
```

We killed it with `kill -9` in testing. It came back in ~3 seconds. That is the
standard we hold every AI system we build to.

## Go break it

The happy path takes 20 minutes to build. Breaking it properly is the real work.

- Feed it a vague topic (`"everything about AI"`) — still returns clean JSON.
- Empty topic — clean 400, logged.
- No API key — one clear error message, not a mystery.
- Kill the service mid-request — systemd restarts it; the next request works.

## What you can swap

- **Model**: any OpenAI-compatible API (`DEEPSEEK_URL`, `DEEPSEEK_MODEL`).
- **Search**: `agents/search.py` uses DuckDuckGo (no key required) — swap in
  Tavily/Brave/SerpAPI behind the same `research_notes()` signature.
- **Language**: the agents are 30 lines each. Port them to whatever you like.

## Say something

Star it if you'd run it. Open an issue when it breaks — the second run is where
the real lessons live, and that's the whole point of this repo.

What's the most polished wrong answer an AI ever gave you? Tell us. Issues are open.

## License

MIT. Steal it, break it, ship it — and tell us what broke.
