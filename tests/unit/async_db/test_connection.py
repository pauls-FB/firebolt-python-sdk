from typing import Callable, List
from unittest.mock import patch

from pyfakefs.fake_filesystem_unittest import Patcher
from pytest import mark, raises
from pytest_httpx import HTTPXMock

from firebolt.async_db.connection import Connection, connect
from firebolt.client.auth import Auth, ClientCredentials
from firebolt.common._types import ColType
from firebolt.common.settings import Settings
from firebolt.utils.exception import (
    ConfigurationError,
    ConnectionClosedError,
    EngineNotRunningError,
    InterfaceError,
)
from firebolt.utils.token_storage import TokenSecureStorage


async def test_closed_connection(connection: Connection) -> None:
    """Connection methods are unavailable for closed connection."""
    await connection.aclose()

    with raises(ConnectionClosedError):
        connection.cursor()

    with raises(ConnectionClosedError):
        async with connection:
            pass

    await connection.aclose()


async def test_cursors_closed_on_close(connection: Connection) -> None:
    """Connection closes all its cursors on close."""
    c1, c2 = connection.cursor(), connection.cursor()
    assert (
        len(connection._cursors) == 2
    ), "Invalid number of cursors stored in connection."

    await connection.aclose()
    assert connection.closed, "Connection was not closed on close."
    assert c1.closed, "Cursor was not closed on connection close."
    assert c2.closed, "Cursor was not closed on connection close."
    assert len(connection._cursors) == 0, "Cursors left in connection after close."
    await connection.aclose()


async def test_cursor_initialized(
    settings: Settings,
    mock_query: Callable,
    connection: Connection,
    python_query_data: List[List[ColType]],
) -> None:
    """Connection initialized its cursors properly."""
    mock_query()

    cursor = connection.cursor()
    assert cursor.connection == connection, "Invalid cursor connection attribute."
    assert cursor._client == connection._client, "Invalid cursor _client attribute"

    assert await cursor.execute("select*") == len(python_query_data)

    cursor.close()
    assert (
        cursor not in connection._cursors
    ), "Cursor wasn't removed from connection after close."


async def test_connect_empty_parameters():
    with raises(ConfigurationError):
        async with await connect(engine_name="engine_name"):
            pass


async def test_connect_engine_name(
    db_name: str,
    account_name: str,
    engine_name: str,
    auth: Auth,
    server: str,
    python_query_data: List[List[ColType]],
    httpx_mock: HTTPXMock,
    mock_query: Callable,
    system_engine_query_url: str,
    get_engine_url_not_running_callback: Callable,
    get_engine_url_invalid_db_callback: Callable,
    auth_url: str,
    check_credentials_callback: Callable,
    get_system_engine_url: str,
    get_system_engine_callback: Callable,
    get_engine_url_callback: Callable,
    account_id_url: str,
    account_id_callback: Callable,
):
    """connect properly handles engine_name"""

    httpx_mock.add_callback(check_credentials_callback, url=auth_url)
    httpx_mock.add_callback(get_system_engine_callback, url=get_system_engine_url)
    httpx_mock.add_callback(account_id_callback, url=account_id_url)

    mock_query()

    for callback, err_cls in (
        (get_engine_url_invalid_db_callback, InterfaceError),
        (get_engine_url_not_running_callback, EngineNotRunningError),
    ):
        httpx_mock.add_callback(callback, url=system_engine_query_url)
        with raises(err_cls):
            async with await connect(
                database=db_name,
                auth=auth,
                engine_name=engine_name,
                account_name=account_name,
                api_endpoint=server,
            ):
                pass

    httpx_mock.add_callback(get_engine_url_callback, url=system_engine_query_url)

    async with await connect(
        engine_name=engine_name,
        database=db_name,
        auth=auth,
        account_name=account_name,
        api_endpoint=server,
    ) as connection:
        assert await connection.cursor().execute("select*") == len(python_query_data)


