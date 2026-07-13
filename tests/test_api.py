from fastapi.testclient import TestClient
from server.main import app
import uuid
from types import SimpleNamespace
from sqlalchemy import func,select
from server.database import DB,Match,MatchParticipant,MatchReplay
from server.rooms import Room,rooms
from server.simulation import Game

def test_health():
    with TestClient(app) as c:
        r=c.get('/api/v1/health');assert r.status_code==200 and r.json()['ok']

def test_classic_and_extended_room_limits():
    name="rules_"+uuid.uuid4().hex[:8]
    with TestClient(app) as c:
        c.post('/api/v1/auth/register',json={"username":name,"password":"testing123"})
        classic=c.post('/api/v1/rooms',json={"name":"classic","mode":"teams","ruleset":"classic","max_players":20})
        assert classic.status_code==200 and classic.json()["max_players"]==10
        assert c.post('/api/v1/rooms',json={"name":"bad","mode":"ffa","ruleset":"classic","max_players":8}).status_code==400
        extended=c.post('/api/v1/rooms',json={"name":"extended","mode":"ffa","ruleset":"extended","max_players":20})
        assert extended.status_code==200 and extended.json()["max_players"]==20

def test_password_change_and_logout_invalidate_old_credentials():
    name="password_"+uuid.uuid4().hex[:8]
    with TestClient(app) as c:
        assert c.post('/api/v1/auth/register',json={"username":name,"password":"oldpass123"}).status_code==200
        assert c.post('/api/v1/auth/password',json={"current_password":"wrongpass","new_password":"newpass123"}).status_code==400
        assert c.post('/api/v1/auth/password',json={"current_password":"oldpass123","new_password":"newpass123"}).status_code==200
        assert c.post('/api/v1/auth/logout').status_code==200
        assert c.get('/api/v1/auth/me').status_code==401
        assert c.post('/api/v1/auth/login',json={"username":name,"password":"oldpass123"}).status_code==401
        assert c.post('/api/v1/auth/login',json={"username":name,"password":"newpass123"}).status_code==200

