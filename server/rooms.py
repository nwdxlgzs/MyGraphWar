import asyncio, random, secrets, time
import json
from dataclasses import dataclass, field
from fastapi import WebSocket
from .simulation import Game, ExpressionError
from .ai import choose_expression
from .database import DB, Match, MatchParticipant, MatchReplay, PlayerStats

COLORS=["#59c3ff","#ff6b6b","#ffd166","#7be495","#c792ea","#ff9f43"]

@dataclass
class Room:
    id:str; name:str; owner_id:int; owner_name:str; mode:str="teams"; max_players:int=8; seed:int=1
    units_per_player:int=2; function_mode:str="normal"; ruleset:str="classic"; axis_half_range:float=25.0; axis_range_mode:str="fixed"
    slots:list=field(default_factory=list); sockets:dict=field(default_factory=dict); chat:list=field(default_factory=list); game:Game|None=None; lock:asyncio.Lock=field(default_factory=asyncio.Lock)
    disconnected:set=field(default_factory=set); say_functions:set=field(default_factory=set); show_next:set=field(default_factory=set); skip_votes:set=field(default_factory=set)
    turn_task:asyncio.Task|None=None
    start_task:asyncio.Task|None=None; starting:bool=False; start_deadline:float|None=None
    match_recorded:bool=False
    spectators:dict=field(default_factory=dict)
    ai_running:bool=False
    last_actions:dict=field(default_factory=dict)
    match_sequence:int=0
    def __post_init__(self): self.slots.append({"id":secrets.token_hex(3),"name":self.owner_name,"user_id":self.owner_id,"team":"A","soldiers":2,"ready":False,"ai":None,"color":COLORS[0]})
    def resolved_axis_half_range(self,token):return self.axis_half_range if self.axis_range_mode=="fixed" else round(random.Random(f"{self.seed}:{token}:axis").uniform(5,50),2)
    def public(self): return {"id":self.id,"name":self.name,"owner_id":self.owner_id,"mode":self.mode,"ruleset":self.ruleset,"max_players":self.max_players,"seed":self.seed,"units_per_player":self.units_per_player,"function_mode":self.function_mode,"axis_half_range":self.axis_half_range,"axis_range_mode":self.axis_range_mode,"slots":self.slots,"spectators":[{"id":k,"name":v} for k,v in self.spectators.items()],"starting":self.starting,"start_deadline":self.start_deadline,"status":"playing" if self.game else "starting" if self.starting else "waiting","game":self.game.snapshot() if self.game else None,"chat":self.chat[-50:]}

