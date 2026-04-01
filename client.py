import asyncio
import websockets

async def send_messages(websocket):
    while True:
        message = input()
        await websocket.send(message)

async def receive_messages(websocket):
    while True:
        message = await websocket.recv()
        print(f"\nReceived: {message}")

async def main():
    uri = "ws://localhost:8765"

    async with websockets.connect(uri) as websocket:
        print("Connected to chat")

        await asyncio.gather(
            send_messages(websocket),
            receive_messages(websocket)
        )

asyncio.run(main())