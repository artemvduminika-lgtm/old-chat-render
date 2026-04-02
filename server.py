import asyncio
import websockets
import json
import sqlite3
from datetime import datetime

clients = {}


conn = sqlite3.connect("chat.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    room TEXT,
    username TEXT,
    message TEXT,
    timestamp TEXT
)
""")
conn.commit()


# --- ФУНКЦИИ ---

async def broadcast(room, message):
    """Отправка всем в комнате"""
    data = json.dumps(message)
    await asyncio.gather(*[
        ws.send(data)
        for ws, info in clients.items()
        if info["room"] == room
    ])


def save_message(room, username, message):
    cursor.execute(
        "INSERT INTO messages (room, username, message, timestamp) VALUES (?, ?, ?, ?)",
        (room, username, message, datetime.now().isoformat())
    )
    conn.commit()


def get_history(room, limit=50):
    cursor.execute(
        "SELECT username, message, timestamp FROM messages WHERE room=? ORDER BY id DESC LIMIT ?",
        (room, limit)
    )
    rows = cursor.fetchall()
    return list(reversed(rows))


async def send_user_list(room):
    users = [
        info["username"]
        for info in clients.values()
        if info["room"] == room
    ]

    await broadcast(room, {
        "type": "users",
        "users": users
    })

async def handler(websocket):
    try:
        data = json.loads(await websocket.recv())

        username = data.get("username", "Anonymous")
        room = data.get("room", "general")

        clients[websocket] = {
            "username": username,
            "room": room
        }

        print(f"{username} joined {room}")

        history = get_history(room)
        await websocket.send(json.dumps({
            "type": "history",
            "messages": history
        }))

        await broadcast(room, {
            "type": "system",
            "message": f"{username} joined the room"
        })

        await send_user_list(room)

        async for message in websocket:
            data = json.loads(message)

            text = data["message"]

            save_message(room, username, text)

            await broadcast(room, {
                "type": "message",
                "user": username,
                "message": text,
                "time": datetime.now().strftime("%H:%M:%S")
            })

    except websockets.ConnectionClosed:
        pass

    finally:
        if websocket in clients:
            info = clients[websocket]
            username = info["username"]
            room = info["room"]

            del clients[websocket]

            print(f"{username} left {room}")

            await broadcast(room, {
                "type": "system",
                "message": f"{username} left the room"
            })

            await send_user_list(room)


# --- ЗАПУСК ---

async def main():
    async with websockets.serve(handler, "localhost", 8765):
        print("Server running at ws://localhost:8765")
        await asyncio.Future()

asyncio.run(main())
