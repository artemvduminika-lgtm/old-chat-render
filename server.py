# ================= SERVER (server.py) =================
import asyncio, websockets, json, sqlite3, uuid
from datetime import datetime

clients = {}

conn = sqlite3.connect("chat.db")
c = conn.cursor()

c.execute("CREATE TABLE IF NOT EXISTS users (id TEXT PRIMARY KEY, username TEXT UNIQUE, password TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS contacts (user_id TEXT, contact_id TEXT)")
c.execute("""
CREATE TABLE IF NOT EXISTS messages (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 sender TEXT,
 receiver TEXT,
 text TEXT,
 time TEXT
)
""")
conn.commit()

# --- HELPERS ---
def get_user(username):
    c.execute("SELECT id FROM users WHERE username=?", (username,))
    r = c.fetchone()
    return r[0] if r else None


def get_username(uid):
    c.execute("SELECT username FROM users WHERE id=?", (uid,))
    r = c.fetchone()
    return r[0] if r else "unknown"


def get_contacts(uid):
    c.execute("""
    SELECT u.username FROM contacts c
    JOIN users u ON c.contact_id = u.id
    WHERE c.user_id=?
    """, (uid,))
    return [r[0] for r in c.fetchall()]


def add_contact(a, b):
    c.execute("INSERT OR IGNORE INTO contacts VALUES (?, ?)", (a, b))
    conn.commit()


def save_msg(s, r, t):
    time = datetime.now().strftime("%H:%M")
    c.execute("INSERT INTO messages (sender,receiver,text,time) VALUES (?,?,?,?)",
              (s, r, t, time))
    conn.commit()
    return c.lastrowid, time


def edit_msg(mid, uid, text):
    c.execute("SELECT sender FROM messages WHERE id=?", (mid,))
    r = c.fetchone()
    if r and r[0] == uid:
        c.execute("UPDATE messages SET text=? WHERE id=?", (text, mid))
        conn.commit()
        return True
    return False


def delete_msg(mid, uid):
    c.execute("SELECT sender FROM messages WHERE id=?", (mid,))
    r = c.fetchone()
    if r and r[0] == uid:
        c.execute("DELETE FROM messages WHERE id=?", (mid,))
        conn.commit()
        return True
    return False


def get_history(a, b):
    c.execute("""
    SELECT id,sender,receiver,text,time FROM messages
    WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) ORDER BY id
    """, (a,b,b,a))
    rows = c.fetchall()
    return [{
        "id":r[0],
        "from":get_username(r[1]),
        "to":get_username(r[2]),
        "text":r[3],
        "time":r[4]
    } for r in rows]

async def send_to(username, data):
    for ws, info in clients.items():
        if info["username"] == username:
            await ws.send(json.dumps(data))

async def broadcast_online():
    online = [info["username"] for info in clients.values()]
    for ws in clients:
        await ws.send(json.dumps({"type":"online","users":online}))

# --- HANDLER ---
async def handler(ws):
    try:
        async for raw in ws:
            data = json.loads(raw)

            if data["type"] == "register":
                try:
                    uid = str(uuid.uuid4())
                    c.execute("INSERT INTO users VALUES (?,?,?)", (uid, data["username"], data["password"]))
                    conn.commit()
                    await ws.send(json.dumps({"type":"ok"}))
                except:
                    await ws.send(json.dumps({"type":"error"}))

            elif data["type"] == "login":
                c.execute("SELECT id FROM users WHERE username=? AND password=?",
                          (data["username"], data["password"]))
                r = c.fetchone()

                if r:
                    clients[ws] = {"id": r[0], "username": data["username"]}
                    await ws.send(json.dumps({
                        "type":"auth",
                        "success":True,
                        "contacts": get_contacts(r[0]),
                        "username": data["username"]
                    }))
                    await broadcast_online()
                else:
                    await ws.send(json.dumps({"type":"auth","success":False}))

            elif data["type"] == "add_contact":
                uid = clients[ws]["id"]
                other = get_user(data["username"])
                if other:
                    add_contact(uid, other)
                    await ws.send(json.dumps({
                        "type":"contacts",
                        "contacts": get_contacts(uid)
                    }))

            elif data["type"] == "history":
                uid = clients[ws]["id"]
                other = get_user(data["user"])
                await ws.send(json.dumps({"type":"history","data":get_history(uid,other)}))

            elif data["type"] == "send":
                uid = clients[ws]["id"]
                other = get_user(data["to"])

                mid, time = save_msg(uid, other, data["text"])

                payload = {
                    "type":"msg",
                    "id":mid,
                    "from":clients[ws]["username"],
                    "to":data["to"],
                    "text":data["text"],
                    "time":time
                }

                await send_to(data["to"], payload)
                await ws.send(json.dumps(payload))

            elif data["type"] == "edit":
                uid = clients[ws]["id"]
                if edit_msg(data["id"], uid, data["text"]):
                    await ws.send(json.dumps({"type":"edit","id":data["id"],"text":data["text"]}))

            elif data["type"] == "delete":
                uid = clients[ws]["id"]
                if delete_msg(data["id"], uid):
                    await ws.send(json.dumps({"type":"delete","id":data["id"]}))

    finally:
        if ws in clients:
            del clients[ws]
            await broadcast_online()

async def main():
    async with websockets.serve(handler, "192.168.31.72", 8765):
        print("Server running")
        await asyncio.Future()

asyncio.run(main())


# ================= CLIENT (index.html) =================
