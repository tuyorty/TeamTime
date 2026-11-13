"""Модель не может придумать сумму, дату или провести операцию."""

import json
from datetime import date
from unittest.mock import AsyncMock

import pytest

from teamtime.core.config import Settings
from teamtime.services.fund import FundError
from teamtime.services.fund_language import extract


def model(monkeypatch, answer):
    class Response:
        content = type(
            "Content",
            (),
            {
                "read": AsyncMock(
                    return_value=json.dumps({"message": {"content": json.dumps(answer)}}).encode()
                )
            },
        )()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        def raise_for_status(self):
            pass

    class Client(Response):
        def __init__(self, **kwargs):
            pass

        def post(self, *args, **kwargs):
            assert kwargs["json"]["format"]["additionalProperties"] is False
            assert kwargs["json"]["stream"] is False
            return Response()

    monkeypatch.setattr("teamtime.services.fund_language.aiohttp.ClientSession", Client)
    return Settings(_env_file=None, fund_ollama_url="http://ollama.invalid:11434")


async def test_hallucinated_fields_are_cleared_before_confirmation(monkeypatch):
    config = model(
        monkeypatch,
        {
            "kind": "receipt",
            "amount": "5000",
            "occurred_on": "2026-11-01",
            "source": "Другой источник",
            "ambiguous": False,
        },
    )
    candidate = await extract("Получил 3000 от Источника А", config)
    assert candidate.amount is None
    assert candidate.occurred_on is None
    assert candidate.source is None


async def test_explicit_fields_are_only_a_candidate(monkeypatch):
    config = model(
        monkeypatch,
        {
            "kind": "receipt",
            "amount": "3100.25",
            "occurred_on": "2026-11-01",
            "source": "Источник А",
            "ambiguous": False,
        },
    )
    candidate = await extract("Источник А перечислил 3 100,25 на руки 01.11.2026", config)
    assert candidate.amount == "3100.25"
    assert candidate.occurred_on == date(2026, 11, 1)


@pytest.mark.parametrize("text", ["Итого получил 20000 за месяц", "Хочу пересмотреть зарплату"])
async def test_totals_and_salary_requests_never_become_receipts(monkeypatch, text):
    config = model(monkeypatch, {"kind": "receipt", "amount": "20000"})
    with pytest.raises(FundError):
        await extract(text, config)


async def test_unconfigured_model_keeps_manual_workflow_available():
    with pytest.raises(FundError, match="пошаговый"):
        await extract("Получил выплату", Settings(_env_file=None))
