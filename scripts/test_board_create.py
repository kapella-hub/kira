"""Reproduce board creation FK error."""
import asyncio


async def main():
    from kira.web.db.database import get_db, init_db
    from kira.web.db.seed import seed_db

    await init_db(":memory:")
    db = await get_db()
    await seed_db(db)

    # Check existing users
    cursor = await db.execute("SELECT id, username FROM users")
    for u in await cursor.fetchall():
        print(f"  user: {u[0]} -> {u[1]}")

    # Simulate login creating a new user
    import secrets

    uid = secrets.token_hex(8)
    await db.execute(
        "INSERT INTO users (id, username, display_name) VALUES (?, ?, ?)",
        (uid, "newuser", "New"),
    )
    await db.commit()

    # Try creating a board
    from kira.web.boards.service import create_board

    try:
        b = await create_board(db, "Test Board", "desc", uid)
        print(f"OK: board created id={b['id']}")
    except Exception as e:
        print(f"ERR: {type(e).__name__}: {e}")

    # Try with non-existent user
    try:
        await create_board(db, "Bad Board", "desc", "fake-id")
        print("UNEXPECTED: should have failed")
    except Exception as e:
        print(f"FK err (expected): {type(e).__name__}: {e}")

    from kira.web.db.database import close_db

    await close_db()
    print("done")


asyncio.run(main())
