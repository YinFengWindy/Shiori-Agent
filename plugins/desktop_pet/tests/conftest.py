"""Shared test doubles: scripted Bilibili HTTP, a controllable danmaku source and clock."""

import asyncio

import httpx
import pytest

LOGIN_COOKIES = {
    "SESSDATA": "sess%2C1%2Cabc",
    "bili_jct": "jct",
    "DedeUserID": "42",
    "DedeUserID__ckMd5": "md5",
}


# nav ``wbi_img`` whose two stems are the 32 + 32 characters WBI mixes into a key.
WBI_IMG = {
    "img_url": "https://i0.hdslb.com/bfs/wbi/7cd084941338484aae1ad9425b84077c.png",
    "sub_url": "https://i0.hdslb.com/bfs/wbi/4932caff0ff746eab6f01bf08b70ac45.png",
}


class FakeBilibili:
    """Answers login, nav and live-room endpoints from mutable scripted state."""

    login_cookies = LOGIN_COOKIES

    def __init__(self) -> None:
        self.scan_code = 86101
        # URL room id -> (real room id, title) served by get_info.
        self.rooms = {"6": (1001, "测试直播间")}
        self.login_valid = True
        self.issued = 0
        self.requests: list[httpx.Request] = []
        # While set, requests whose path ends with ``hold_path`` wait for the
        # gate to be released; ``held`` counts the parked requests.
        self.gate: asyncio.Event | None = None
        self.hold_path = "/qrcode/poll"
        self.held = 0
        self.transport = httpx.MockTransport(self._handle)

    async def wait_held(self, count: int) -> None:
        """Yield until ``count`` requests are parked at ``gate``."""
        while self.held < count:
            await asyncio.sleep(0)

    async def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if self.gate is not None and path.endswith(self.hold_path):
            self.held += 1
            await self.gate.wait()
        if path.endswith("/qrcode/generate"):
            self.issued += 1
            key = f"key-{self.issued}"
            data = {
                "url": f"https://account.bilibili.com/scan?{key}",
                "qrcode_key": key,
            }
            return httpx.Response(200, json={"code": 0, "message": "0", "data": data})
        if path.endswith("/qrcode/poll"):
            return self._poll()
        if path.endswith("/web-interface/nav"):
            session = request.headers.get("cookie", "")
            if self.login_valid and f"SESSDATA={LOGIN_COOKIES['SESSDATA']}" in session:
                data = {"isLogin": True, "mid": 42, "uname": "主播", "wbi_img": WBI_IMG}
                return httpx.Response(200, json={"code": 0, "data": data})
            return httpx.Response(
                200,
                json={
                    "code": -101,
                    "message": "账号未登录",
                    "data": {"isLogin": False, "wbi_img": WBI_IMG},
                },
            )
        if path.endswith("/Room/get_info"):
            room = self.rooms.get(request.url.params.get("room_id", ""))
            if room is None:
                return httpx.Response(200, json={"code": 1, "message": "房间不存在"})
            data = {"room_id": room[0], "title": room[1]}
            return httpx.Response(200, json={"code": 0, "data": data})
        if request.url.host == "www.bilibili.com":
            cookie = "buvid3=BUVID-FAKE; Path=/; Domain=.bilibili.com"
            return httpx.Response(200, headers=[("set-cookie", cookie)], text="<html>")
        if path.endswith("/getDanmuInfo"):
            host = {"host": "comet.example", "port": 2243, "wss_port": 443}
            data = {"token": "stream-token", "host_list": [host]}
            return httpx.Response(200, json={"code": 0, "data": data})
        raise AssertionError(f"unexpected request {request.url}")

    def _poll(self) -> httpx.Response:
        success = self.scan_code == 0
        data = {
            "url": "https://passport.biligame.com/crossDomain?..." if success else "",
            "refresh_token": "refresh" if success else "",
            "timestamp": 0,
            "code": self.scan_code,
            "message": "",
        }
        headers = (
            [
                ("set-cookie", f"{name}={value}; Path=/; Domain=bilibili.com")
                for name, value in LOGIN_COOKIES.items()
            ]
            if success
            else []
        )
        return httpx.Response(
            200, headers=headers, json={"code": 0, "message": "0", "data": data}
        )


@pytest.fixture
def bilibili() -> FakeBilibili:
    """A fresh scripted Bilibili for each test; never touches the network."""
    return FakeBilibili()


async def settle() -> None:
    """Let every ready task run until the loop is quiet."""
    for _ in range(50):
        await asyncio.sleep(0)


class FakeClock:
    """Controllable monotonic clock: ``sleep`` only returns when ``advance`` passes it."""

    def __init__(self) -> None:
        self.time = 0.0
        self._sleepers: list[tuple[float, asyncio.Future[None]]] = []

    def now(self) -> float:
        return self.time

    async def settle(self) -> None:
        """Run every ready task without moving time."""
        await settle()

    async def sleep(self, seconds: float) -> None:
        entry = (self.time + seconds, asyncio.get_running_loop().create_future())
        self._sleepers.append(entry)
        try:
            await entry[1]
        finally:
            self._sleepers.remove(entry)

    async def advance(self, seconds: float) -> None:
        """Move time forward, waking sleepers deadline by deadline."""
        target = self.time + seconds
        while True:
            await settle()
            due = [
                at
                for at, future in self._sleepers
                if at <= target and not future.done()
            ]
            if not due:
                break
            self.time = max(self.time, min(due))
            for at, future in list(self._sleepers):
                if at <= self.time and not future.done():
                    future.set_result(None)
        self.time = target
        await settle()


