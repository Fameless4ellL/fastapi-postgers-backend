from src.models import get_sync_db
from src.models import Network, Currency


def default_network():
    db = next(get_sync_db())

    net = db.query(Network).filter(Network.symbol == "ETH").first()

    if net is None:
        # create
        net = Network(
            chain_id=1,
            name="Ethereum",
            symbol="ETH",
            rpc_url="https://eth.llamarpc.com",
            explorer_url="https://sepolia.etherscan.io/",
        )
        db.add(net)

    cur = db.query(Currency).filter(
        Currency.code == "USDT",
        Currency.network_id == net.id
    ).first()

    if cur is None:
        # create
        cur = Currency(
            name="Tether",
            code="USDT",
            network_id=net.id,
            decimals=6,
            address="0x7169D38820dfd117C3FA1f22a697dBA58d90BA06".lower(),
        )
        db.add(cur)

    db.commit()