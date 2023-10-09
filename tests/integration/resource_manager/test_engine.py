from collections import namedtuple

from firebolt.client.auth import Auth
from firebolt.service.manager import ResourceManager
from firebolt.service.types import EngineStatus, EngineType, WarmupMethod


def make_engine_name(database_name: str, suffix: str) -> str:
    return f"{database_name}_{suffix}"


def test_create_start_stop_engine(
    auth: Auth,
    account_name: str,
    api_endpoint: str,
    database_name: str,
):
    rm = ResourceManager(
        auth=auth, account_name=account_name, api_endpoint=api_endpoint
    )
    name = make_engine_name(database_name, "start_stop")

    engine = rm.engines.create(name=name)
    assert engine.name == name

    database = rm.databases.create(name=name)
    assert database.name == name

    engine.attach_to_database(database)
    assert engine.database == database

    engine.start()
    assert engine.current_status == EngineStatus.RUNNING

    engine.stop()
    assert engine.current_status in {EngineStatus.STOPPING, EngineStatus.STOPPED}

    engine.delete()
    database.delete()


ParamValue = namedtuple("ParamValue", "set expected")
ENGINE_UPDATE_PARAMS = {
    "scale": ParamValue(3, 3),
    "spec": ParamValue("B1", "B1"),
    "auto_stop": ParamValue(123, 7380),
    "warmup": ParamValue(WarmupMethod.PRELOAD_ALL_DATA, WarmupMethod.PRELOAD_ALL_DATA),
    "engine_type": ParamValue(EngineType.DATA_ANALYTICS, EngineType.DATA_ANALYTICS),
}


def test_engine_update_single_parameter(
    auth: Auth,
    account_name: str,
    api_endpoint: str,
    database_name: str,
):
    rm = ResourceManager(
        auth=auth, account_name=account_name, api_endpoint=api_endpoint
    )

    name = make_engine_name(database_name, "single_param")
    engine = rm.engines.create(name=name)

    engine.attach_to_database(rm.databases.get(database_name))
    assert engine.database.name == database_name

    for param, value in ENGINE_UPDATE_PARAMS.items():
        engine.update(**{param: value.set})

        engine_new = rm.engines.get(name)
        if param == "spec":
            current_value = engine_new.spec.name
        elif param == "engine_type":
            current_value = engine_new.type
        else:
            current_value = getattr(engine_new, param)
        assert current_value == value.expected, f"Invalid {param} value"

    engine.delete()


def test_engine_update_multiple_parameters(
    auth: Auth,
    account_name: str,
    api_endpoint: str,
    database_name: str,
):
    rm = ResourceManager(
        auth=auth, account_name=account_name, api_endpoint=api_endpoint
    )

    name = make_engine_name(database_name, "multi_param")
    engine = rm.engines.create(name=name)

    engine.attach_to_database(rm.databases.get(database_name))
    assert engine.database.name == database_name

    engine.update(
        **dict({(param, value.set) for param, value in ENGINE_UPDATE_PARAMS.items()})
    )

    engine_new = rm.engines.get(name)

    for param, value in ENGINE_UPDATE_PARAMS.items():
        if param == "spec":
            current_value = engine_new.spec.name
        elif param == "engine_type":
            current_value = engine_new.type
        else:
            current_value = getattr(engine_new, param)
        assert current_value == value.expected, f"Invalid {param} value"

    engine.delete()
