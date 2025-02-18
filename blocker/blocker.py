import asyncio
import datetime
import logging
from abc import ABC, abstractmethod
import time
from typing import Tuple, List, Dict, Any, Iterable

from web3 import AsyncWeb3
from web3.datastructures import AttributeDict
from web3.exceptions import BlockNotFound
from eth_abi.codec import ABICodec

from web3._utils.filters import construct_event_filter_params
from web3._utils.events import get_event_data

logger = logging.getLogger(__name__)


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
        block_when: datetime.datetime,
        event: AttributeDict
    ) -> object:
        pass

    @abstractmethod
    def delete_data(self, since_block: int) -> int:
        pass


class EventScanner:
    def __init__(
        self,
        w3: AsyncWeb3,
        state: EventScannerState,
        events: List,
        filters: Dict[str, Any],
        max_chunk_scan_size: int = 10000,
        max_request_retries: int = 30,
        request_retry_seconds: float = 3.0
    ):
        self.logger = logger
        self.w3 = w3
        self.state = state
        self.events = events
        self.filters = filters

        self.min_scan_chunk_size = 10
        self.max_scan_chunk_size = max_chunk_scan_size
        self.max_request_retries = max_request_retries
        self.request_retry_seconds = request_retry_seconds

        self.chunk_size_decrease = 0.5
        self.chunk_size_increase = 2.0

    async def get_block_timestamp(self, block_num) -> datetime.datetime:
        try:
            block_info = await self.w3.eth.get_block(block_num)
        except BlockNotFound:
            return None
        last_time = block_info["timestamp"]
        return datetime.datetime.fromtimestamp(last_time)

    def get_suggested_scan_start_block(self):
        end_block = self.get_last_scanned_block()
        if end_block:
            return max(1, end_block - self.NUM_BLOCKS_RESCAN_FOR_FORKS)
        return 1

    async def get_suggested_scan_end_block(self):
        return await self.w3.eth.block_number - 1

    def get_last_scanned_block(self) -> int:
        return self.state.get_last_scanned_block()

    def delete_potentially_forked_block_data(self, after_block: int):
        self.state.delete_data(after_block)

    async def scan_chunk(
        self,
        start_block,
        end_block
    ) -> Tuple[int, datetime.datetime, list]:
        block_timestamps = {}
        get_block_timestamp = self.get_block_timestamp

        async def get_block_when(block_num):
            if block_num not in block_timestamps:
                block_timestamps[block_num] = await get_block_timestamp(block_num)
            return block_timestamps[block_num]

        all_processed = []

        for event_type in self.events:
            async def _fetch_events(_start_block, _end_block):
                return await _fetch_events_for_all_contracts(
                    self.w3,
                    event_type,
                    self.filters,
                    from_block=_start_block,
                    to_block=_end_block
                )

            end_block, events = await _retry_web3_call(
                _fetch_events,
                start_block=start_block,
                end_block=end_block,
                retries=self.max_request_retries,
                delay=self.request_retry_seconds)

            for evt in events:
                idx = evt["logIndex"]
                assert idx is not None, "Somehow tried to scan a pending block"
                block_number = evt["blockNumber"]
                block_when = await get_block_when(block_number)
                logger.debug(f"Processing event {evt['event']}, block: {evt['blockNumber']} count: {evt['blockNumber']}")
                processed = self.state.process_event(block_when, evt)
                all_processed.append(processed)

        end_block_timestamp = await get_block_when(end_block)
        return end_block, end_block_timestamp, all_processed

    def estimate_next_chunk_size(self, current_chuck_size: int, event_found_count: int):
        if event_found_count > 0:
            current_chuck_size = self.min_scan_chunk_size
        else:
            current_chuck_size *= self.chunk_size_increase

        current_chuck_size = max(self.min_scan_chunk_size, current_chuck_size)
        current_chuck_size = min(self.max_scan_chunk_size, current_chuck_size)
        return int(current_chuck_size)

    async def scan(
        self,
        start_block,
        end_block,
        start_chunk_size=20
    ) -> Tuple[list, int]:
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
                f"Scanning blocks: {current_block} - {estimated_end_block}, chunk size {chunk_size}, last chunk scan took {last_scan_duration}, last logs found {last_logs_found}"
            )

            start = time.time()
            actual_end_block, _, new_entries = await self.scan_chunk(current_block, estimated_end_block)
            current_end = actual_end_block
            last_scan_duration = time.time() - start
            all_processed += new_entries
            chunk_size = self.estimate_next_chunk_size(chunk_size, len(new_entries))
            current_block = current_end + 1
            total_chunks_scanned += 1
            self.state.end_chunk(current_end)

        return all_processed, total_chunks_scanned


