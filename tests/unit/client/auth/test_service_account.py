import typing

import pytest
from httpx import StreamError, codes
from pytest_httpx import HTTPXMock
from pytest_mock import MockerFixture

from firebolt.client.auth import ServiceAccount
from firebolt.utils.exception import AuthenticationError
from tests.unit.util import execute_generator_requests


def test_auth_service_account(
    httpx_mock: HTTPXMock,
    mocker: MockerFixture,
    check_service_account_credentials_callback: typing.Callable,
    client_id,
    client_secret,
    test_token,
):
    """Auth can retrieve token and expiration values."""
    httpx_mock.add_callback(check_service_account_credentials_callback)

    mocker.patch("firebolt.client.auth.request_based.time", return_value=0)
    auth = ServiceAccount(client_id, client_secret)
    execute_generator_requests(auth.get_new_token_generator())
    assert auth.token == test_token, "invalid access token"
    assert auth._expires == 2**32, "invalid expiration value"


def test_auth_error_handling(httpx_mock: HTTPXMock):
    """Auth handles various errors properly."""
    for api_endpoint in ("https://host", "host"):
        auth = ServiceAccount("client_id", "client_secret", use_token_cache=False)

        # Internal httpx error
        def http_error(*args, **kwargs):
            raise StreamError("httpx")

        httpx_mock.add_callback(http_error)
        with pytest.raises(StreamError) as excinfo:
            execute_generator_requests(auth.get_new_token_generator(), api_endpoint)

        assert str(excinfo.value) == "httpx", "Invalid authentication error message"
        httpx_mock.reset(True)

        # HTTP error
        httpx_mock.add_response(status_code=codes.BAD_REQUEST)
        with pytest.raises(AuthenticationError) as excinfo:
            execute_generator_requests(auth.get_new_token_generator(), api_endpoint)

        errmsg = str(excinfo.value)
        assert "Bad Request" in errmsg, "Invalid authentication error message"
        httpx_mock.reset(True)

        # Firebolt api error
        httpx_mock.add_response(
            status_code=codes.OK, json={"error": "", "message": "firebolt"}
        )
        with pytest.raises(AuthenticationError) as excinfo:
            execute_generator_requests(auth.get_new_token_generator(), api_endpoint)

        httpx_mock.reset(True)