class RoomManager:
    def __init__(self): self.rooms={}; self.user_room={}
    def list(self): return [{"id":r.id,"name":r.name,"players":len(r.slots),"max_players":r.max_players,"mode":r.mode,"ruleset":r.ruleset,"status":"playing" if r.game else "starting" if r.starting else "waiting"} for r in self.rooms.values()]
    def create(self,user,name,mode,max_players,seed=None,ruleset="classic"):
        previous_id=self.user_room.get(user.id);previous=self.rooms.get(previous_id) if previous_id else None
        if previous:
            if previous.game or previous.starting:raise ValueError("你已有正在进行或即将开始的比赛")
            self.leave(previous,user.id,explicit=True)
        ruleset=ruleset if ruleset in ("classic","extended") else "classic"
        if ruleset=="classic":mode="teams";max_players=min(10,max_players)
        rid=secrets.token_hex(3); room=Room(rid,name[:32],user.id,user.username,mode,max(2,min(20,max_players)),seed or random.randint(1,999999),ruleset=ruleset); self.rooms[rid]=room; self.user_room[user.id]=rid; return room
    def join(self,room,user):
        previous_id=self.user_room.get(user.id);previous=self.rooms.get(previous_id) if previous_id else None
        if previous and previous.id!=room.id:
            if previous.game or previous.starting:raise ValueError("你已有正在进行或即将开始的比赛")
            self.leave(previous,user.id,explicit=True)
        existing=next((s for s in room.slots if s.get("user_id")==user.id),None)
        if existing:return
        if room.starting:raise ValueError("比赛正在开始，暂时无法加入")
        if room.game:room.spectators[user.id]=user.username;return
        if len(room.slots)>=room.max_players:raise ValueError("房间已满")
        room.slots.append({"id":secrets.token_hex(3),"name":user.username,"user_id":user.id,"team":"A" if len(room.slots)%2==0 else "B","soldiers":2,"ready":False,"ai":None,"color":COLORS[len(room.slots)%len(COLORS)]}); self.user_room[user.id]=room.id
    def leave(self,room,user_id,explicit=False):
        room.say_functions.discard(user_id);room.show_next.discard(user_id);room.skip_votes.discard(user_id)
        room.spectators.pop(user_id,None)
        if room.game:
            if explicit:room.disconnected.add(user_id)
            return
        room.slots[:]=[s for s in room.slots if s.get("user_id")!=user_id]
        self.user_room.pop(user_id,None)
        if room.owner_id==user_id:
            human=next((s for s in room.slots if s.get("user_id")),None)
            if human:room.owner_id=human["user_id"];room.owner_name=human["name"]
        if not any(s.get("user_id") for s in room.slots):self.rooms.pop(room.id,None)
    def remove_room(self,room):
        self.rooms.pop(room.id,None)
        for slot in room.slots:
            uid=slot.get("user_id")
            if uid and self.user_room.get(uid)==room.id:self.user_room.pop(uid,None)
        if room.turn_task:room.turn_task.cancel()
        if room.start_task:room.start_task.cancel()
    async def broadcast(self,room,event,payload=None):
        data={"v":1,"type":event,"payload":payload if payload is not None else room.public()}; dead=[]
        for uid,ws in list(room.sockets.items()):
            try: await ws.send_json(data)
            except Exception:dead.append(uid)
        for uid in dead:room.sockets.pop(uid,None)
    async def send_user(self,room,user_id,event,payload):
        ws=room.sockets.get(user_id)
        if ws:
            try:await ws.send_json({"v":1,"type":event,"payload":payload})
            except Exception:pass
    async def run_ai(self,room):
        if room.ai_running:return
        room.ai_running=True
        try:
            while room.game and not room.game.finished and not room.game.resolving and (room.game.active().ai or room.game.active().user_id in room.disconnected):
                await asyncio.sleep(.8);actor=room.game.active();actor_id=actor.id;turn=room.game.turn;difficulty=actor.ai or "adaptive";choice=await asyncio.to_thread(choose_expression,room.game,difficulty);expr,expr_y=choice if isinstance(choice,tuple) else (choice,None)
                async with room.lock:
                    if not room.game or room.game.finished or room.game.resolving or room.game.turn!=turn or room.game.active().id!=actor_id:return
                    if not actor.ai and actor.user_id not in room.disconnected:return
                    try:result=room.game.shoot(expr,expression_y=expr_y)
                    except ExpressionError:
                        result=room.game.skip_turn();await self.broadcast(room,"timeout",result);await self.start_turn(room);return
                    await self.broadcast(room,"shot",result)
                    shown=expr if expr_y is None else f"x={expr}; y={expr_y}"
                    for uid in list(room.say_functions):await self.send_user(room,uid,"function_used",{"player":actor.name,"expression":shown})
                    if room.game.finished:self.record_match(room)
                    asyncio.create_task(self.resolve_shot(room,len(result["points"])));return
        finally:room.ai_running=False
    async def resolve_shot(self,room,point_count=0):
        task=asyncio.current_task()
        if room.turn_task and room.turn_task is not task:room.turn_task.cancel()
        await asyncio.sleep(self.resolution_seconds(point_count))
        async with room.lock:
            if not room.game:return
            room.game.resolving=False
            if not room.game.finished:
                await self.start_turn(room);asyncio.create_task(self.run_ai(room))
            else:await self.broadcast(room,"turn",room.game.snapshot())
    @staticmethod
    def resolution_seconds(point_count):return max(0,point_count)/1500+3
    async def start_turn(self,room):
        if not room.game or room.game.finished:return
        task=asyncio.current_task()
        if room.turn_task and room.turn_task is not task:room.turn_task.cancel()
        room.game.turn_deadline=time.time()+60
        expected_turn=room.game.turn;await self.broadcast(room,"turn",room.game.snapshot())
        async def timeout():
            try:
                await asyncio.sleep(60)
                async with room.lock:
                    if room.game and not room.game.finished and room.game.turn==expected_turn:
                        result=room.game.skip_turn();await self.broadcast(room,"timeout",result);await self.start_turn(room);asyncio.create_task(self.run_ai(room))
            except asyncio.CancelledError:pass
        room.turn_task=asyncio.create_task(timeout())
    async def schedule_start(self,room):
        if room.starting or room.game:raise ValueError("比赛已经在开始中")
        room.starting=True;room.start_deadline=time.time()+5
        await self.broadcast(room,"countdown",room.public())
        async def begin():
            try:
                await asyncio.sleep(5)
                async with room.lock:
                    if room.id not in self.rooms or not room.starting:return
                    room.match_sequence+=1
                    axis_half_range=room.resolved_axis_half_range(room.match_sequence)
                    room.game=Game(room.slots,room.mode,room.seed,units_per_player=room.units_per_player,function_mode=room.function_mode,axis_half_range=axis_half_range);room.match_recorded=False;room.starting=False;room.start_deadline=None
                    await self.broadcast(room,"started",room.public());await self.start_turn(room);asyncio.create_task(self.run_ai(room))
            except asyncio.CancelledError:pass
        room.start_task=asyncio.create_task(begin())
    def record_match(self,room):
        if room.match_recorded or not room.game or not room.game.finished:return
        room.match_recorded=True;game=room.game
        kills={}
        unit_owner={u.id:u.user_id for u in game.units}
        for shot in game.history:
            owner=unit_owner.get(shot["shooter"])
            if owner:kills[owner]=kills.get(owner,0)+len(shot["damages"])
        with DB() as db:
            match=Match(mode=game.mode,winner=game.winner,turns=game.turn,finished=True);db.add(match);db.flush()
            for slot in room.slots:
                uid=slot.get("user_id")
                slot_team=slot["team"] if game.mode=="teams" else str(uid or slot["id"])
                won=slot_team==game.winner
                db.add(MatchParticipant(match_id=match.id,user_id=uid,name=slot["name"],team=slot_team,soldiers=slot.get("soldiers",2),kills=kills.get(uid,0) if uid else 0,won=won,is_ai=bool(slot.get("ai"))))
                if uid:
                    stats=db.get(PlayerStats,uid)
                    if not stats:stats=PlayerStats(user_id=uid,matches=0,wins=0,kills=0,damage=0);db.add(stats)
                    stats.matches+=1;stats.kills+=kills.get(uid,0);stats.damage+=kills.get(uid,0)
                    if won:stats.wins+=1
            db.add(MatchReplay(match_id=match.id,payload=json.dumps(game.replay(),ensure_ascii=False,separators=(",",":"))))
            db.commit()
    def record_aborted(self,room):
        if room.match_recorded or not room.game or room.game.finished:return
        room.match_recorded=True
        with DB() as db:
            match=Match(mode=room.game.mode,winner=None,turns=room.game.turn,finished=False);db.add(match);db.flush()
            for slot in room.slots:db.add(MatchParticipant(match_id=match.id,user_id=slot.get("user_id"),name=slot["name"],team=slot["team"],soldiers=slot.get("soldiers",2),kills=0,won=False,is_ai=bool(slot.get("ai"))))
            db.add(MatchReplay(match_id=match.id,payload=json.dumps(room.game.replay(),ensure_ascii=False,separators=(",",":"))));db.commit()

rooms=RoomManager()
