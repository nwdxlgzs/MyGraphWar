import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Cookie, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select
from . import __version__
from .config import settings
from .auth import db_session,current_user,validate_credentials,create_session,hasher,websocket_user
from .database import init_db,User,Session,PlayerStats,Match,MatchParticipant,MatchReplay,DB
from .rooms import rooms
from .simulation import Game,ExpressionError
from .protocol import handle_room_message

@asynccontextmanager
async def lifespan(app):
    init_db()
    yield
    for room in list(rooms.rooms.values()):rooms.record_aborted(room)
app=FastAPI(title="MyGraphWar",version=__version__,lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=["http://localhost:5173","http://127.0.0.1:5173"],allow_credentials=True,allow_methods=["*"],allow_headers=["*"])

class Credentials(BaseModel): username:str; password:str
class PasswordChange(BaseModel): current_password:str; new_password:str
class RoomCreate(BaseModel): name:str=Field(min_length=1,max_length=32); mode:str="teams"; ruleset:str="classic"; max_players:int=Field(8,ge=2,le=20); seed:int|None=None

def user_json(u): return {"id":u.id,"username":u.username}

@app.get("/api/v1/health")
def health():return {"ok":True,"version":__version__}
@app.post("/api/v1/auth/register")
def register(data:Credentials,response:Response,db=Depends(db_session)):
    validate_credentials(data.username,data.password)
    if db.scalar(select(User).where(User.username==data.username)):raise HTTPException(409,"用户名已存在")
    u=User(username=data.username,password_hash=hasher.hash(data.password));db.add(u);db.flush();db.add(PlayerStats(user_id=u.id));db.commit();token=create_session(db,u.id);response.set_cookie("mgw_session",token,httponly=True,samesite="lax",max_age=2592000);return user_json(u)
@app.post("/api/v1/auth/login")
def login(data:Credentials,response:Response,db=Depends(db_session)):
    u=db.scalar(select(User).where(User.username==data.username))
    if not u or not hasher.verify(data.password,u.password_hash):raise HTTPException(401,"用户名或密码错误")
    token=create_session(db,u.id);response.set_cookie("mgw_session",token,httponly=True,samesite="lax",max_age=2592000);return user_json(u)
@app.post("/api/v1/auth/logout")
def logout(response:Response,mgw_session:str|None=Cookie(None),user=Depends(current_user),db=Depends(db_session)):
    if mgw_session:
        row=db.get(Session,mgw_session)
        if row:db.delete(row);db.commit()
    response.delete_cookie("mgw_session");return {"ok":True}
@app.post("/api/v1/auth/password")
def change_password(data:PasswordChange,user=Depends(current_user),db=Depends(db_session)):
    if not hasher.verify(data.current_password,user.password_hash):raise HTTPException(400,"当前密码错误")
    if len(data.new_password)<8 or len(data.new_password)>128:raise HTTPException(400,"新密码需为8-128位")
    if data.current_password==data.new_password:raise HTTPException(400,"新密码不能与当前密码相同")
    db_user=db.get(User,user.id);db_user.password_hash=hasher.hash(data.new_password);db.commit();return {"ok":True}
@app.get("/api/v1/auth/me")
def me(user=Depends(current_user)):return user_json(user)
@app.get("/api/v1/stats")
def stats(user=Depends(current_user)):
    with DB() as db:
        s=db.get(PlayerStats,user.id);return {"matches":s.matches,"wins":s.wins,"kills":s.kills,"damage":s.damage}
@app.get("/api/v1/matches")
def match_history(user=Depends(current_user)):
    with DB() as db:
        ids=list(db.scalars(select(MatchParticipant.match_id).where(MatchParticipant.user_id==user.id).order_by(MatchParticipant.match_id.desc()).limit(50)))
        matches=[db.get(Match,i) for i in ids]
        return [{"id":m.id,"mode":m.mode,"winner":m.winner,"turns":m.turns,"finished":m.finished,"created_at":m.created_at.isoformat()} for m in matches if m]
