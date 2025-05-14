import asyncio
import datetime
import os
import requests
import logging
import time

from abc import ABC, abstractmethod

from typing import Tuple, List, Dict, Any, Iterable

from web3 import Web3, exceptions
from web3.datastructures import AttributeDict
from eth_abi.codec import ABICodec

from redis_ import redis_m
from aiohttp.client_exceptions import ServerDisconnectedError

from web3._utils.filters import construct_event_filter_params
from web3._utils.events import get_event_data

from utils import AWSHTTPProvider

logger = logging.getLogger("BLOCKER")

ABI = """[
    {
        "anonymous": false,
        "inputs": [
            {
                "indexed": true,
                "name": "from",
                "type": "address"
            },
            {
                "indexed": true,
                "name": "to",
                "type": "address"
            },
            {
                "indexed": false,
                "name": "value",
                "type": "uint256"
            }
        ],
        "name": "Transfer",
        "type": "event"
    }
]
"""
CRON_KEY = os.getenv("CRON_KEY", "thisisatest")

class EventScannerState(ABC):
    @abstractmethod
    def get_last_scanned_block(self) -> int:
        pass

    @abstractmethod
    def start_chunk(self, block_number: int):
        pass

    @abstractmethod
    def end_chunk(self, block_number: int):
        pass

    @abstractmethod
    def process_event(
        self,
        # block_when: datetime.datetime,
        event: AttributeDict
    ) -> object:
        pass

    @abstractmethod
    def delete_data(self, since_block: int) -> int:
        pass


class JSONifiedState(EventScannerState):
    def __init__(self, network="eth"):
        self.state = None
        self.network = network
        self.last_save = 0

    def reset(self):
        redis_m.set_state(self.network, 0)
        self.state = 0

    def restore(self):
        try:
            self.state = int(redis_m.get_state(self.network))
            logger.info(
                f"Restored the state,"
                f"previously {self.state['last_scanned_block']}"
                "blocks have been scanned"
            )
        except Exception:
            logger.info("State starting from scratch")
            self.reset()

    def save(self):
        redis_m.set_state(self.network, self.state)
        self.last_save = time.time()

    def get_last_scanned_block(self):
        return self.state

    def delete_data(self, since_block):
        pass
        # for block_num in range(since_block, self.get_last_scanned_block()):
        #     if block_num in self.state["blocks"]:
        #         del self.state["blocks"][block_num]

    def start_chunk(self, block_number, chunk_size):
        pass

    def end_chunk(self, block_number):
        self.state = block_number
        if time.time() - self.last_save > 60:
            self.save()

    def process_event(
        self,
        event: AttributeDict,
        contract_address: str
    ) -> str:
        log_index = event.logIndex
        txhash = event.transactionHash.hex()
        block_number = event.blockNumber
        args = event["args"]

        if args.to in redis_m.get_wallets():
            transfer = {
                "txhash": txhash,
                "_from": args["from"],
                "to": args.to,
                "contract": contract_address,
                "value": args.value,
            }
            logger.info(f"DEPOSIT: {transfer}")

            requests.post(
                "http://api:8000/v1/cron/api/transfer/",
                params={"key": "thisisatest"},
                json=transfer
            )

        return f"{block_number}-{txhash}-{log_index}"


class EventScanner:
    def __init__(
        self,
        w3: Web3,
        state: EventScannerState,
        contracts: List[Dict[str, Any]],
        max_chunk_scan_size: int = 10000,
        max_request_retries: int = 30,
        request_retry_seconds: float = 3.0
    ):
        self.logger = logger
        self.w3 = w3
        self.state = state
        self.contracts = contracts

        self.min_scan_chunk_size = 10
        self.max_scan_chunk_size = max_chunk_scan_size
        self.max_request_retries = max_request_retries
        self.request_retry_seconds = request_retry_seconds

        self.chunk_size_decrease = 0.5
        self.chunk_size_increase = 2.0

    def get_suggested_scan_start_block(self):
        end_block = self.get_last_scanned_block()
        if end_block:
            return max(1, end_block - self.NUM_BLOCKS_RESCAN_FOR_FORKS)
        return 1

    def get_suggested_scan_end_block(self):
        return self.w3.eth.block_number - 1

    def get_last_scanned_block(self) -> int:
        return self.state.get_last_scanned_block()

    def delete_potentially_forked_block_data(self, after_block: int):
        self.state.delete_data(after_block)

    def scan_chunk(
        self,
        start_block,
        end_block
    ) -> Tuple[int, list]:

        all_processed = []

        for contract in self.contracts:
            event_type = contract["event"]
            filters = contract["filters"]

            def _fetch_events(_start_block, _end_block):
                return _fetch_events_for_all_contracts(
                    self.w3,
                    event_type,
                    filters,
                    from_block=_start_block,
                    to_block=_end_block
                )

            end_block, events = _retry_web3_call(
                _fetch_events,
                start_block=start_block,
                end_block=end_block,
                retries=self.max_request_retries,
                delay=self.request_retry_seconds
            )

            for evt in events:
                idx = evt["logIndex"]
                assert idx is not None, "Somehow tried to scan a pending block"

                logger.debug(
                    f"Processing event {evt['event']},"
                    f"block: {evt['blockNumber']}"
                    f"count: {evt['blockNumber']}"
                )

                processed = self.state.process_event(evt, filters.get("address"))
                all_processed.append(processed)

        return end_block, all_processed

    def estimate_next_chunk_size(
        self,
        current_chuck_size: int,
        event_found_count: int
    ):
        if event_found_count > 0:
            current_chuck_size = self.min_scan_chunk_size
        else:
            current_chuck_size *= self.chunk_size_increase

        current_chuck_size = max(self.min_scan_chunk_size, current_chuck_size)
        current_chuck_size = min(self.max_scan_chunk_size, current_chuck_size)
        return int(current_chuck_size)

    def scan(
        self,
        start_block,
        end_block,
        start_chunk_size=20
    ) -> Tuple[list, int]:
        """
        :param start_block: The first block included in the scan
        :param end_block: The last block included in the scan
        :param start_chunk_size: How many blocks we try to fetch over JSON-RPC
        """
        assert start_block <= end_block

        current_block = start_block
        chunk_size = start_chunk_size
        last_scan_duration = last_logs_found = 0
        total_chunks_scanned = 0
        all_processed = []

        while current_block <= end_block:
            self.state.start_chunk(current_block, chunk_size)
            estimated_end_block = min(current_block + chunk_size, end_block)
            logger.debug(
                f"Scanning blocks: {current_block} - {estimated_end_block},"
                f"chunk size {chunk_size},"
                f"last chunk scan took {last_scan_duration},"
                f"last logs found {last_logs_found}"
            )

            start = time.time()
            actual_end_block, new_entries = self.scan_chunk(
                current_block,
                estimated_end_block
            )
            current_end = actual_end_block
            last_scan_duration = time.time() - start
            all_processed += new_entries
            chunk_size = self.estimate_next_chunk_size(
                chunk_size,
                len(new_entries)
            )
            current_block = current_end + 1
            total_chunks_scanned += 1
            self.state.end_chunk(current_end)

        return all_processed, total_chunks_scanned


