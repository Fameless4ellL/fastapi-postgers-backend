import json
from tronpy import Tron
from tronpy.keys import PrivateKey, to_base58check_address
from eth_account import Account
from aiohttp import ClientResponse, ClientTimeout
import requests
from typing import Any, Optional, Union, Dict
from eth_typing import URI
from web3 import Web3, middleware
from web3._utils.http_session_manager import HTTPSessionManager
from web3._utils.empty import empty
from web3.providers.rpc import HTTPProvider, AsyncHTTPProvider
from web3._utils.http import (
    DEFAULT_HTTP_TIMEOUT,
)
from aiohttp import client_exceptions
from requests_auth_aws_sigv4 import AWSSigV4
from tronpy.providers import HTTPProvider as TronHTTPProvider
from src.models.other import Currency
from src.globals import redis
from settings import settings, aws


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


def get_w3(
    url: int,
    private_key: str = settings.private_key
) -> Union[Web3, bool]:
    try:
        w3 = Web3(AWSHTTPProvider(url))

        if not w3.is_connected():
            return False
    except client_exceptions.ClientError:
        return False

    acct = w3.eth.account.from_key(private_key)

    w3.middleware_onion.inject(
        middleware.SignAndSendRawMiddlewareBuilder.build(acct),
        layer=0
    )
    w3.eth.default_account = acct.address

    return w3


def transfer(
    currency: Currency,
    private_key: str,
    amount: float,
    address: str,
    tx: str = ""
) -> Union[str, bool]:
    try:
        if currency.network.symbol.lower() == "tron":
            return transfer_trc20(currency, private_key, amount, address, tx)

        w3 = get_w3(
            currency.network.rpc_url,
            private_key
        )

        if not w3:
            return False

        if tx:
            tx = w3.eth.get_transaction_receipt(tx)
            if tx.status != 1:
                return "", "Transaction failed"

            return tx, "success"

        abi = redis.get("abi")

        contract = w3.eth.contract(
            address=w3.to_checksum_address(address),
            abi=json.loads(abi)
        )

        amount = int(amount * 10 ** currency.decimals)
        _hash = contract.functions.transfer(
            w3.to_checksum_address(address),
            amount
        ).transact()

        tx = w3.eth.get_transaction_receipt(_hash)

        if tx.status != 1:
            return "", "Transaction failed"
    except Exception as e:
        return "", str(e)
    return _hash, "success"


def transfer_trc20(
    currency: Currency,
    private_key: str,
    amount: float,
    address: str,
    tx: str = ""
) -> Union[str, bool]:
    try:
        provider = TronHTTPProvider(currency.network.rpc_url)
        client = Tron(provider=provider)

        if tx:
            txn = client.get_transaction(tx)
            if txn["ret"][0]["contractRet"] != "SUCCESS":
                return "", "Transaction failed"

            return tx, "success"

        contract = client.get_contract(
            to_base58check_address(currency.address)
        )

        priv_key = PrivateKey(bytes.fromhex(private_key))
        acct = Account.from_key(private_key)

        amount = int(amount * 10 ** currency.decimals)
        address = to_base58check_address(address)
        txn = (
            contract.functions.transfer(address, amount)
            .with_owner(to_base58check_address(acct.address))
            .fee_limit(5_000_000)
            .build()
            .sign(priv_key)
        )

        txn = txn.broadcast()
        if txn["result"]:
            return txn["txid"], "success"
        else:
            return "", "failed"
    except Exception as e:
        return "", str(e)
