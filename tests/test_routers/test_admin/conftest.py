from fastapi.testclient import TestClient
import pytest
from sqlalchemy.orm.session import Session

from models import InstaBingo, Currency
from models.user import Role, User, Kyc, ReferralLink
from globals import redis


PASSWORD = "test_password"


@pytest.fixture
def tear_down(db: Session):
    redis.set("SMS:testclient", 123456)
    yield
    redis.delete("SMS:testclient")

    db.query(User).filter(
        User.username == "testuser"
    ).delete()
    db.commit()


@pytest.fixture
def admin(
    db: Session,
    user: User,
):
    user.role = Role.SUPER_ADMIN.value
    db.commit()
    yield user


@pytest.fixture
def admin_token(
    api: TestClient,
    admin: User,
):
    response = api.post(
        "/v1/admin/login",
        json={
            "login": admin.username,
            "password": PASSWORD,
        }
    )
    assert response.status_code == 200
    assert "access_token" in response.json()
    yield response.json()["access_token"]


@pytest.fixture
def kyc(
    db: Session,
):
    """
    Создание KYC.
    """
    kyc = Kyc(
        country="USA",
    )
    db.add(kyc)
    db.commit()
    db.refresh(kyc)
    yield kyc
    db.query(Kyc).delete()


@pytest.fixture
def instabingo(
    db: Session,
    currency: Currency,
):
    """
    Создание InstaBingo.
    """
    instabingo = InstaBingo(
        country="KAZ",
        currency_id=currency.id
    )
    db.add(instabingo)
    db.commit()
    db.refresh(instabingo)
    yield instabingo

    try:
        db.query(InstaBingo).filter(
            InstaBingo.id == instabingo.id
        ).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)


@pytest.fixture
def referral(
    db: Session,
    admin: User,
):
    """
    Создание реферальной ссылки.
    """
    referral = ReferralLink(
        name="test_referral",
        comment="test_comment",
        link="test_link",
        generated_by=admin.id,
    )
    db.add(referral)
    db.commit()
    db.refresh(referral)
    yield referral

    try:
        db.query(ReferralLink).filter(
            ReferralLink.id == referral.id
        ).delete()
        db.commit()
    except Exception as e:
        db.rollback()
        print(e)


@pytest.fixture
def referral_user(
    db: Session,
    referral: ReferralLink,
    user: User,
):
    """
    Создание пользователя с реферальной ссылкой.
    """
    user.referral_id = referral.id
    db.commit()
    yield user