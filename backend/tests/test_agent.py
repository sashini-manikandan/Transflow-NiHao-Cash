"""Agent tests.

A fake provider stands in for OpenAI so the tool-calling loop, the validation
rules and the safety boundaries are tested without a network call or an API key.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app.agent.llm_provider import LLMToolCall, LLMTurn, LLMUnavailable
from app.agent.service import AgentService
from app.agent.tools import (
    ALLOWED_TOOL_NAMES,
    TOOL_REGISTRY,
    ToolContext,
    ToolValidationError,
    execute_tool,
    tool_definitions,
)
from app.config import Settings


class FakeProvider:
    """Replays a scripted sequence of model turns and records what it saw."""

    def __init__(self, turns: list[LLMTurn], model: str = "fake-model"):
        self._turns = list(turns)
        self.model = model
        self.available = True
        self.calls: list[dict] = []

    def respond(self, *, instructions, messages, tools):
        self.calls.append(
            {"instructions": instructions, "messages": list(messages), "tools": tools}
        )
        if not self._turns:
            return LLMTurn(text="done")
        return self._turns.pop(0)


class BrokenProvider:
    model = "fake-model"
    available = True

    def respond(self, **_kwargs):
        raise LLMUnavailable("The assistant timed out before the model replied.")


def _call(name: str, arguments: dict, call_id: str = "call_1") -> LLMToolCall:
    return LLMToolCall(call_id=call_id, name=name, arguments_json=json.dumps(arguments))


def _settings(**overrides) -> Settings:
    base = {
        "openai_api_key": "",
        "agent_max_tool_iterations": 4,
        "agent_max_tool_calls": 8,
        "database_url": "sqlite://",
    }
    base.update(overrides)
    return Settings(**base)


def _agent(db, user, provider=None, today=None, **setting_overrides) -> AgentService:
    return AgentService(
        db, user, _settings(**setting_overrides),
        today=today or date.today(), provider=provider,
    )


# --------------------------------------------------------------------------
# tool registry contract
# --------------------------------------------------------------------------
def test_the_allowlist_is_exactly_the_seven_specified_tools():
    assert ALLOWED_TOOL_NAMES == {
        "get_recurring_payments",
        "get_upcoming_bills",
        "forecast_balance",
        "analyze_subscriptions",
        "analyze_currency_costs",
        "get_savings_options",
        "create_reminder",
    }


def test_tool_schemas_are_closed_and_well_formed():
    definitions = tool_definitions()
    assert len(definitions) == len(TOOL_REGISTRY)
    for definition in definitions:
        assert definition["type"] == "function"
        assert definition["description"]
        assert definition["parameters"]["additionalProperties"] is False


def test_no_tool_accepts_a_user_scoping_argument():
    for spec in TOOL_REGISTRY.values():
        fields = set(spec.args_model.model_fields)
        assert not fields & {"user_id", "user", "email", "account_id"}


def test_every_tool_result_declares_currency_period_and_uncertainty(live_seeded, db):
    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    for name, spec in TOOL_REGISTRY.items():
        arguments = (
            {"title": "Check tuition", "due_date": (date.today() + timedelta(days=3)).isoformat()}
            if name == "create_reminder"
            else {}
        )
        payload = execute_tool(ctx, name, arguments)
        assert payload["tool"] == name
        assert payload["reporting_currency"] == "AED"
        assert payload["period"]
        assert payload["uncertainty"]
        assert payload["scope"] == "current user only"
        assert "demo data" in payload["data_source"].lower()


# --------------------------------------------------------------------------
# argument validation
# --------------------------------------------------------------------------
def test_unknown_tool_name_is_refused(live_seeded, db):
    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    with pytest.raises(ToolValidationError, match="Unknown tool"):
        execute_tool(ctx, "drop_all_tables", {})


def test_out_of_range_arguments_are_refused(live_seeded, db):
    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    with pytest.raises(ToolValidationError):
        execute_tool(ctx, "forecast_balance", {"horizon_days": 100000})
    with pytest.raises(ToolValidationError):
        execute_tool(ctx, "forecast_balance", {"horizon_days": 0})
    with pytest.raises(ToolValidationError):
        execute_tool(ctx, "get_recurring_payments", {"min_confidence": 5})
    with pytest.raises(ToolValidationError):
        execute_tool(ctx, "get_recurring_payments", {"status": "everything"})


def test_unexpected_arguments_are_refused_rather_than_ignored(live_seeded, db):
    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    with pytest.raises(ToolValidationError):
        execute_tool(ctx, "get_upcoming_bills", {"days_ahead": 30, "sql": "DROP TABLE users"})


def test_a_model_supplied_user_id_is_rejected_outright(live_seeded, db, second_user):
    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    with pytest.raises(ToolValidationError, match="Scope is set by the server"):
        execute_tool(ctx, "get_upcoming_bills", {"user_id": second_user.id})


def test_tools_only_ever_read_the_context_user(live_seeded, db, second_user):
    ctx = ToolContext(db=db, user=second_user, today=date.today())
    payload = execute_tool(ctx, "get_upcoming_bills", {"days_ahead": 30})
    names = [b["name"] for b in payload["data"]["bills"]]
    assert names == ["Other user private bill"]


# --------------------------------------------------------------------------
# the loop
# --------------------------------------------------------------------------
def test_a_tool_result_is_fed_back_and_the_answer_is_returned(live_seeded, db):
    provider = FakeProvider(
        [
            LLMTurn(
                tool_calls=[_call("get_upcoming_bills", {"days_ahead": 30})],
                raw_output=[{"type": "function_call", "call_id": "call_1"}],
            ),
            LLMTurn(text="You have bills due soon."),
        ]
    )
    result = _agent(db, live_seeded, provider).run("What is due?")

    assert result.mode == "llm"
    assert result.answer == "You have bills due soon."
    assert [t.tool for t in result.tool_calls] == ["get_upcoming_bills"]
    assert result.tool_calls[0].status == "ok"
    assert result.facts

    second_turn_messages = provider.calls[1]["messages"]
    outputs = [i for i in second_turn_messages if i.get("role") == "tool"]
    assert len(outputs) == 1
    assert "total_due_base" in outputs[0]["content"]


def test_several_tools_in_one_turn_all_run(live_seeded, db):
    provider = FakeProvider(
        [
            LLMTurn(
                tool_calls=[
                    _call("get_upcoming_bills", {"days_ahead": 14}, "c1"),
                    _call("forecast_balance", {"horizon_days": 30}, "c2"),
                    _call("analyze_subscriptions", {}, "c3"),
                ],
                raw_output=[],
            ),
            LLMTurn(text="Combined answer."),
        ]
    )
    result = _agent(db, live_seeded, provider).run("Give me a full picture")

    assert [t.tool for t in result.tool_calls] == [
        "get_upcoming_bills", "forecast_balance", "analyze_subscriptions",
    ]
    assert all(t.status == "ok" for t in result.tool_calls)


def test_a_hallucinated_tool_is_blocked_and_reported_back_to_the_model(live_seeded, db):
    provider = FakeProvider(
        [
            LLMTurn(tool_calls=[_call("transfer_money", {"amount": 500})], raw_output=[]),
            LLMTurn(text="I cannot do that."),
        ]
    )
    result = _agent(db, live_seeded, provider).run("Send 500 to my friend")

    assert result.tool_calls[0].status == "rejected"
    assert "not an available tool" in result.tool_calls[0].error

    outputs = [i for i in provider.calls[1]["messages"] if i.get("role") == "tool"]
    assert json.loads(outputs[0]["content"])["error"] == "rejected"


def test_bad_arguments_are_surfaced_to_the_model_not_executed(live_seeded, db):
    provider = FakeProvider(
        [
            LLMTurn(
                tool_calls=[_call("forecast_balance", {"horizon_days": -5})], raw_output=[]
            ),
            LLMTurn(text="I need a valid horizon."),
        ]
    )
    result = _agent(db, live_seeded, provider).run("forecast please")

    assert result.tool_calls[0].status == "invalid_arguments"
    assert "horizon_days" in result.tool_calls[0].error


def test_malformed_json_arguments_do_not_crash_the_loop(live_seeded, db):
    provider = FakeProvider(
        [
            LLMTurn(
                tool_calls=[
                    LLMToolCall(call_id="c1", name="get_upcoming_bills", arguments_json="{oops")
                ],
                raw_output=[],
            ),
            LLMTurn(text="Recovered."),
        ]
    )
    result = _agent(db, live_seeded, provider).run("bills?")
    assert result.tool_calls[0].status == "invalid_arguments"
    assert result.answer == "Recovered."


def test_the_iteration_cap_stops_a_tool_calling_loop(live_seeded, db):
    looping = [
        LLMTurn(tool_calls=[_call("get_upcoming_bills", {}, f"c{i}")], raw_output=[])
        for i in range(20)
    ]
    provider = FakeProvider(looping)
    result = _agent(db, live_seeded, provider, agent_max_tool_iterations=3).run("loop")

    assert result.iterations == 3
    assert result.truncated is True
    assert len(result.tool_calls) == 3


def test_the_tool_call_budget_is_enforced_within_a_single_turn(live_seeded, db):
    provider = FakeProvider(
        [
            LLMTurn(
                tool_calls=[_call("get_upcoming_bills", {}, f"c{i}") for i in range(6)],
                raw_output=[],
            ),
            LLMTurn(text="Partial answer."),
        ]
    )
    result = _agent(db, live_seeded, provider, agent_max_tool_calls=2).run("spam")

    assert len([t for t in result.tool_calls if t.status == "ok"]) == 2
    assert result.truncated is True


def test_a_provider_outage_degrades_to_the_offline_answer(live_seeded, db):
    result = _agent(db, live_seeded, BrokenProvider()).run("What bills are due?")

    assert result.mode == "offline_deterministic"
    assert "timed out" in result.answer
    assert result.tool_calls


# --------------------------------------------------------------------------
# prompt and data safety
# --------------------------------------------------------------------------
def test_instructions_forbid_self_calculation_and_require_uncertainty(live_seeded, db):
    provider = FakeProvider([LLMTurn(text="hi")])
    _agent(db, live_seeded, provider).run("hello")

    instructions = provider.calls[0]["instructions"].lower()
    assert "never calculate" in instructions
    assert "untrusted data" in instructions
    assert "cannot cancel a subscription" in instructions
    assert "passwords" in instructions
    assert "cross-border" in instructions or "remittance" in instructions
    assert "linked" in instructions or "one cash-flow" in instructions
    assert "fx_sensitivity_whatif" in instructions or "what if the cedi" in instructions
    assert "month-vs-month" in instructions or "this-month vs last-month" in instructions


def test_no_secret_or_connection_string_is_ever_sent_to_the_model(live_seeded, db):
    provider = FakeProvider(
        [
            LLMTurn(tool_calls=[_call("analyze_currency_costs", {"months": 6})], raw_output=[]),
            LLMTurn(text="ok"),
        ]
    )
    settings = _settings(openai_api_key="sk-test-SHOULD-NEVER-APPEAR")
    agent = AgentService(db, live_seeded, settings, provider=provider)
    agent.run("currency costs?")

    transmitted = json.dumps(
        [{"i": c["instructions"], "p": c["messages"]} for c in provider.calls], default=str
    )
    assert "sk-test-SHOULD-NEVER-APPEAR" not in transmitted
    assert "sqlite" not in transmitted.lower()
    assert "DATABASE_URL" not in transmitted


def test_tool_output_carries_no_other_users_data(live_seeded, db, second_user):
    provider = FakeProvider(
        [
            LLMTurn(tool_calls=[_call("get_upcoming_bills", {"days_ahead": 60})], raw_output=[]),
            LLMTurn(text="ok"),
        ]
    )
    _agent(db, live_seeded, provider).run("bills?")

    transmitted = json.dumps(provider.calls[1]["messages"], default=str)
    assert "Other user private bill" not in transmitted
    assert "SECRET OTHER USER" not in transmitted


def test_conversation_history_is_bounded(live_seeded, db):
    provider = FakeProvider([LLMTurn(text="ok")])
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"turn {i}"}
        for i in range(40)
    ]
    _agent(db, live_seeded, provider).run("latest", history=history)

    sent = provider.calls[0]["messages"]
    assert len(sent) == 13  # 12 history turns plus the new message
    assert sent[-1]["content"] == "latest"


# --------------------------------------------------------------------------
# state-changing tool
# --------------------------------------------------------------------------
def test_an_assistant_reminder_is_a_draft_awaiting_confirmation(live_seeded, db):
    from app.models import Reminder

    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    payload = execute_tool(
        ctx,
        "create_reminder",
        {
            "title": "Pay tuition instalment",
            "due_date": (date.today() + timedelta(days=10)).isoformat(),
            "related_kind": "bill",
        },
    )

    assert payload["data"]["created"] is True
    assert payload["data"]["status"] == "pending_confirmation"
    assert payload["data"]["requires_user_confirmation"] is True

    stored = db.query(Reminder).filter(Reminder.id == payload["data"]["reminder_id"]).one()
    assert stored.status == "pending_confirmation"
    assert stored.created_by == "assistant"
    assert stored.user_id == live_seeded.id


def test_a_reminder_in_the_past_is_refused(live_seeded, db):
    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    payload = execute_tool(
        ctx,
        "create_reminder",
        {"title": "Too late", "due_date": (date.today() - timedelta(days=30)).isoformat()},
    )
    assert payload["data"]["created"] is False
    assert "past" in payload["data"]["reason"]


def test_tool_use_is_audited_without_recording_financial_detail(live_seeded, db):
    from app.models import AuditLog

    provider = FakeProvider(
        [
            LLMTurn(tool_calls=[_call("analyze_subscriptions", {})], raw_output=[]),
            LLMTurn(text="ok"),
        ]
    )
    _agent(db, live_seeded, provider).run("subs?")

    logs = db.query(AuditLog).filter(AuditLog.event == "tool_call").all()
    assert logs
    entry = logs[-1]
    assert entry.tool_name == "analyze_subscriptions"
    assert entry.authorized is True
    assert entry.user_id == live_seeded.id
    assert "AED" not in entry.detail
    assert "Netflix" not in entry.detail


def test_a_rejected_tool_is_audited_as_unauthorized(live_seeded, db):
    from app.models import AuditLog

    provider = FakeProvider(
        [
            LLMTurn(tool_calls=[_call("delete_everything", {})], raw_output=[]),
            LLMTurn(text="no"),
        ]
    )
    _agent(db, live_seeded, provider).run("delete it all")

    rejected = db.query(AuditLog).filter(AuditLog.event == "tool_call_rejected").all()
    assert rejected
    assert rejected[-1].authorized is False
    assert rejected[-1].outcome == "not_allowlisted"


# --------------------------------------------------------------------------
# payload cost
#
# Tool output is resent on every iteration, so an oversized payload is paid
# for repeatedly. These budgets are deliberately loose; they exist to catch a
# tool quietly growing an unbounded list, not to pin an exact size.
# --------------------------------------------------------------------------
def _approx_tokens(payload: dict) -> int:
    return len(json.dumps(payload, default=str)) // 4


@pytest.mark.parametrize(
    "tool,arguments,budget",
    [
        ("analyze_subscriptions", {"include_dormant": False}, 5000),
        ("forecast_balance", {"horizon_days": 30}, 2500),
        ("get_recurring_payments", {"status": "active", "limit": 20}, 3500),
        ("get_savings_options", {"limit": 6}, 2500),
        ("analyze_currency_costs", {"months": 6}, 1500),
        ("get_upcoming_bills", {"days_ahead": 30}, 1000),
    ],
)
def test_tool_payloads_stay_within_a_token_budget(
    live_seeded, db, tool, arguments, budget
):
    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    assert _approx_tokens(execute_tool(ctx, tool, arguments)) < budget


def test_recurrence_detection_runs_once_per_request(live_seeded, db, monkeypatch):
    """Four tools need the same series; recomputing it for each is pure waste."""
    from app.services import analysis

    runs = []
    original = analysis.detect_recurring
    monkeypatch.setattr(
        analysis, "detect_recurring",
        lambda *a, **k: (runs.append(1), original(*a, **k))[1],
    )

    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    execute_tool(ctx, "get_recurring_payments", {"status": "active"})
    execute_tool(ctx, "forecast_balance", {"horizon_days": 30})
    execute_tool(ctx, "analyze_subscriptions", {"include_dormant": False})
    execute_tool(ctx, "get_savings_options", {"limit": 6})

    assert len(runs) == 1


def test_the_model_is_not_given_raw_transaction_ids_for_subscriptions(live_seeded, db):
    """It cannot verify an id, and the count plus date range say more."""
    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    payload = execute_tool(ctx, "analyze_subscriptions", {"include_dormant": False})

    for entry in payload["data"]["subscriptions"]:
        assert "evidence_sample" not in entry
        assert entry["observed"]["charges_observed"] is not None
        assert entry["observed"]["first_seen"] and entry["observed"]["last_seen"]


def test_a_stale_rate_is_still_flagged_after_the_forecast_is_trimmed(live_seeded, db):
    """Dropping the per-event prose must not drop the caveat itself."""
    ctx = ToolContext(db=db, user=live_seeded, today=date.today())
    payload = execute_tool(ctx, "forecast_balance", {"horizon_days": 60})

    events = payload["data"]["events"]
    assert events
    assert all("fx_note" not in e for e in events)
    assert "rate_stale" in payload["uncertainty"]["guidance"]
    assert any(e.get("rate_stale") for e in events)


# --------------------------------------------------------------------------
# offline mode
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "question,expected_tool",
    [
        ("What bills are due this month?", "get_upcoming_bills"),
        ("Can I afford my tuition payment?", "forecast_balance"),
        ("Am I paying for Netflix twice?", "analyze_subscriptions"),
        ("How much do I lose on exchange fees?", "analyze_currency_costs"),
        ("Where can I save money?", "get_savings_options"),
    ],
)
def test_offline_mode_routes_questions_to_the_right_tool(
    live_seeded, db, question, expected_tool
):
    result = _agent(db, live_seeded).run(question)
    assert result.mode == "offline_deterministic"
    assert expected_tool in [t.tool for t in result.tool_calls]
    assert result.facts


def test_offline_answers_label_themselves_and_cite_figures(live_seeded, db):
    result = _agent(db, live_seeded).run("What bills do I have coming up?")
    assert "no language model is configured" in result.answer
    assert "AED" in result.answer
    assert result.model is None


def test_offline_mode_falls_back_to_an_overview_for_vague_questions(live_seeded, db):
    result = _agent(db, live_seeded).run("hello there")
    assert len(result.tool_calls) == 3
    assert result.answer


@pytest.mark.parametrize(
    "question,expected_tool",
    [
        # "wasting" must reach the keyword "waste" despite the suffix.
        ("How much am I wasting on streaming?", "get_savings_options"),
        ("Will I go overdrawn before my next instalment?", "forecast_balance"),
        ("What happens if the cedi drops 10 percent?", "analyze_currency_costs"),
        ("Are my renewals costing me too much?", "get_recurring_payments"),
        ("Has anything been repriced?", "analyze_subscriptions"),
    ],
)
def test_offline_routing_survives_word_endings(
    live_seeded, db, question, expected_tool
):
    result = _agent(db, live_seeded).run(question)
    assert expected_tool in [t.tool for t in result.tool_calls]


def test_an_unmatched_question_says_so_instead_of_pretending(live_seeded, db):
    """A generic dump presented as an answer would be misleading."""
    result = _agent(db, live_seeded).run("Compare my spending with last year")
    assert "could not match that question" in result.answer


def test_a_follow_up_reuses_the_previous_question_s_tools(live_seeded, db):
    history = [
        {"role": "user", "content": "What bills are due this month?"},
        {"role": "assistant", "content": "Four bills are due."},
    ]
    result = _agent(db, live_seeded).run("and what about the one after that?", history)

    assert "get_upcoming_bills" in [t.tool for t in result.tool_calls]
    assert "follow-up" in result.answer


def test_a_follow_up_without_any_history_is_not_faked(live_seeded, db):
    result = _agent(db, live_seeded).run("what about that one?")
    assert "follow-up" not in result.answer
    assert "could not match that question" in result.answer


def test_a_new_topic_is_not_mistaken_for_a_follow_up(live_seeded, db):
    """'this month' is not a back-reference, and must not reuse the old plan."""
    history = [{"role": "user", "content": "Am I paying for Netflix twice?"}]
    result = _agent(db, live_seeded).run(
        "Compare my spending this month with last month", history
    )
    assert "follow-up" not in result.answer
