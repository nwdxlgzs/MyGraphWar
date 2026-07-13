import asyncio
import pytest
from types import SimpleNamespace
from server.rooms import Room,RoomManager
from server.simulation import Game
from server.protocol import handle_room_message
from server.rooms import rooms
from server.database import DB,Match,MatchReplay
from sqlalchemy import func,select

class FakeSocket:
    def __init__(self,fail=False):self.messages=[];self.fail=fail;self.closed=None
    async def send_json(self,data):
        if self.fail:raise RuntimeError("disconnected")
        self.messages.append(data)
    async def close(self,code=1000):self.closed=code

def test_twenty_connection_broadcast_and_failed_socket_cleanup():
    manager=RoomManager();room=Room("load","load",1,"owner")
    sockets={i:FakeSocket() for i in range(20)};sockets[7]=FakeSocket(fail=True);room.sockets=sockets
    asyncio.run(manager.broadcast(room,"load_test",{"sequence":1}))
    assert 7 not in room.sockets and len(room.sockets)==19
    assert all(ws.messages==[{"v":1,"type":"load_test","payload":{"sequence":1}}] for ws in room.sockets.values())

def test_owner_transfer_with_multiple_waiting_players():
    manager=RoomManager();users=[SimpleNamespace(id=i,username=f"u{i}") for i in range(1,5)]
    room=manager.create(users[0],"room","teams",20,1)
    for user in users[1:]:manager.join(room,user)
    manager.leave(room,users[0].id,explicit=True)
    assert room.owner_id==users[1].id and len(room.slots)==3

def test_concurrent_ai_triggers_only_one_shot():
    manager=RoomManager();room=Room("ai","ai",1,"owner")
    room.slots=[{"id":"a","name":"A","user_id":None,"team":"A","soldiers":1,"ai":"medium"},{"id":"b","name":"B","user_id":None,"team":"B","soldiers":1,"ai":"medium"}]
    room.game=Game(room.slots,seed=101,units_per_player=1);room.game.obstacles=[]
    async def run():await asyncio.gather(manager.run_ai(room),manager.run_ai(room))
    asyncio.run(run())
    assert len(room.game.history)==1

def test_owner_can_kick_waiting_human_player():
    owner=SimpleNamespace(id=81001,username="owner");guest=SimpleNamespace(id=81002,username="guest")
    room=rooms.create(owner,"kick","teams",4,202);rooms.join(room,guest)
    owner_ws,guest_ws=FakeSocket(),FakeSocket();room.sockets={owner.id:owner_ws,guest.id:guest_ws}
    asyncio.run(handle_room_message(room,owner,owner_ws,{"type":"kick","payload":{"user_id":guest.id}}))
    assert all(s.get("user_id")!=guest.id for s in room.slots)
    assert guest_ws.closed==4003 and guest_ws.messages[-1]["type"]=="kicked"
    rooms.leave(room,owner.id,explicit=True)

def test_original_function_playback_and_next_turn_delay():
    assert RoomManager.resolution_seconds(0)==3
    assert RoomManager.resolution_seconds(1500)==4
    assert RoomManager.resolution_seconds(3000)==5

def test_random_axis_range_changes_each_match_but_stays_in_safe_range():
    room=Room("axis","axis",1,"owner",seed=909);room.axis_range_mode="random"
    first=room.resolved_axis_half_range(1);second=room.resolved_axis_half_range(2)
    assert 5<=first<=50 and 5<=second<=50 and first!=second
    room.axis_range_mode="fixed";room.axis_half_range=7.25
    assert room.resolved_axis_half_range(3)==7.25

def test_reconnect_cancels_pending_disconnect_ai_shot():
    manager=RoomManager();room=Room("reconnect","reconnect",1,"owner")
    room.slots=[{"id":"a","name":"A","user_id":1,"team":"A","soldiers":1,"ai":None},{"id":"b","name":"B","user_id":2,"team":"B","soldiers":1,"ai":None}]
    room.game=Game(room.slots,seed=303,units_per_player=1);room.game.obstacles=[]
    active=room.game.active();room.disconnected.add(active.user_id)
    async def run():
        task=asyncio.create_task(manager.run_ai(room));await asyncio.sleep(1);room.disconnected.discard(active.user_id);await task
    asyncio.run(run())
    assert room.game.history==[]

def test_chat_rate_limit_does_not_limit_commands():
    owner=SimpleNamespace(id=82001,username="owner");room=rooms.create(owner,"rate","teams",4,404);ws=FakeSocket();room.sockets={owner.id:ws}
    asyncio.run(handle_room_message(room,owner,ws,{"type":"chat","payload":{"text":"hello"}}))
    with pytest.raises(ValueError):asyncio.run(handle_room_message(room,owner,ws,{"type":"chat","payload":{"text":"again"}}))
    asyncio.run(handle_room_message(room,owner,ws,{"type":"chat","payload":{"text":"-shownext"}}))
    rooms.leave(room,owner.id,explicit=True)

def test_unfinished_match_is_persisted_as_aborted_once():
    room=Room("aborted","aborted",1,"owner");room.slots=[{"id":"a","name":"A","user_id":None,"team":"A","soldiers":1,"ai":True},{"id":"b","name":"B","user_id":None,"team":"B","soldiers":1,"ai":True}];room.game=Game(room.slots,seed=405,units_per_player=1)
    with DB() as db:before=db.scalar(select(func.count()).select_from(Match))
    rooms.record_aborted(room);rooms.record_aborted(room)
    with DB() as db:
        after=db.scalar(select(func.count()).select_from(Match));saved=db.scalar(select(Match).order_by(Match.id.desc()));replay=db.get(MatchReplay,saved.id)
    assert after==before+1 and not saved.finished and replay is not None

def test_account_moves_between_waiting_rooms_but_not_active_match():
    manager=RoomManager();user=SimpleNamespace(id=83001,username="single")
    first=manager.create(user,"first","teams",4,1);second=manager.create(user,"second","teams",4,2)
    assert first.id not in manager.rooms and manager.user_room[user.id]==second.id
    second.game=Game(second.slots+[{'id':'ai','name':'AI','user_id':None,'team':'B','soldiers':1,'ai':'easy'}],seed=2,units_per_player=1)
    with pytest.raises(ValueError):manager.create(user,"third","teams",4,3)

def test_finished_room_cleanup_removes_membership_and_tasks():
    manager=RoomManager();user=SimpleNamespace(id=84001,username="cleanup");room=manager.create(user,"cleanup","teams",4,1)
    manager.remove_room(room)
    assert room.id not in manager.rooms and user.id not in manager.user_room

def test_owner_can_return_finished_match_to_pregame():
    owner=SimpleNamespace(id=85001,username="owner");room=rooms.create(owner,"rematch","teams",4,505);room.slots.append({"id":"ai","name":"AI","user_id":None,"team":"B","soldiers":1,"ready":True,"ai":"easy","color":"#223344"});room.game=Game(room.slots,seed=505,units_per_player=1);room.game.finished=True;room.game.winner="A";room.match_recorded=True;ws=FakeSocket();room.sockets={owner.id:ws}
    asyncio.run(handle_room_message(room,owner,ws,{"type":"return_to_room","payload":{}}))
    assert room.game is None and not room.match_recorded and not room.slots[0]["ready"]
    assert ws.messages[-1]["type"]=="snapshot"
    rooms.leave(room,owner.id,explicit=True)
