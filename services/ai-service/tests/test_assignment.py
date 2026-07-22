from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import importlib.util
from pathlib import Path
import uuid

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.models import AnalystProfile
from app.schemas.scoring import AnalystSyncRequest, AssignmentStatus
from app.services.analyst_service import AnalystService
from app.services.assignment_service import AssignmentService


def profile_request(analyst_id, **overrides):
    values = {
        "analyst_id": analyst_id,
        "specializations": ["CALINTI_KART"],
        "regions": ["TR"],
        "active_cases": 0,
        "max_active_cases": 10,
        "accuracy_rate": Decimal("0.9000"),
        "is_active": True,
    }
    values.update(overrides)
    return AnalystSyncRequest(**values)


def seed(db, analyst_id, **overrides):
    AnalystService(db).sync(profile_request(analyst_id, **overrides))


def test_analyst_table_and_migration_upgrade_downgrade_exist(engine):
    assert "analyst_profiles" in inspect(engine).get_table_names()
    migration_path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "001_initial_ai_schema.py"
    )
    spec = importlib.util.spec_from_file_location("ai_initial_migration", migration_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert callable(module.upgrade)
    assert callable(module.downgrade)


def test_specialization_dominates_assignment_score(db):
    specialist = uuid.uuid4()
    generic = uuid.uuid4()
    seed(db, specialist, specializations=["CALINTI_KART"], accuracy_rate="0.80")
    seed(db, generic, specializations=["PARA_AKLAMA"], accuracy_rate="1.00")
    result = AssignmentService(db).assign("CALINTI_KART")
    db.commit()
    assert result.assigned_analyst_id == specialist
    assert result.assignment_status is AssignmentStatus.ASSIGNED


def test_full_and_inactive_analysts_are_excluded(db):
    full = uuid.uuid4()
    inactive = uuid.uuid4()
    available = uuid.uuid4()
    seed(db, full, active_cases=2, max_active_cases=2)
    seed(db, inactive, is_active=False)
    seed(db, available, specializations=["PARA_AKLAMA"])
    result = AssignmentService(db).assign("CALINTI_KART")
    db.commit()
    assert result.assigned_analyst_id == available


def test_accuracy_and_availability_contribute_to_ranking(db):
    accurate_but_busy = uuid.uuid4()
    available = uuid.uuid4()
    seed(
        db,
        accurate_but_busy,
        active_cases=9,
        max_active_cases=10,
        accuracy_rate="1.0",
    )
    seed(db, available, active_cases=0, max_active_cases=10, accuracy_rate="0.8")
    first = db.get(AnalystProfile, accurate_but_busy)
    second = db.get(AnalystProfile, available)
    assert AssignmentService.score(second, "CALINTI_KART") > AssignmentService.score(
        first, "CALINTI_KART"
    )
    result = AssignmentService(db).assign("CALINTI_KART")
    db.commit()
    assert result.assigned_analyst_id == available


def test_tie_breaks_by_active_cases_then_uuid(db):
    low_uuid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    high_uuid = uuid.UUID("00000000-0000-0000-0000-000000000002")
    seed(db, high_uuid, active_cases=2, max_active_cases=20)
    seed(db, low_uuid, active_cases=1, max_active_cases=10)
    # Same availability ratio and accuracy; lower active_cases wins.
    result = AssignmentService(db).assign("CALINTI_KART")
    db.commit()
    assert result.assigned_analyst_id == low_uuid

    db.query(AnalystProfile).delete()
    db.commit()
    seed(db, high_uuid)
    seed(db, low_uuid)
    tied = AssignmentService(db).assign("CALINTI_KART")
    db.commit()
    assert tied.assigned_analyst_id == low_uuid


def test_queue_when_no_capacity(db):
    seed(db, uuid.uuid4(), active_cases=1, max_active_cases=1)
    result = AssignmentService(db).assign("CALINTI_KART")
    assert result.assigned_analyst_id is None
    assert result.assignment_status is AssignmentStatus.QUEUED


def test_concurrent_assignment_never_exceeds_capacity(tmp_path):
    database_path = Path(tmp_path) / "assignment.db"
    engine = create_engine(
        f"sqlite+pysqlite:///{database_path}",
        connect_args={"check_same_thread": False, "timeout": 15},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=True)
    analyst_id = uuid.uuid4()
    with factory() as session:
        seed(session, analyst_id, max_active_cases=1)

    def assign_once():
        with factory() as session:
            result = AssignmentService(session).assign("CALINTI_KART")
            session.commit()
            return result.assignment_status

    with ThreadPoolExecutor(max_workers=4) as pool:
        statuses = list(pool.map(lambda _: assign_once(), range(4)))
    with Session(engine) as session:
        stored = session.scalar(select(AnalystProfile))
        assert stored.active_cases == 1
    assert statuses.count(AssignmentStatus.ASSIGNED) == 1
    assert statuses.count(AssignmentStatus.QUEUED) == 3
    engine.dispose()
