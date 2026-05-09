import os
import asyncio
from datetime import datetime, timedelta, timezone

import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "6180067276"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "-1002798221648"))
CHANNEL_JOIN_URL = os.getenv("CHANNEL_JOIN_URL", "https://t.me/BGMIxSAFExHACKS").strip()
DB_PATH = os.getenv("DB_PATH", "bot.db")

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def fmt_remaining(delta: timedelta) -> str:
    total = max(0, int(delta.total_seconds()))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"{h}h {m}m {s}s"

def home_text(unlocked: bool) -> str:
    if unlocked:
        return (
            "✅ Channel verified\n\n"
            "🎁 Daily Free Key feature unlocked.\n"
            "Tap Claim Daily Key to collect your key.\n"
            "If you unfollow the channel, claim will lock again."
        )
    return (
        "🔐 First channel follow to get DAILY FREE KEY features unlock.\n\n"
        "Join the channel and then tap Verify Now."
    )

def home_kb(unlocked: bool):
    kb = InlineKeyboardBuilder()
    if unlocked:
        kb.button(text="🎁 Claim Daily Key", callback_data="claim")
        kb.button(text="🔄 Recheck Channel", callback_data="verify")
    else:
        kb.button(text="➕ Join Channel", url=CHANNEL_JOIN_URL)
        kb.button(text="✅ Verify Now", callback_data="verify")
    kb.adjust(1)
    return kb.as_markup()

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                joined INTEGER DEFAULT 0,
                unlocked INTEGER DEFAULT 0,
                last_claim_at TEXT,
                next_claim_at TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_text TEXT UNIQUE,
                used INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                name TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        await db.execute("INSERT OR IGNORE INTO settings(name, value) VALUES('daily_qty', '1')")
        await db.commit()

async def ensure_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO users(user_id) VALUES(?)", (user_id,))
        await db.commit()

async def get_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT user_id, joined, unlocked, last_claim_at, next_claim_at FROM users WHERE user_id=?",
            (user_id,),
        )
        return await cur.fetchone()

async def update_user(user_id: int, joined=None, unlocked=None, last_claim_at=None, next_claim_at=None):
    parts = []
    vals = []
    if joined is not None:
        parts.append("joined=?")
        vals.append(1 if joined else 0)
    if unlocked is not None:
        parts.append("unlocked=?")
        vals.append(1 if unlocked else 0)
    if last_claim_at is not None:
        parts.append("last_claim_at=?")
        vals.append(last_claim_at.isoformat())
    if next_claim_at is not None:
        parts.append("next_claim_at=?")
        vals.append(next_claim_at.isoformat())

    if not parts:
        return

    vals.append(user_id)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {', '.join(parts)} WHERE user_id=?", vals)
        await db.commit()

