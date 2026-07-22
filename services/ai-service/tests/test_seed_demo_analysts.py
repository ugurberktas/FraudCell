import uuid

from sqlalchemy import select

from app.models import AnalystProfile
from scripts import seed_demo_analysts


def set_seed_environment(monkeypatch):
    values = {
        "DEMO_CARD_ANALYST_ID": str(uuid.uuid4()),
        "DEMO_ACCOUNT_ANALYST_ID": str(uuid.uuid4()),
        "DEMO_LAUNDERING_ANALYST_ID": str(uuid.uuid4()),
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def test_seed_requires_all_identity_analyst_ids(engine, monkeypatch, capsys):
    monkeypatch.setattr(seed_demo_analysts, "_get_engine", lambda: engine)
    for key in (
        "DEMO_CARD_ANALYST_ID",
        "DEMO_ACCOUNT_ANALYST_ID",
        "DEMO_LAUNDERING_ANALYST_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    assert seed_demo_analysts.main([]) == 1
    assert "Missing analyst UUID" in capsys.readouterr().err


def test_seed_is_idempotent_and_creates_three_specialists(
    engine, monkeypatch, capsys
):
    monkeypatch.setattr(seed_demo_analysts, "_get_engine", lambda: engine)
    values = set_seed_environment(monkeypatch)
    assert seed_demo_analysts.main([]) == 0
    assert seed_demo_analysts.main([]) == 0
    output = capsys.readouterr().out
    assert "Demo analyst profile synchronized" in output

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        profiles = session.scalars(select(AnalystProfile)).all()
        assert len(profiles) == 3
        assert {str(profile.analyst_id) for profile in profiles} == set(values.values())
        assert {profile.specializations[0] for profile in profiles} == {
            "CALINTI_KART",
            "HESAP_ELE_GECIRME",
            "PARA_AKLAMA",
        }