@app.get("/api/v1/matches/{match_id}")
def match_detail(match_id:int,user=Depends(current_user)):
    with DB() as db:
        match=db.get(Match,match_id)
        if not match:raise HTTPException(404,"比赛不存在")
        participants=list(db.scalars(select(MatchParticipant).where(MatchParticipant.match_id==match_id)))
        return {"id":match.id,"mode":match.mode,"winner":match.winner,"turns":match.turns,"created_at":match.created_at.isoformat(),"participants":[{"name":p.name,"team":p.team,"soldiers":p.soldiers,"kills":p.kills,"won":p.won,"is_ai":p.is_ai} for p in participants]}
@app.get("/api/v1/matches/{match_id}/replay")
def saved_replay(match_id:int,user=Depends(current_user)):
    import json
    with DB() as db:
        replay=db.get(MatchReplay,match_id)
        if not replay:raise HTTPException(404,"重放不存在")
        return json.loads(replay.payload)
@app.get("/api/v1/rooms")
def list_rooms(user=Depends(current_user)):return rooms.list()
@app.post("/api/v1/rooms")
def create_room(data:RoomCreate,user=Depends(current_user)):
    if data.mode not in ("teams","ffa") or data.ruleset not in ("classic","extended"):raise HTTPException(400,"无效模式")
    if data.ruleset=="classic" and data.mode!="teams":raise HTTPException(400,"经典规则只支持 A/B 团队战")
    if len(rooms.rooms)>=settings.max_rooms and user.id not in rooms.user_room:raise HTTPException(503,"服务器房间数量已达上限")
    try:return rooms.create(user,data.name,data.mode,data.max_players,data.seed,data.ruleset).public()
    except ValueError as exc:raise HTTPException(409,str(exc))
@app.get("/api/v1/rooms/{room_id}")
def room_detail(room_id:str,user=Depends(current_user)):
    r=rooms.rooms.get(room_id)
    if not r:raise HTTPException(404,"房间不存在")
    return r.public()
@app.get("/api/v1/rooms/{room_id}/replay")
def room_replay(room_id:str,user=Depends(current_user)):
    r=rooms.rooms.get(room_id)
    if not r or not r.game:raise HTTPException(404,"重放不存在")
    return r.game.replay()

@app.websocket("/ws/v1/rooms/{room_id}")
async def room_ws(ws:WebSocket,room_id:str):
    user=websocket_user(ws);room=rooms.rooms.get(room_id)
    if not user or not room:await ws.close(4401 if not user else 4404);return
    try:rooms.join(room,user)
    except ValueError:await ws.close(4409);return
    await ws.accept();old=room.sockets.get(user.id)
    if old:
        try:await old.close(4001)
        except Exception:pass
    room.sockets[user.id]=ws;await rooms.broadcast(room,"snapshot")
    room.disconnected.discard(user.id)
    try:
        while True:
            msg=await asyncio.wait_for(ws.receive_json(),timeout=30)
            if len(json.dumps(msg,ensure_ascii=False).encode("utf-8"))>4096:
                await ws.send_json({"v":1,"type":"error","payload":{"message":"消息超过 4 KiB 限制"}});continue
            try:
                if await handle_room_message(room,user,ws,msg)=="leave":break
            except (ValueError,ExpressionError,TypeError) as e:await ws.send_json({"v":1,"type":"error","payload":{"message":str(e)}})
    except asyncio.TimeoutError:
        try:await ws.close(code=4000,reason="心跳超时")
        except Exception:pass
    except (WebSocketDisconnect,RuntimeError):pass
    finally:
        if room.sockets.get(user.id)==ws:
            room.sockets.pop(user.id,None)
            if room.game and any(s.get("user_id")==user.id for s in room.slots):room.disconnected.add(user.id);asyncio.create_task(rooms.run_ai(room))
            elif room.game:room.spectators.pop(user.id,None)
            else:rooms.leave(room,user.id)
            if room.game and room.game.finished and not room.sockets:rooms.remove_room(room)

dist=Path(__file__).resolve().parents[1]/"web"/"dist"
if dist.exists():app.mount("/",StaticFiles(directory=dist,html=True),name="web")
