"""应用启动阶段数据库连通性测试。"""

import sys
import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


def test_init_db_validates_postgres_connection() -> None:
    """启动初始化必须真实连接 PostgreSQL 并执行轻量级连通性检查。"""
    import app.persistence.postgres as postgres

    connection = Mock()

    with patch.object(postgres, "_connect", return_value=connection) as connect:
        postgres.init_db()

    connect.assert_called_once_with()
    connection.execute.assert_called_once_with("SELECT 1")
    connection.close.assert_called_once_with()


def test_init_db_does_not_log_schema_initialization(caplog: pytest.LogCaptureFixture) -> None:
    """启动检查只验证连接，不应提示运行时初始化 schema 或表。"""
    import app.persistence.postgres as postgres

    connection = Mock()
    caplog.set_level(logging.INFO)

    with patch.object(postgres, "_connect", return_value=connection):
        postgres.init_db()

    assert "数据库结构初始化" not in caplog.text
    assert "创建 schema" not in caplog.text


def test_init_db_propagates_postgres_connection_error() -> None:
    """数据库不可达时，初始化异常必须向上传播，让应用启动失败。"""
    import app.persistence.postgres as postgres

    connection_error = RuntimeError("database unavailable")

    with patch.object(postgres, "_connect", side_effect=connection_error):
        with pytest.raises(RuntimeError, match="database unavailable"):
            postgres.init_db()


def test_init_db_closes_connection_when_probe_fails() -> None:
    """连接已建立但探测 SQL 失败时，初始化必须关闭连接并传播原异常。"""
    import app.persistence.postgres as postgres

    probe_error = RuntimeError("probe failed")
    connection = Mock()
    connection.execute.side_effect = probe_error

    with patch.object(postgres, "_connect", return_value=connection):
        with pytest.raises(RuntimeError, match="probe failed"):
            postgres.init_db()

    connection.execute.assert_called_once_with("SELECT 1")
    connection.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_lifespan_propagates_init_db_error() -> None:
    """lifespan 启动阶段必须传播 init_db 异常，阻止应用进入就绪状态。"""
    import app.main as main

    startup_error = RuntimeError("startup database unavailable")

    with patch.object(main, "init_db", side_effect=startup_error):
        with pytest.raises(RuntimeError, match="startup database unavailable"):
            await main.lifespan(main.app).__aenter__()


@pytest.mark.asyncio
async def test_lifespan_does_not_log_database_initialization_complete(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """启动成功后不应提示数据库初始化完成，避免误解为运行时建库建表。"""
    import app.main as main

    context = main.lifespan(main.app)
    caplog.set_level(logging.INFO)

    with patch.object(main, "init_db"):
        await context.__aenter__()
        await context.__aexit__(None, None, None)

    assert "数据库初始化完成" not in caplog.text