def test_websocket_error_isolated_and_connection_survives():
    name="ws_"+uuid.uuid4().hex[:8]
    with TestClient(app) as c:
        assert c.post('/api/v1/auth/register',json={"username":name,"password":"testing123"}).status_code==200
        room=c.post('/api/v1/rooms',json={"name":"protocol","mode":"teams","max_players":4}).json()
        with c.websocket_connect(f'/ws/v1/rooms/{room["id"]}') as ws:
            assert ws.receive_json()["type"]=="snapshot"
            ws.send_json({"v":1,"type":"not_a_real_message","payload":{}})
            error=ws.receive_json();assert error["type"]=="error"
            ws.send_json({"v":1,"type":"ping","payload":{}})
            pong=ws.receive_json();assert pong["type"]=="pong"
            ws.send_json({"v":1,"type":"chat","payload":{"text":"x"*5000}})
            oversized=ws.receive_json();assert oversized["type"]=="error" and "4 KiB" in oversized["payload"]["message"]
            ws.send_json({"v":1,"type":"ping","payload":{}});assert ws.receive_json()["type"]=="pong"
            ws.send_json({"v":1,"type":"chat","payload":{"text":"-shownext"}})
            assert ws.receive_json()=={"v":1,"type":"preference","payload":{"show_next":True}}
            ws.send_json({"v":1,"type":"chat","payload":{"text":"-sayfunc"}})
            shown=ws.receive_json();assert shown["type"]=="system"
            ws.send_json({"v":1,"type":"add_ai","payload":{"difficulty":"easy"}})
            assert ws.receive_json()["type"]=="snapshot"
            ws.send_json({"v":1,"type":"configure","payload":{"function_mode":"normal","units_per_player":1}})
            assert ws.receive_json()["type"]=="snapshot"
            ws.send_json({"v":1,"type":"configure","payload":{"axis_half_range":7.5}})
            scaled=ws.receive_json();assert scaled["type"]=="snapshot" and scaled["payload"]["axis_half_range"]==7.5
            ws.send_json({"v":1,"type":"configure","payload":{"axis_range_mode":"random"}})
            random_mode=ws.receive_json();assert random_mode["type"]=="snapshot" and random_mode["payload"]["axis_range_mode"]=="random"
            ws.send_json({"v":1,"type":"configure","payload":{"axis_half_range":101}})
            assert ws.receive_json()["type"]=="error"
            ws.send_json({"v":1,"type":"ping","payload":{}});assert ws.receive_json()["type"]=="pong"
            ws.send_json({"v":1,"type":"configure","payload":{"mode":"ffa"}})
            classic_mode_error=ws.receive_json();assert classic_mode_error["type"]=="error" and "经典规则" in classic_mode_error["payload"]["message"]
            owner_slot=room["slots"][0]["id"]
            ws.send_json({"v":1,"type":"configure","payload":{"slot_id":owner_slot,"color":"#1260a0"}})
            colored=ws.receive_json();assert colored["type"]=="snapshot" and colored["payload"]["slots"][0]["color"]=="#1260a0"
            ws.send_json({"v":1,"type":"configure","payload":{"slot_id":owner_slot,"color":"javascript:red"}})
            assert ws.receive_json()["type"]=="error"
            ws.send_json({"v":1,"type":"configure","payload":{"slot_id":owner_slot,"color":"#ffffff"}})
            assert ws.receive_json()["type"]=="error"
            ws.send_json({"v":1,"type":"start","payload":{}})
            countdown=ws.receive_json();assert countdown["type"]=="countdown" and countdown["payload"]["start_deadline"]
            assert ws.receive_json()["type"]=="started"
            turn=ws.receive_json();assert turn["type"]=="turn" and turn["payload"]["turn_deadline"]
            ws.send_json({"v":1,"type":"validate_expression","payload":{"expression":"sin(x)"}})
            valid=ws.receive_json();assert valid["type"]=="validation" and valid["payload"]["ok"]
            ws.send_json({"v":1,"type":"validate_expression","payload":{"expression":"__import__('os')"}})
            invalid=ws.receive_json();assert invalid["type"]=="validation" and not invalid["payload"]["ok"]
            ws.send_json({"v":1,"type":"shoot","payload":{"expression":"__import__('os')"}})
            assert ws.receive_json()["type"]=="error"
            ws.send_json({"v":1,"type":"ping","payload":{}})
            assert ws.receive_json()["type"]=="pong"

def test_finished_match_is_recorded_once():
    room=Room("record","record",999,"owner")
    room.slots=[{"id":"ai1","name":"A","user_id":None,"team":"A","soldiers":1,"ai":"easy"},{"id":"ai2","name":"B","user_id":None,"team":"B","soldiers":1,"ai":"easy"}]
    room.game=Game(room.slots,seed=44,units_per_player=1);room.game.finished=True;room.game.winner="A"
    with DB() as db:before=db.scalar(select(func.count()).select_from(Match))
    rooms.record_match(room);rooms.record_match(room)
    with DB() as db:
        after=db.scalar(select(func.count()).select_from(Match));saved=db.scalar(select(Match).order_by(Match.id.desc()))
        participants=list(db.scalars(select(MatchParticipant).where(MatchParticipant.match_id==saved.id)))
        replay=db.get(MatchReplay,saved.id)
    assert after==before+1 and len(participants)==2 and replay is not None

def test_waiting_room_leave_transfers_owner_and_removes_empty_room():
    first=SimpleNamespace(id=70001,username="first");second=SimpleNamespace(id=70002,username="second")
    room=rooms.create(first,"lifecycle","teams",4,123);rooms.join(room,second)
    rooms.leave(room,first.id,explicit=True)
    assert room.owner_id==second.id and all(s.get("user_id")!=first.id for s in room.slots)
    rooms.leave(room,second.id,explicit=True)
    assert room.id not in rooms.rooms

def test_replay_contains_initial_and_final_state():
    slots=[{"id":"a","name":"A","user_id":None,"team":"A","soldiers":1},{"id":"b","name":"B","user_id":None,"team":"B","soldiers":1}]
    game=Game(slots,seed=61,units_per_player=1);game.obstacles=[];game.shoot("0")
    replay=game.replay()
    assert replay["version"]==1 and replay["initial"]["turn"]==0
    assert len(replay["shots"])==1 and replay["final"]["turn"]==1
