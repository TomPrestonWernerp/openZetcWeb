"""对象存储、向量数据库和图数据库多来源配置仓储。"""

from __future__ import annotations

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from openzetc.storage.postgres.models_business import (
    GraphDatabaseConfig,
    ObjectStorageConfig,
    VectorDatabaseConfig,
)

type InfrastructureSource = ObjectStorageConfig | VectorDatabaseConfig | GraphDatabaseConfig

MODEL_BY_SECTION = {
    "object_storage": ObjectStorageConfig,
    "vector_database": VectorDatabaseConfig,
    "graph_database": GraphDatabaseConfig,
}


def get_model(section: str):
    try:
        return MODEL_BY_SECTION[section]
    except KeyError as exc:
        raise ValueError(f"不支持的基础设施配置类型: {section}") from exc


class InfrastructureConfigRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list(self, section: str) -> list[InfrastructureSource]:
        model = get_model(section)
        result = await self.session.execute(
            select(model).order_by(model.is_active.desc(), model.config_name, model.id)
        )
        return list(result.scalars().all())

    async def get(self, section: str, source_id: int) -> InfrastructureSource | None:
        return await self.session.get(get_model(section), source_id)

    async def get_by_name(self, section: str, config_name: str) -> InfrastructureSource | None:
        model = get_model(section)
        result = await self.session.execute(select(model).where(model.config_name == config_name))
        return result.scalar_one_or_none()

    async def get_active(self, section: str) -> InfrastructureSource | None:
        model = get_model(section)
        result = await self.session.execute(select(model).where(model.is_active.is_(True)))
        return result.scalar_one_or_none()

    async def count(self, section: str) -> int:
        model = get_model(section)
        result = await self.session.execute(select(func.count(model.id)))
        return int(result.scalar() or 0)

    async def create(
        self,
        section: str,
        *,
        config_name: str,
        provider: str,
        config_json: dict,
        is_active: bool = False,
        updated_by_uid: str | None = None,
    ) -> InfrastructureSource:
        model = get_model(section)
        row = model(
            config_name=config_name,
            provider=provider,
            config_json=config_json,
            is_active=is_active,
            created_by_uid=updated_by_uid,
            updated_by_uid=updated_by_uid,
        )
        self.session.add(row)
        await self.session.flush()
        return row

    async def update(
        self,
        row: InfrastructureSource,
        *,
        config_name: str,
        provider: str,
        config_json: dict,
        updated_by_uid: str | None = None,
    ) -> InfrastructureSource:
        row.config_name = config_name
        row.provider = provider
        row.config_json = config_json
        row.updated_by_uid = updated_by_uid
        await self.session.flush()
        return row

    async def activate(self, section: str, source_id: int) -> InfrastructureSource:
        model = get_model(section)
        row = await self.get(section, source_id)
        if row is None:
            raise ValueError("配置来源不存在")
        await self.session.execute(update(model).values(is_active=False))
        await self.session.flush()
        row.is_active = True
        await self.session.flush()
        return row

    async def delete(self, section: str, source_id: int) -> bool:
        model = get_model(section)
        result = await self.session.execute(delete(model).where(model.id == source_id))
        await self.session.flush()
        return bool(result.rowcount)