async def _retry_web3_call(func, start_block, end_block, retries, delay) -> Tuple[int, list]:
    for i in range(retries):
        try:
            return end_block, await func(start_block, end_block)
        except Exception as e:
            if i < retries - 1:
                logger.warning(
                    f"Retrying events for block range {start_block} - {end_block} ({end_block-start_block}) failed with {e} , retrying in {delay} seconds")
                end_block = start_block + ((end_block - start_block) // 2)
                await asyncio.sleep(delay)
                continue
            else:
                logger.warning("Out of retries")
                raise


async def _fetch_events_for_all_contracts(
    w3,
    event,
    argument_filters: Dict[str, Any],
    from_block: int,
    to_block: int
) -> Iterable:
    if from_block is None:
        raise Web3TypeError("Missing mandatory keyword argument to get_logs: from_block")

    abi = event._get_event_abi()
    codec: ABICodec = w3.codec

    data_filter_set, event_filter_params = construct_event_filter_params(
        abi,
        codec,
        address=argument_filters.get("address"),
        argument_filters=argument_filters,
        from_block=from_block,
        to_block=to_block
    )

    logger.debug(
        f"Querying eth_getLogs with the following parameters: {event_filter_params}"
    )
    logs = await w3.eth.get_logs(event_filter_params)
    all_events = []
    for log in logs:
        evt = get_event_data(codec, abi, log)
        all_events.append(evt)
    return all_events


if __name__ == "__main__":
    import sys
    import json
    from web3.providers import AsyncHTTPProvider

    class JSONifiedState(EventScannerState):
        def __init__(self):
            self.state = None
            self.fname = "state.json"
            self.last_save = 0

        def reset(self):
            self.state = {
                "last_scanned_block": 0,
                "blocks": {},
            }

        def restore(self):
            try:
                self.state = json.load(open(self.fname, "rt"))
                print(f"Restored the state, previously {self.state['last_scanned_block']} blocks have been scanned")
            except (IOError, json.decoder.JSONDecodeError):
                print("State starting from scratch")
                self.reset()

        def save(self):
            with open(self.fname, "wt") as f:
                json.dump(self.state, f)
            self.last_save = time.time()

        def get_last_scanned_block(self):
            return self.state["last_scanned_block"]

        def delete_data(self, since_block):
            for block_num in range(since_block, self.get_last_scanned_block()):
                if block_num in self.state["blocks"]:
                    del self.state["blocks"][block_num]

        def start_chunk(self, block_number, chunk_size):
            pass

        def end_chunk(self, block_number):
            self.state["last_scanned_block"] = block_number
            if time.time() - self.last_save > 60:
                self.save()

        def process_event(
            self,
            block_when: datetime.datetime,
            event: AttributeDict
        ) -> str:
            log_index = event.logIndex
            txhash = event.transactionHash.hex()
            block_number = event.blockNumber
            args = event["args"]
            transfer = {
                "from": args["from"],
                "to": args.to,
                "value": args.value,
                "timestamp": block_when.isoformat(),
            }
            if block_number not in self.state["blocks"]:
                self.state["blocks"][block_number] = {}
            block = self.state["blocks"][block_number]
            if txhash not in block:
                self.state["blocks"][block_number][txhash] = {}
            self.state["blocks"][block_number][txhash][log_index] = transfer
            return f"{block_number}-{txhash}-{log_index}"

    async def run():
        if len(sys.argv) < 2:
            print("Usage: eventscanner.py http://your-node-url")
            sys.exit(1)

        api_url = sys.argv[1]
        logging.basicConfig(level=logging.INFO)
        provider = AsyncHTTPProvider(api_url)
        w3 = AsyncWeb3(provider)

        state = JSONifiedState()
        state.restore()

        RCC_ADDRESS = "0x7169D38820dfd117C3FA1f22a697dBA58d90BA06"
        ERC20_ABI = [{"constant":True,"inputs":[],"name":"name","outputs":[{"name":"","type":"string"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"name":"_upgradedAddress","type":"address"}],"name":"deprecate","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":False,"inputs":[{"name":"_spender","type":"address"},{"name":"_value","type":"uint256"}],"name":"approve","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"deprecated","outputs":[{"name":"","type":"bool"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"name":"_evilUser","type":"address"}],"name":"addBlackList","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"totalSupply","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"name":"_from","type":"address"},{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transferFrom","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"upgradedAddress","outputs":[{"name":"","type":"address"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[{"name":"","type":"address"}],"name":"balances","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"maximumFee","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"_totalSupply","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[],"name":"unpause","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":False,"inputs":[{"name":"receiver","type":"address"},{"name":"amount","type":"uint256"}],"name":"_mint","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[{"name":"_maker","type":"address"}],"name":"getBlackListStatus","outputs":[{"name":"","type":"bool"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[{"name":"","type":"address"},{"name":"","type":"address"}],"name":"allowed","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"paused","outputs":[{"name":"","type":"bool"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[{"name":"who","type":"address"}],"name":"balanceOf","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[],"name":"pause","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"getOwner","outputs":[{"name":"","type":"address"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"owner","outputs":[{"name":"","type":"address"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"symbol","outputs":[{"name":"","type":"string"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"name":"_to","type":"address"},{"name":"_value","type":"uint256"}],"name":"transfer","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":False,"inputs":[{"name":"newBasisPoints","type":"uint256"},{"name":"newMaxFee","type":"uint256"}],"name":"setParams","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":False,"inputs":[{"name":"amount","type":"uint256"}],"name":"issue","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":False,"inputs":[{"name":"amount","type":"uint256"}],"name":"redeem","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[{"name":"_owner","type":"address"},{"name":"_spender","type":"address"}],"name":"allowance","outputs":[{"name":"remaining","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[],"name":"basisPointsRate","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":True,"inputs":[{"name":"","type":"address"}],"name":"isBlackListed","outputs":[{"name":"","type":"bool"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"name":"_clearedUser","type":"address"}],"name":"removeBlackList","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":True,"inputs":[],"name":"MAX_UINT","outputs":[{"name":"","type":"uint256"}],"payable":False,"stateMutability":"view","type":"function"},{"constant":False,"inputs":[{"name":"newOwner","type":"address"}],"name":"transferOwnership","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":False,"inputs":[{"name":"_blackListedUser","type":"address"}],"name":"destroyBlackFunds","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"constant":False,"inputs":[{"name":"amount","type":"uint256"}],"name":"_giveMeATokens","outputs":[],"payable":False,"stateMutability":"nonpayable","type":"function"},{"inputs":[{"name":"_initialSupply","type":"uint256"},{"name":"_name","type":"string"},{"name":"_symbol","type":"string"},{"name":"_decimals","type":"uint256"}],"payable":False,"stateMutability":"nonpayable","type":"constructor"},{"anonymous":False,"inputs":[{"indexed":False,"name":"amount","type":"uint256"}],"name":"Issue","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"name":"amount","type":"uint256"}],"name":"Redeem","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"name":"newAddress","type":"address"}],"name":"Deprecate","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"name":"feeBasisPoints","type":"uint256"},{"indexed":False,"name":"maxFee","type":"uint256"}],"name":"Params","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"name":"_blackListedUser","type":"address"},{"indexed":False,"name":"_balance","type":"uint256"}],"name":"DestroyedBlackFunds","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"name":"_user","type":"address"}],"name":"AddedBlackList","type":"event"},{"anonymous":False,"inputs":[{"indexed":False,"name":"_user","type":"address"}],"name":"RemovedBlackList","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"name":"owner","type":"address"},{"indexed":True,"name":"spender","type":"address"},{"indexed":False,"name":"value","type":"uint256"}],"name":"Approval","type":"event"},{"anonymous":False,"inputs":[{"indexed":True,"name":"from","type":"address"},{"indexed":True,"name":"to","type":"address"},{"indexed":False,"name":"value","type":"uint256"}],"name":"Transfer","type":"event"},{"anonymous":False,"inputs":[],"name":"Pause","type":"event"},{"anonymous":False,"inputs":[],"name":"Unpause","type":"event"}]

        ERC20 = w3.eth.contract(address=RCC_ADDRESS, abi=ERC20_ABI)
        
        scanner = EventScanner(
            w3=w3,
            state=state,
            events=[ERC20.events.Transfer],
            filters={"address": RCC_ADDRESS},
            max_chunk_scan_size=10000
        )

        chain_reorg_safety_blocks = 10
        scanner.delete_potentially_forked_block_data(state.get_last_scanned_block() - chain_reorg_safety_blocks)
        start_block = max(state.get_last_scanned_block() - chain_reorg_safety_blocks, 0)
        end_block = await scanner.get_suggested_scan_end_block()

        print(f"Scanning events from blocks {start_block} - {end_block}")

        while True:
            start = time.time()
            result, total_chunks_scanned = await scanner.scan(start_block, end_block)

            state.save()
            duration = time.time() - start
            print(f"Scanned total {len(result)} Transfer events, in {duration} seconds, total {total_chunks_scanned} chunk scans performed")

            await asyncio.sleep(5)  # Wait for 60 seconds before scanning again

    asyncio.run(run())