def _retry_web3_call(
    func,
    start_block,
    end_block,
    retries,
    delay
) -> Tuple[int, list]:
    """
    :param func: A callable that triggers Ethereum JSON-RPC
    :param start_block: The initial start block of the block range
    :param end_block: The initial start block of the block range
    :param retries: How many times we retry
    :param delay: Time to sleep between retries
    """
    for i in range(retries):
        try:
            return end_block, func(start_block, end_block)
        except Exception as e:
            if i < retries - 1:
                logger.warning(
                    f"Retrying events for block range {start_block} - {end_block} "
                    f"({end_block-start_block}) failed with {e} , retrying in {delay} seconds"
                )
                end_block = start_block + ((end_block - start_block) // 2)
                time.sleep(delay)
                continue

            logger.warning("Out of retries")
            raise


def _fetch_events_for_all_contracts(
    w3,
    event,
    argument_filters: Dict[str, Any],
    from_block: int,
    to_block: int
) -> Iterable:
    if from_block is None:
        raise exceptions.Web3TypeError(
            "Missing mandatory keyword argument to get_logs: from_block"
        )

    abi = event._get_event_abi()
    codec: ABICodec = w3.codec

    _, event_filter_params = construct_event_filter_params(
        abi,
        codec,
        address=argument_filters.get("address"),
        argument_filters=argument_filters,
        from_block=from_block,
        to_block=to_block
    )

    logger.debug(
        "Querying eth_getLogs with the following parameters: "
        f"{event_filter_params}"
    )
    logs = w3.eth.get_logs(event_filter_params)
    all_events = []
    for log in logs:
        evt = get_event_data(codec, abi, log)
        all_events.append(evt)
    return all_events


async def main() -> None:
    logger.info(f"BLOCKER START: {datetime.datetime.now()}")

    queue = asyncio.Queue()

    await asyncio.gather(
        check_net_status(queue),
        consumer(queue)
    )


async def check_net_status(queue: asyncio.Queue) -> None:
    redis_networks = redis_m.get_networks()

    for node, label in redis_networks:
        await queue.put(
            run(node, label)
        )


async def consumer(queue: asyncio.Queue):
    while True:
        await asyncio.sleep(1)

        if queue.empty():
            continue

        task = await queue.get()

        if task:
            logger.info(f"Executing task: {task}")
            asyncio.create_task(task)


async def run(node: str, network: str) -> None:
    logging.basicConfig(level=logging.INFO)
    provider = AWSHTTPProvider(node, exception_retry_configuration=None)
    w3 = Web3(provider)

    state = JSONifiedState(network=network)
    state.restore()

    if state.state == 0:
        state.state = w3.eth.block_number - 1

    ERC20_TOKENS = redis_m.get_tokens(network)
    contracts = []

    for address in ERC20_TOKENS:
        contract = w3.eth.contract(address=address, abi=ABI)
        contracts.append(
            {"event": contract.events.Transfer, "filters": {"address": w3.to_checksum_address(address)}}
        )

    scanner = EventScanner(
        w3=w3,
        state=state,
        contracts=contracts,
        max_chunk_scan_size=10000
    )

    chain_reorg_safety_blocks = 10
    while True:
        try:
            scanner.delete_potentially_forked_block_data(
                state.get_last_scanned_block() - chain_reorg_safety_blocks
            )
            # NOTE blocks cannot go negative
            start_block = max(
                state.get_last_scanned_block() - chain_reorg_safety_blocks, 0
            )
            end_block = scanner.get_suggested_scan_end_block()

            logger.info(f"{network.upper()}: Scanning events from blocks {start_block} - {end_block}")

            start = time.time()
            result, total_chunks_scanned = scanner.scan(
                start_block, end_block
            )

            state.save()
            duration = time.time() - start

            msg = (
                f"{network.upper()}: Scanned total {len(result)} events, "
                f"in {duration} seconds, total {total_chunks_scanned} "
                "chunk scans performed"
            )

            logger.info(msg)

        except ServerDisconnectedError as e:
            logger.error(f"Server disconnected: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Unexpected error: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)
        else:
            await asyncio.sleep(5)
    return None


if __name__ == "__main__":
    asyncio.run(main())
