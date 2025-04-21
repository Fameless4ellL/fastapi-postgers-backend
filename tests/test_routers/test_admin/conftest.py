import io

import pytest
from PIL import Image
from fastapi import UploadFile
from httpx import AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from models import InstaBingo, Currency
from models.user import Role, User, Kyc, ReferralLink, Document

PASSWORD = "test_password"


@pytest.fixture
async def admin(
    db: AsyncSession,
    user: User,
):
    user.role = Role.SUPER_ADMIN.value
    await db.commit()
    yield user


@pytest.fixture
async def admin_token(
    async_api: AsyncClient,
    admin: User,
):
    response =await async_api.post(
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
async def kyc(
    db: AsyncSession,
):
    """
    Создание KYC.
    """
    kyc = Kyc(
        country="USA",
    )
    db.add(kyc)
    await db.commit()
    await db.refresh(kyc)
    yield kyc

    try:
        await db.execute(
            delete(Kyc).where(Kyc.id == kyc.id)
        )
        await db.commit()
    except Exception as e:
        print(e)


@pytest.fixture
async def instabingo(
    db: AsyncSession,
    currency: Currency,
):
    """
    Create InstaBingo.
    """
    instabingo = InstaBingo(
        country="KAZ",
        currency_id=currency.id
    )
    db.add(instabingo)
    await db.commit()
    await db.refresh(instabingo)
    yield instabingo

    try:
        await db.execute(
            delete(InstaBingo).where(InstaBingo.id == instabingo.id)
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(e)


@pytest.fixture
async def referral(
    db: AsyncSession,
    admin: User,
):
    """
    Create a referral link.
    """
    referral = ReferralLink(
        name="test_referral",
        comment="test_comment",
        link="test_link",
        generated_by=admin.id,
    )
    db.add(referral)
    await db.commit()
    await db.refresh(referral)
    yield referral

    try:
        await db.execute(
            delete(ReferralLink).where(ReferralLink.id == referral.id)
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        print(e)


@pytest.fixture
async def referral_user(
    db: AsyncSession,
    referral: ReferralLink,
    user: User,
):
    """
    Create a user with a referral link.
    """
    user.referral_id = referral.id
    await db.commit()
    yield user


@pytest.fixture
async def file() -> UploadFile:
    """
    Create a file.
    """
    img = Image.new('RGB', (800, 600), color='blue')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)

    upload_file = UploadFile(
        filename="test_image.png",
        file=img_bytes,
    )

    yield upload_file


@pytest.fixture(scope="function")
async def doc(
    db: AsyncSession,
    user: User,
    file: UploadFile,
):
    """
    Create a document.
    """
    doc = Document(
        user_id=user.id,
        file=file,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    yield doc

    try:
        await db.execute(
            delete(Document).where(Document.id == doc.id)
        )
        await db.commit()
    except Exception as e:
        print(e)