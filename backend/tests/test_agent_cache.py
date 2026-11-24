import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import agent, config, gemini, pipeline
from app.main import app
from seed.data import DEMO_INVOICES, INVOICES
from tests.test_pipeline import SAMPLES, run

CHIPS = ["Pay all held invoices due this week", "What is waiting for approval and why?", "Pay the Cedar & Pine Furniture invoice"]


def load_demo(conn):
    for i in INVOICES + DEMO_INVOICES:
        run(conn, i["file"])


@pytest.fixture()
def demo(env):
    conn, sent = env
    load_demo(conn)
    return conn, sent


def test_the_three_chips_are_recorded():
    entries = json.loads(agent.CACHE_FILE.read_text())
    assert [e["prompt"] for e in entries] == [c.lower() for c in CHIPS]
    for e in entries:
        assert e["reply"] and e["steps"] and {s["tool"] for s in e["steps"]} <= {"list_invoices", "run_checks", "propose_payment"}


@pytest.mark.parametrize("chip", CHIPS)
def test_chips_answer_instantly_with_no_gemini_call(demo, chip, monkeypatch):
    conn, sent = demo
    before = len(sent)
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")  # any Gemini call would raise
    monkeypatch.setattr(gemini, "post_generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Gemini was called")))
    out = agent.run_agent(conn, chip)
    assert out["cached"] is True and out["reply"] and out["steps"]
    assert all("result" in s for s in out["steps"])  # tools really ran, against the live invoices
    assert len(sent) == before  # replaying never pays anything


def test_proposal_chips_show_a_confirmable_proposal(demo):
    conn, _ = demo
    for chip in (CHIPS[0], CHIPS[2]):
        out = agent.run_agent(conn, chip)
        rec = out["proposal"]["recommended"]
        assert [r["invoice"]["supplier"] for r in rec] == ["Cedar & Pine Furniture"]
        assert out["proposal"]["total_recommended_paise"] == 31310000


def test_matching_is_case_and_space_insensitive(demo):
    conn, _ = demo
    assert agent.run_agent(conn, "  PAY the cedar & pine   furniture INVOICE ")["cached"] is True


def test_replay_goes_through_the_real_confirm_path_once(demo):
    conn, sent = demo
    before = len(sent)
    with TestClient(app) as c:
        out = c.post("/api/agent", json={"message": CHIPS[2]}).json()
        assert out["cached"] is True
        ids = [r["invoice"]["id"] for r in out["proposal"]["recommended"]]
        res = c.post("/api/agent/confirm", json={"invoice_ids": ids}).json()["results"]
        assert res[0]["paid"] is True and len(sent) == before + 1
        again = c.post("/api/agent/confirm", json={"invoice_ids": ids}).json()["results"]
        assert again[0]["paid"] is False and len(sent) == before + 1  # cannot be paid twice


def test_a_changed_state_or_a_new_question_is_not_served_from_the_cache(demo, monkeypatch):
    conn, _ = demo
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    assert agent.cached_run(conn, "Which supplier is the biggest?") is None  # not a recorded prompt
    pipeline.reject(conn, conn.execute("SELECT id FROM invoices WHERE status='HELD' LIMIT 1").fetchone()[0])
    assert agent.cached_run(conn, CHIPS[0]) is None  # the invoices are no longer in the recorded state
    with pytest.raises(gemini.GeminiError):
        agent.run_agent(conn, CHIPS[0])  # falls through to live Gemini (unavailable here)


def test_an_injected_client_bypasses_the_cache(demo, monkeypatch):
    """Tests (and any caller) that pass their own Gemini client always get a live run, never a recording."""
    conn, _ = demo
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    reply = {"role": "model", "parts": [{"text": "live answer"}]}

    def handler(req):
        return httpx.Response(200, json={"candidates": [{"content": reply}]})

    client = httpx.Client(base_url="https://g.test", transport=httpx.MockTransport(handler))
    out = agent.run_agent(conn, CHIPS[0], client=client)
    assert out["reply"] == "live answer" and "cached" not in out
