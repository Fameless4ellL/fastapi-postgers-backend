from aiohttp import BasicAuth, ClientResponse, ClientSession, ClientTimeout
import requests
from typing import Any, Optional, Union, Dict
from eth_typing import URI
from web3._utils.http_session_manager import HTTPSessionManager
from web3._utils.empty import empty
from web3.providers.rpc import HTTPProvider, AsyncHTTPProvider
from web3._utils.http import (
    DEFAULT_HTTP_TIMEOUT,
)
from requests_auth_aws_sigv4 import AWSSigV4
from settings import aws


aws_auth = AWSSigV4(
    'managedblockchain',
    aws_access_key_id=aws.access_key,
    aws_secret_access_key=aws.secret_key,
    region=aws.region
)


class ModHTTPSessionManager(HTTPSessionManager):
    def get_response_from_post_request(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> requests.Response:
        kwargs.setdefault("timeout", DEFAULT_HTTP_TIMEOUT)
        session = self.cache_and_return_session(
            endpoint_uri, request_timeout=kwargs["timeout"]
        )
        return session.post(
            endpoint_uri,
            *args,
            **kwargs,
            auth=aws_auth
        )

    async def async_get_response_from_post_request(
        self, endpoint_uri: URI, *args: Any, **kwargs: Any
    ) -> ClientResponse:
        kwargs.setdefault("timeout", ClientTimeout(DEFAULT_HTTP_TIMEOUT))
        session = await self.async_cache_and_return_session(
            endpoint_uri, request_timeout=kwargs["timeout"]
        )

        response = await session.post(
            endpoint_uri,
            *args,
            **kwargs,
            auth=aws_auth
        )
        return response

    async def async_make_post_request(
        self,
        endpoint_uri: URI,
        data: Union[bytes, Dict[str, Any]],
        **kwargs: Any
    ) -> bytes:
        response = await self.async_get_response_from_post_request(
            endpoint_uri, data=data, **kwargs
        )
        response.raise_for_status()
        return await response.read()


class AWSHTTPProvider(HTTPProvider):
    def __init__(
        self,
        endpoint_uri: Optional[Union[URI, str]] = None,
        request_kwargs: Optional[Any] = None,
        session: Optional[Any] = None,
        exception_retry_configuration: Optional[Any] = empty,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._request_session_manager = ModHTTPSessionManager()

        if endpoint_uri is None:
            self.endpoint_uri = (
                self._request_session_manager.get_default_http_endpoint()
            )
        else:
            self.endpoint_uri = URI(endpoint_uri)

        self._request_kwargs = request_kwargs or {}
        self._exception_retry_configuration = exception_retry_configuration

        if session:
            self._request_session_manager.cache_and_return_session(
                self.endpoint_uri, session
            )


class AWSAsyncHTTPProvider(AsyncHTTPProvider):
    # TODO: add async version of AWSHTTPProvider
    def __init__(
        self,
        endpoint_uri: Optional[Union[URI, str]] = None,
        request_kwargs: Optional[Any] = None,
        exception_retry_configuration: Optional[Any] = empty,
        **kwargs: Any,
    ) -> None:
        self._request_session_manager = ModHTTPSessionManager()

        if endpoint_uri is None:
            self.endpoint_uri = (
                self._request_session_manager.get_default_http_endpoint()
            )
        else:
            self.endpoint_uri = URI(endpoint_uri)

        self._request_kwargs = request_kwargs or {}
        self._exception_retry_configuration = exception_retry_configuration

        super().__init__(**kwargs)
