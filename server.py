import asyncio
import websockets
import json
import sqlite3
from datetime import datetime
import uuid

clients = {}

conn = sqlite3.connect("chat.db")
cursor = conn.cursor()

cursor.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE)")
cursor.execute("CREATE TABLE IF NOT EXISTS contacts (user_id TEXT, contact_id TEXT)")
cursor.execute("""
CREATE TABLE IF NOT EXISTS private_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT,
    receiver TEXT,
    message TEXT,
    timestamp TEXT
)
""")
conn.commit()

# --- HELPERS ---

def get_or_create_user(username):
    cursor.execute("SELECT id FROM users WHERE username=?", (username,))
    row = cursor.fetchone()
    if row: return row[0]

    uid = str(uuid.uuid4())
    cursor.execute("INSERT INTO users VALUES (?, ?)", (uid, username))
    conn.commit()
    return uid


def get_username(user_id):
    cursor.execute("SELECT username FROM users WHERE id=?", (user_id,))
    r = cursor.fetchone()
    return r[0] if r else "unknown"


def get_contacts(user_id):
    cursor.execute("""
    SELECT u.username FROM contacts c
    JOIN users u ON c.contact_id = u.id
    WHERE c.user_id=?
    """, (user_id,))
    return [r[0] for r in cursor.fetchall()]


def add_contact(user_id, contact_id):
    cursor.execute("SELECT 1 FROM contacts WHERE user_id=? AND contact_id=?", (user_id, contact_id))
    if cursor.fetchone(): return
    cursor.execute("INSERT INTO contacts VALUES (?, ?)", (user_id, contact_id))
    conn.commit()


def save_private(s, r, m):
    cursor.execute("INSERT INTO private_messages (sender, receiver, message, timestamp) VALUES (?, ?, ?, ?)",
                   (s, r, m, datetime.now().isoformat()))
    conn.commit()


def get_history(a, b):
    cursor.execute("""
    SELECT sender, message FROM private_messages
    WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?)
    ORDER BY id
    """, (a, b, b, a))
    rows = cursor.fetchall()
    return [(get_username(r[0]), r[1]) for r in rows]


def get_unread_contacts(user_id):
    # very simple: who sent last messages
    cursor.execute("""
    SELECT DISTINCT sender FROM private_messages
    WHERE receiver=?
    ORDER BY id DESC
    LIMIT 20
    """, (user_id,))
    return [get_username(r[0]) for r in cursor.fetchall()]


async def send_to(username, data):
    for ws, info in clients.items():
        if info["username"] == username:
            await ws.send(json.dumps(data))


# --- HANDLER ---

async def handler(ws):
    data = json.loads(await ws.recv())
    username = data["username"]
    uid = get_or_create_user(username)

    clients[ws] = {"username": username, "id": uid}

    await ws.send(json.dumps({
        "type": "init",
        "contacts": get_contacts(uid),
        "unread": get_unread_contacts(uid)
    }))

    try:
        async for msg in ws:
            data = json.loads(msg)

            if data["type"] == "add_contact":
                cursor.execute("SELECT id FROM users WHERE username=?", (data["username"],))
                r = cursor.fetchone()
                if r:
                    add_contact(uid, r[0])
                    await ws.send(json.dumps({"type": "contacts", "contacts": get_contacts(uid)}))

            elif data["type"] == "load_history":
                cursor.execute("SELECT id FROM users WHERE username=?", (data["username"],))
                r = cursor.fetchone()
                if r:
                    await ws.send(json.dumps({"type": "history", "messages": get_history(uid, r[0])}))

            elif data["type"] == "private":
                to = data["to"]
                text = data["message"]

                cursor.execute("SELECT id FROM users WHERE username=?", (to,))
                r = cursor.fetchone()
                if r:
                    save_private(uid, r[0], text)

                    await send_to(to, {
                        "type": "private",
                        "from": username,
                        "message": text
                    })

    finally:
        del clients[ws]


async def main():
    async with websockets.serve(handler, "192.168.1.104", 8765):
        print("Running...")
        await asyncio.Future()

asyncio.run(main())
