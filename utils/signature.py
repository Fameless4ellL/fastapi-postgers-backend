import hashlib
import hmac
from operator import itemgetter

from schemes.tg import WidgetLogin


class TgAuth:
    def __init__(self, item: WidgetLogin, secret: bytes):
        self.hash = item.hash
        self.secret_key = hashlib.sha256(secret).digest()
        self.data = item.model_dump(exclude={"hash"})

    def data_to_string(self) -> str:
        return "\n".join(f"{k}={v}" for k, v in sorted(
            self.data.items(),
            key=itemgetter(0))
        )

    def calc_hash(self) -> str:
        msg = bytearray(self.data_to_string(), "utf-8")
        res = hmac.new(
            self.secret_key,
            msg=msg,
            digestmod=hashlib.sha256
        ).hexdigest()
        return res

    def check_hash(self) -> bool:
        return self.calc_hash() == self.hash