async def test_connect_database(
    db_name: str,
    auth_url: str,
    server: str,
    auth: Auth,
    account_name: str,
    python_query_data: List[List[ColType]],
    httpx_mock: HTTPXMock,
    query_callback: str,
    check_credentials_callback: Callable,
    system_engine_query_url: str,
    system_engine_no_db_query_url: str,
    get_system_engine_url: str,
    get_system_engine_callback: Callable,
    account_id_url: str,
    account_id_callback: Callable,
):
    httpx_mock.add_callback(check_credentials_callback, url=auth_url)
    httpx_mock.add_callback(get_system_engine_callback, url=get_system_engine_url)
    httpx_mock.add_callback(query_callback, url=system_engine_no_db_query_url)
    httpx_mock.add_callback(account_id_callback, url=account_id_url)
    async with await connect(
        database=None,
        auth=auth,
        account_name=account_name,
        api_endpoint=server,
    ) as connection:
        await connection.cursor().execute("select*")

    httpx_mock.reset(True)
    httpx_mock.add_callback(get_system_engine_callback, url=get_system_engine_url)
    httpx_mock.add_callback(query_callback, url=system_engine_query_url)
    httpx_mock.add_callback(account_id_callback, url=account_id_url)

    async with await connect(
        database=db_name,
        auth=auth,
        account_name=account_name,
        api_endpoint=server,
    ) as connection:
        assert await connection.cursor().execute("select*") == len(python_query_data)


async def test_connection_commit(connection: Connection):
    # nothing happens
    connection.commit()

    await connection.aclose()
    with raises(ConnectionClosedError):
        connection.commit()


@mark.nofakefs
async def test_connection_token_caching(
    db_name: str,
    server: str,
    access_token: str,
    client_id: str,
    client_secret: str,
    engine_name: str,
    account_name: str,
    python_query_data: List[List[ColType]],
    mock_connection_flow: Callable,
    mock_query: Callable,
) -> None:
    mock_connection_flow()
    mock_query()

    with Patcher():
        async with await connect(
            database=db_name,
            auth=ClientCredentials(client_id, client_secret, use_token_cache=True),
            engine_name=engine_name,
            account_name=account_name,
            api_endpoint=server,
        ) as connection:
            assert await connection.cursor().execute("select*") == len(
                python_query_data
            )
        ts = TokenSecureStorage(username=client_id, password=client_secret)
        assert ts.get_cached_token() == access_token, "Invalid token value cached"

    # Do the same, but with use_token_cache=False
    with Patcher():
        async with await connect(
            database=db_name,
            auth=ClientCredentials(client_id, client_secret, use_token_cache=False),
            engine_name=engine_name,
            account_name=account_name,
            api_endpoint=server,
        ) as connection:
            assert await connection.cursor().execute("select*") == len(
                python_query_data
            )
        ts = TokenSecureStorage(username=client_id, password=client_secret)
        assert (
            ts.get_cached_token() is None
        ), "Token is cached even though caching is disabled"


async def test_connect_with_user_agent(
    engine_name: str,
    account_name: str,
    server: str,
    db_name: str,
    auth: Auth,
    access_token: str,
    httpx_mock: HTTPXMock,
    query_callback: Callable,
    query_url: str,
    mock_connection_flow: Callable,
) -> None:
    with patch("firebolt.async_db.connection.get_user_agent_header") as ut:
        ut.return_value = "MyConnector/1.0 DriverA/1.1"
        mock_connection_flow()
        httpx_mock.add_callback(
            query_callback,
            url=query_url,
            match_headers={"User-Agent": "MyConnector/1.0 DriverA/1.1"},
        )

        async with await connect(
            auth=auth,
            database=db_name,
            engine_name=engine_name,
            account_name=account_name,
            api_endpoint=server,
            additional_parameters={
                "user_clients": [("MyConnector", "1.0")],
                "user_drivers": [("DriverA", "1.1")],
            },
        ) as connection:
            await connection.cursor().execute("select*")
        ut.assert_called_with([("DriverA", "1.1")], [("MyConnector", "1.0")])


async def test_connect_no_user_agent(
    engine_name: str,
    account_name: str,
    server: str,
    db_name: str,
    auth: Auth,
    access_token: str,
    httpx_mock: HTTPXMock,
    query_callback: Callable,
    query_url: str,
    mock_connection_flow: Callable,
) -> None:
    with patch("firebolt.async_db.connection.get_user_agent_header") as ut:
        ut.return_value = "Python/3.0"
        mock_connection_flow()
        httpx_mock.add_callback(
            query_callback, url=query_url, match_headers={"User-Agent": "Python/3.0"}
        )

        async with await connect(
            auth=auth,
            database=db_name,
            engine_name=engine_name,
            account_name=account_name,
            api_endpoint=server,
        ) as connection:
            await connection.cursor().execute("select*")
        ut.assert_called_with([], [])