@pytest.fixture
def clock() -> FakeClock:
    """A fresh controllable clock."""
    return FakeClock()


class FakeStreamConnection:
    """One connection of ``FakeDanmakuSource``; the test drives what it delivers."""

    def __init__(self, room_id: int, uid: int, buvid: str, sink) -> None:
        self.room_id = room_id
        self.uid = uid
        self.buvid = buvid
        self.sink = sink
        self.closed: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def send(
        self, message_id: str, text: str, *, uid: int = 7, uname: str = "观众"
    ) -> None:
        """Deliver one danmaku (a repeat when ``message_id`` was sent before)."""
        from plugins.desktop_pet.backend.bilibili_danmaku import Danmaku

        self.sink.danmaku(
            Danmaku(message_id=message_id, uid=uid, uname=uname, text=text)
        )

    def drop(self, error: BaseException) -> None:
        """End the connection with ``error``, as a real stream failure would."""
        self.closed.set_exception(error)


class FakeDanmakuSource:
    """Controllable danmaku source; each ``run`` is one connection that auths at once."""

    def __init__(self) -> None:
        self.connections: list[FakeStreamConnection] = []
        self.authenticate = True

    @property
    def current(self) -> FakeStreamConnection:
        return self.connections[-1]

    async def run(self, room_id, credentials, buvid, sink) -> None:
        connection = FakeStreamConnection(room_id, credentials.uid, buvid, sink)
        self.connections.append(connection)
        if self.authenticate:
            sink.connected()
        await connection.closed
        raise AssertionError("fake connection closed without an error")


@pytest.fixture
def danmaku_source() -> FakeDanmakuSource:
    """A fresh controllable danmaku source."""
    return FakeDanmakuSource()


def _enable_pet(roles, role_id: str) -> None:
    """Seed ``role_id`` as the pet's single enabled role in the fake role store."""
    package = {
        "id": "pkg",
        "format": "codex",
        "display_name": "Pet",
        "manifest_path": f"plugins/desktop_pet/pets-{role_id}/pkg/pet.json",
        "spritesheet_path": f"plugins/desktop_pet/pets-{role_id}/pkg/sheet.png",
    }
    roles.extensions.values["desktop_pet"] = {
        role_id: {
            "pet_packages": [package],
            "selected_pet_package_id": "pkg",
            "desktop_pet_enabled": True,
        }
    }


@pytest.fixture
def enable_pet():
    """``enable_pet(roles, role_id)``: make ``role_id`` the pet's only enabled role."""
    return _enable_pet


class PetOutputDouble:
    """The real ``LiveReplyOutput`` over a recording RPC; outcomes come back by RPC."""

    def __init__(self, clock: FakeClock, delivered: bool = True) -> None:
        from shiori_sdk.testing.memory_context import FakeRpc

        from plugins.desktop_pet.backend.live_output import LiveReplyOutput

        class Rpc(FakeRpc):
            async def emit(self, name, payload):
                await super().emit(name, payload)
                return delivered

        self.clock = clock
        self.rpc = Rpc()
        self.output = LiveReplyOutput(self.rpc)

    def shows(self) -> list[dict]:
        return [p for name, p in self.rpc.events if name == "live.reply.show"]

    def cancels(self) -> list[dict]:
        return [p for name, p in self.rpc.events if name == "live.cancel"]

    async def outcome(
        self, show: dict, bubble="succeeded", speech="succeeded", error=""
    ):
        """Report one shown reply's outcome as the pet background would."""

        def result(status: str) -> dict:
            return {"status": status, "error": error if status == "failed" else ""}

        await self.rpc.handlers["live.reply.outcome"](
            {
                "reply_id": show["reply_id"],
                "run_id": show["run_id"],
                "bubble": result(bubble),
                "speech": result(speech),
            }
        )
        await self.clock.settle()


@pytest.fixture
def pet_output(clock) -> PetOutputDouble:
    """Pet output whose background receives every show."""
    return PetOutputDouble(clock)


@pytest.fixture
def lost_pet_output(clock) -> PetOutputDouble:
    """Pet output with no background to receive anything."""
    return PetOutputDouble(clock, delivered=False)


class TurnAnswers:
    """Builders for ``FakeExternalTurns`` answers."""

    @staticmethod
    def replied(text: str):
        from shiori_sdk.external_turns import ExternalTurnResult

        return ExternalTurnResult(status="replied", reply=text)

    @staticmethod
    def status(status: str):
        from shiori_sdk.external_turns import ExternalTurnResult

        return ExternalTurnResult(status=status)  # type: ignore[arg-type]

    @staticmethod
    def held(gate: asyncio.Event, reply: str, cancelled: list[str]):
        """An answer that stays in flight until ``gate`` opens."""

        async def answer(message):
            try:
                await gate.wait()
            except asyncio.CancelledError:
                cancelled.append(message.message_id)
                raise
            return TurnAnswers.replied(reply)

        return answer

    @staticmethod
    def failing(error: Exception):
        """An answer whose turn raises ``error``."""

        async def answer(message):
            raise error

        return answer


@pytest.fixture
def answers() -> type[TurnAnswers]:
    """Builders for scripted external-turn answers."""
    return TurnAnswers
