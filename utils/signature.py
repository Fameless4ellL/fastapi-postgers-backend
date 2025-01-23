from datetime import datetime, timedelta
import hashlib
import base64
import hmac

from operator import itemgetter
import traceback
from typing import Optional
from Crypto.PublicKey import RSA
from Crypto.Cipher import AES, PKCS1_OAEP
from schemes.tg import WidgetLogin
from jose import JWTError, jwt
from passlib.context import CryptContext
from settings import settings


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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


def decrypt_data(
    data: str,
    data_secret: str,
    data_hash: str
):
    """
    When the user confirms your request by pressing the "Authorize" button,
    the Bot API sends an Update with the field passport_data to the bot that
    contains encrypted Telegram Passport data.

    see: https://core.telegram.org/passport#receiving-information
    """
    # Decrypt data
    data_encrypted = base64.b64decode(data)
    data_secret = base64.b64decode(data_secret)
    data_hash = base64.b64decode(data_hash)

    data_secret_hash = hashlib.sha512(data_secret + data_hash).digest()

    data_key = data_secret_hash[:32]
    data_iv = data_secret_hash[32:48]

    # AES256-CBC with this data_key and data_iv to decrypt the data
    # (the data field in EncryptedPassportElement).
    cipher = AES.new(data_key, AES.MODE_CBC, iv=data_iv)
    data_decrypted = cipher.decrypt(data_encrypted)

    # Check decrypted data with hash provided
    data_decrypted_hash = hashlib.sha256(data_decrypted).digest()
    print(data_decrypted_hash)
    if hashlib.sha256(data_decrypted).digest() != data_decrypted_hash:
        raise Exception('HASH_INVALID')

    # Remove padding
    padding_len = data_decrypted[0]
    data_decrypted = data_decrypted[padding_len:]

    return data_decrypted


def decrypt_credential_secret(
    credential_secret: str
):
    # Check types and decode from base64
    try:
        if not isinstance(credential_secret, bytes):
            credential_secret = str.encode(credential_secret)
        credential_secret = base64.decodebytes(credential_secret)
        # Import key and decrypt secret
        private_key = RSA.import_key(open("./private.key").read())
        cipher_rsa = PKCS1_OAEP.new(private_key)
        decrypted_secret = cipher_rsa.decrypt(credential_secret)
    except (ValueError, IndexError, TypeError):
        traceback.print_exc()
        return "", "INVALID_SECRET"
    finally:
        return base64.encodebytes(decrypted_secret), ""


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm="HS256")

    return encoded_jwt


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except JWTError:
        return None
