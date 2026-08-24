from __future__ import annotations

import os
import re
import threading
from collections.abc import Callable
from typing import Any

from yuxi.utils import logger

from neo4j import GraphDatabase as GD

_SAFE_NEO4J_LABEL_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_shared_neo4j_connection: Neo4jConnectionManager | None = None
_shared_neo4j_connection_lock = threading.Lock()


def safe_neo4j_label(value: str) -> str:
    if not _SAFE_NEO4J_LABEL_RE.match(value or ""):
        raise ValueError(f"非法 Neo4j 标签: {value}")
    return value


def _session(connection_or_driver):
    if hasattr(connection_or_driver, "session"):
        return connection_or_driver.session()
    return connection_or_driver.driver.session()


def neo4j_write(connection_or_driver, query: Callable) -> Any:
    """在写事务中执行 Cypher 操作的简写。"""
    with _session(connection_or_driver) as session:
        return session.execute_write(query)


def neo4j_read(connection_or_driver, cypher: str, **kwargs) -> list[dict[str, Any]]:
    """执行只读 Cypher 查询并返回结果列表。"""
    with _session(connection_or_driver) as session:
        result = session.run(cypher, **kwargs)
        return [record.data() for record in result]


class Neo4jConnectionManager:
    def __init__(self, settings: dict | None = None):
        self.driver = None
        if settings is None:
            from yuxi.config import config

            settings = config.resolve_infrastructure_config("graph_database")
        self.settings = settings
        self.database = str(settings.get("name") or "neo4j")
        self.signature = tuple(settings.values())
        self.status = "closed"
        if os.environ.get("LITE_MODE", "").lower() in ("true", "1"):
            logger.info("LITE_MODE enabled, skipping Neo4j connection")
            return
        self._connect()

    def _connect(self):
        if self.driver and self._is_connected():
            return

        uri = str(self.settings.get("uri") or "bolt://graph:7687")
        username = str(self.settings.get("username") or "neo4j")
        password = str(self.settings.get("password") or "")

        try:
            self.driver = GD.driver(uri, auth=(username, password))
            with self.session() as session:
                session.run("RETURN 1")
            self.status = "open"
            logger.info("Successfully connected to Neo4j")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            raise

    def _is_connected(self) -> bool:
        if not self.driver:
            return False
        try:
            with self.session() as session:
                session.run("RETURN 1")
            return True
        except Exception:
            return False

    def is_running(self):
        return self.status == "open" or self.status == "processing"

    def session(self):
        if not self.driver:
            raise RuntimeError("Neo4j connection is not initialized")
        return self.driver.session(database=self.database)

    def close(self):
        if self.driver:
            self.driver.close()
            self.driver = None
            self.status = "closed"


def get_shared_neo4j_connection() -> Neo4jConnectionManager:
    global _shared_neo4j_connection
    from yuxi.config import config

    signature = config.infrastructure_signature("graph_database")
    if (
        _shared_neo4j_connection is None
        or not _shared_neo4j_connection.driver
        or _shared_neo4j_connection.signature != signature
    ):
        with _shared_neo4j_connection_lock:
            if (
                _shared_neo4j_connection is None
                or not _shared_neo4j_connection.driver
                or _shared_neo4j_connection.signature != signature
            ):
                if _shared_neo4j_connection is not None:
                    _shared_neo4j_connection.close()
                _shared_neo4j_connection = Neo4jConnectionManager()
    return _shared_neo4j_connection


def close_shared_neo4j_connection() -> None:
    with _shared_neo4j_connection_lock:
        if _shared_neo4j_connection is not None:
            _shared_neo4j_connection.close()
