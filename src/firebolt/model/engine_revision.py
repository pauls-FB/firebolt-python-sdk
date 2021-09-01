from __future__ import annotations

from datetime import datetime

from pydantic import Field

from firebolt.firebolt_client import get_firebolt_client
from firebolt.model import FireboltBaseModel
from firebolt.model.instance_type import InstanceTypeKey, instance_types


class EngineRevisionKey(FireboltBaseModel):
    account_id: str
    engine_id: str
    engine_revision_id: str


class Specification(FireboltBaseModel):
    """
    An EngineRevision Specification.

    Notably, it determines which instance types and how many of them its Engine gets.

    See Also: engine.Settings, which also contains engine configuration.
    """

    db_compute_instances_type_key: InstanceTypeKey = Field(
        alias="db_compute_instances_type_id"
    )
    db_compute_instances_count: int
    db_compute_instances_use_spot: bool
    db_version: str
    proxy_instances_type_key: InstanceTypeKey = Field(alias="proxy_instances_type_id")
    proxy_instances_count: int
    proxy_version: str

    @classmethod
    def ingest_default(cls) -> Specification:
        """Default Specification for data ingestion"""
        instance_type_key = instance_types.get_by_name(instance_name="i3.4xlarge").key
        return cls(
            db_compute_instances_type_id=instance_type_key,
            db_compute_instances_count=2,
            db_compute_instances_use_spot=False,
            db_version="",
            proxy_instances_type_id=instance_type_key,
            proxy_instances_count=1,
            proxy_version="",
        )

    @classmethod
    def analytics_default(cls) -> Specification:
        """Default Specification for analytics (querying)"""
        instance_type_key = instance_types.get_by_name(instance_name="m5d.4xlarge").key
        return cls(
            db_compute_instances_type_id=instance_type_key,
            db_compute_instances_count=1,
            db_compute_instances_use_spot=False,
            db_version="",
            proxy_instances_type_id=instance_type_key,
            proxy_instances_count=1,
            proxy_version="",
        )


class EngineRevision(FireboltBaseModel):
    """
    A Firebolt Engine revision, which contains a Specification (instance types, counts).

    As engines are updated with new settings, revisions are created.
    """

    key: EngineRevisionKey = Field(alias="id")
    current_status: str
    specification: Specification
    create_time: datetime
    create_actor: str
    last_update_time: datetime
    last_update_actor: str
    desired_status: str
    health_status: str

    @classmethod
    def get_by_id(cls, engine_id: str, engine_revision_id: str) -> EngineRevision:
        """Get an EngineRevision by engine_id and engine_revision_id"""
        fc = get_firebolt_client()
        return cls.get_by_engine_revision_key(
            EngineRevisionKey(
                account_id=fc.account_id,
                engine_id=engine_id,
                engine_revision_id=engine_revision_id,
            )
        )

    @classmethod
    def get_by_engine_revision_key(
        cls, engine_revision_key: EngineRevisionKey
    ) -> EngineRevision:
        """
        Fetch an EngineRevision from Firebolt by it's key.

        Args:
            engine_revision_key: Key of the desired EngineRevision.

        Returns:
            The requested EngineRevision
        """
        fc = get_firebolt_client()
        response = fc.http_client.get(
            url=f"/core/v1/accounts/{engine_revision_key.account_id}"
            f"/engines/{engine_revision_key.engine_id}"
            f"/engineRevisions/{engine_revision_key.engine_revision_id}",
        )
        engine_spec: dict = response.json()["engine_revision"]
        return cls.parse_obj(engine_spec)

    @classmethod
    def analytics_default(cls) -> EngineRevision:
        """Get an EngineRevision configured with default settings for analytics"""
        return cls.construct(specification=Specification.analytics_default())

    @classmethod
    def ingest_default(cls) -> EngineRevision:
        """Get an EngineRevision configured with default settings for ingestion"""
        return cls.construct(specification=Specification.ingest_default())
