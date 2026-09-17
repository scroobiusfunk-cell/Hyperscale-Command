from __future__ import annotations

import pytest

from app.logging import external_call


def test_external_call_records_extra_fields_on_success() -> None:
    with external_call("cxalloy", "fetch_equipment", version="v2") as record:
        record["item_count"] = 3
    assert record["item_count"] == 3


def test_external_call_reraises_and_still_logs() -> None:
    with pytest.raises(RuntimeError, match="provider down"):  # noqa: SIM117
        with external_call("llm", "extract", version="v1"):
            raise RuntimeError("provider down")