async def get_setting(name: str, default: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE name=?", (name,))
        row = await cur.fetchone()
        return row[0] if row else default

async def set_setting(name: str, value: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO settings(name, value) VALUES(?, ?) "
            "ON CONFLICT(name) DO UPDATE SET value=excluded.value",
            (name, value),
        )
        await db.commit()

async def add_keys(keys: list[str]):
    async with aiosqlite.connect(DB_PATH) as db:
        for key in keys:
            key = key.strip()
            if not key:
                continue
            try:
                await db.execute("INSERT INTO keys(key_text) VALUES(?)", (key,))
            except Exception:
                pass
        await db.commit()

async def take_keys(n: int) -> list[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "SELECT id, key_text FROM keys WHERE used=0 ORDER BY id ASC LIMIT ?",
            (n,),
        )
        rows = await cur.fetchall()
        if not rows:
            return []

        ids = [row[0] for row in rows]
        await db.executemany("UPDATE keys SET used=1 WHERE id=?", [(i,) for i in ids])
        await db.commit()
        return [row[1] for row in rows]

async def unused_key_count() -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM keys WHERE used=0")
        (cnt,) = await cur.fetchone()
        return cnt

async def is_member(user_id: int) -> bool:
    member = await bot.get_chat_member(CHANNEL_ID, user_id)
    return member.status in ("member", "administrator", "creator")

@dp.message(Command("start"))
async def start(message: Message):
    await ensure_user(message.from_user.id)
    try:
        ok = await is_member(message.from_user.id)
    except Exception:
        ok = False

    await update_user(message.from_user.id, joined=ok, unlocked=ok)
    await message.answer(home_text(ok), reply_markup=home_kb(ok))

@dp.message(Command("menu"))
async def menu(message: Message):
    await ensure_user(message.from_user.id)
    user = await get_user(message.from_user.id)
    ok = bool(user and user[2] == 1)
    try:
        live = await is_member(message.from_user.id)
    except Exception:
        live = False

    if ok and not live:
        await update_user(message.from_user.id, joined=False, unlocked=False)
        ok = False

    await message.answer(home_text(ok), reply_markup=home_kb(ok))

@dp.callback_query(F.data == "verify")
async def verify(callback: CallbackQuery):
    uid = callback.from_user.id
    await ensure_user(uid)

    try:
        ok = await is_member(uid)
    except Exception:
        ok = False

    if ok:
        await update_user(uid, joined=True, unlocked=True)
        await callback.message.edit_text(home_text(True), reply_markup=home_kb(True))
        await callback.answer("Verified")
    else:
        await update_user(uid, joined=False, unlocked=False)
        await callback.message.edit_text(home_text(False), reply_markup=home_kb(False))
        await callback.answer("Join the channel first", show_alert=True)

@dp.callback_query(F.data == "claim")
async def claim(callback: CallbackQuery):
    uid = callback.from_user.id
    await ensure_user(uid)

    try:
        ok = await is_member(uid)
    except Exception:
        ok = False

    if not ok:
        await update_user(uid, joined=False, unlocked=False)
        await callback.message.edit_text(home_text(False), reply_markup=home_kb(False))
        await callback.answer("You left the channel. Claim locked again.", show_alert=True)
        return

    user = await get_user(uid)
    if not user:
        await callback.answer("User not found", show_alert=True)
        return

    next_claim_at = user[4]
    now = utcnow()

    if next_claim_at:
        nca = datetime.fromisoformat(next_claim_at)
        if now < nca:
            await callback.answer(f"Next claim after {fmt_remaining(nca - now)}", show_alert=True)
            return

    daily_qty = int(await get_setting("daily_qty", "1"))
    keys = await take_keys(daily_qty)

    if not keys:
        await callback.answer("No keys available right now", show_alert=True)
        return

    await update_user(
        uid,
        joined=True,
        unlocked=True,
        last_claim_at=now,
        next_claim_at=now + timedelta(hours=24),
    )

    text = "🎁 Your DAILY FREE KEY:\n\n" + "\n".join(f"<code>{k}</code>" for k in keys)
    await callback.message.answer(text, parse_mode="HTML")
    await callback.message.answer(
        "Come back after 24 hours for the next claim.",
        reply_markup=home_kb(True),
    )
    await callback.answer("Claim sent")

@dp.message(Command("addkeys"))
async def addkeys(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID:
        return

    raw = command.args or ""
    keys = [x.strip() for x in raw.split("|") if x.strip()]
    if not keys:
        await message.answer("Usage:\n/addkeys KEY1|KEY2|KEY3")
        return

    await add_keys(keys)
    left = await unused_key_count()
    await message.answer(f"Added {len(keys)} keys.\nUnused keys left: {left}")

@dp.message(Command("setqty"))
async def setqty(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID:
        return

    raw = (command.args or "").strip()
    if not raw.isdigit():
        await message.answer("Usage:\n/setqty 1")
        return

    qty = max(1, min(int(raw), 20))
    await set_setting("daily_qty", str(qty))
    await message.answer(f"Daily claim quantity set to {qty}")

@dp.message(Command("broadcast"))
async def broadcast(message: Message, command: CommandObject):
    if message.from_user.id != OWNER_ID:
        return

    text = (command.args or "").strip()
    if not text:
        await message.answer("Usage:\n/broadcast your message")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users")
        users = await cur.fetchall()

    sent = 0
    for (uid,) in users:
        try:
            await bot.send_message(uid, text)
            sent += 1
            await asyncio.sleep(0.03)
        except Exception:
            pass

    await message.answer(f"Broadcast done. Sent: {sent}")

@dp.message(Command("stats"))
async def stats(message: Message):
    if message.from_user.id != OWNER_ID:
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        (users,) = await cur.fetchone()
        cur = await db.execute("SELECT COUNT(*) FROM keys WHERE used=0")
        (keys_left,) = await cur.fetchone()
        cur = await db.execute("SELECT value FROM settings WHERE name='daily_qty'")
        row = await cur.fetchone()
        qty = row[0] if row else "1"

    await message.answer(
        f"Users: {users}\n"
        f"Unused keys: {keys_left}\n"
        f"Daily qty: {qty}"
    )

@dp.callback_query(F.data == "stats")
async def stats_cb(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Not allowed", show_alert=True)
        return
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT COUNT(*) FROM users")
        (users,) = await cur.fetchone()
        cur = await db.execute("SELECT COUNT(*) FROM keys WHERE used=0")
        (keys_left,) = await cur.fetchone()
        cur = await db.execute("SELECT value FROM settings WHERE name='daily_qty'")
        row = await cur.fetchone()
        qty = row[0] if row else "1"
    await callback.message.answer(
        f"Users: {users}\nUnused keys: {keys_left}\nDaily qty: {qty}"
    )
    await callback.answer()

@dp.callback_query(F.data == "help_add")
async def help_add(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Not allowed", show_alert=True)
        return
    await callback.message.answer("Add keys like this:\n/addkeys KEY1|KEY2|KEY3|KEY4")
    await callback.answer()

@dp.callback_query(F.data == "help_broadcast")
async def help_broadcast(callback: CallbackQuery):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("Not allowed", show_alert=True)
        return
    await callback.message.answer("Broadcast like this:\n/broadcast your message here")
    await callback.answer()

async def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN missing. Put a fresh token in .env")
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
