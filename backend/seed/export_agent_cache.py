"""Record the AP agent's answers to the three suggested prompts into seed/agent_cache.json (committed), so they are
instant on the live site. Needs GEMINI_API_KEY. Run from backend/:   python -m seed.export_agent_cache

It loads the demo data into a temporary database, asks the real Gemini agent each prompt once, and stores the tool calls
it made plus its reply. At runtime app/agent.py replays the tool calls against the live invoices (so proposals are
always computed fresh) and reuses only the wording. "Today" is fixed at 2026-11-06 for the recording because the demo
invoices are dated early November, so "due this week" is meaningful.
"""
import json
import tempfile
import time
from pathlib import Path

from app import agent, config, db, pipeline

PROMPTS = ["Pay all held invoices due this week", "What is waiting for approval and why?", "Pay the Cedar & Pine Furniture invoice"]
RECORDED_TODAY = "2026-11-06"
HERE = Path(__file__).parent


def main():
    from seed.seed import seed_db
    entries = []
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        config.DB_PATH = str(Path(tmp) / "agent.db")
        seed_db()
        conn = db.connect()
        for pdf in sorted((HERE / "invoices").glob("*.pdf")):
            pipeline.process_invoice(conn, pdf.read_bytes(), pdf.name)
        for prompt in PROMPTS:
            for attempt in range(1, 4):  # Gemini can time out or be briefly overloaded
                try:
                    entry = agent.record(conn, prompt, RECORDED_TODAY)
                    break
                except Exception as e:
                    print(f"attempt {attempt} failed ({type(e).__name__}); retrying", flush=True)
                    time.sleep(5)
            else:
                raise SystemExit(f"could not record {prompt!r}")
            print(f"recorded: {prompt!r} -> {[s['tool'] for s in entry['steps']]}", flush=True)
            entries.append(entry)
            time.sleep(2)
        conn.close()
    (HERE / "agent_cache.json").write_text(json.dumps(entries, indent=1))
    print(f"saved {len(entries)} recordings")


if __name__ == "__main__":
    main()
