from fastapi import Request
from fastapi.responses import JSONResponse
from aiogram import types, filters
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User
from routers import router, dp, bot


@router.post("/telegram")
async def telegram_handler(request: Request):
    """
        Handler for telegram bot
    """
    body = await request.body()
    if body:
        update = types.Update.model_validate(
            obj=await request.json(),
            context={"bot": bot}
        )
        await dp.feed_update(bot, update)
    return JSONResponse(status_code=200, content={"message": "OK"})


@dp.message(filters.Command("start"))
async def start_handler(
    message: types.Message,
    db: AsyncSession
):
    """
    /start
    """
    print(message.passport_data)
    # Check if the user exists
    result = await db.execute(select(User).filter(User.telegram_id == message.from_user.id))
    user = result.scalars().first()

    if not user:
        # Create a new user if not exists
        new_user = User(
            telegram_id=message.from_user.id,
            first_name=message.from_user.first_name,
            last_name=message.from_user.last_name,
            language_code=message.from_user.language_code,
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        user = new_user
    await message.reply(
        f"Hello, {message.from_user.full_name}!"
        "Please provide your passport details.",
        reply_markup=types.ReplyKeyboardRemove()
    )


@dp.message()
async def empty(message: types.Message):
    return await message.reply("I don't understand you.")