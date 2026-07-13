import asyncio
import time
from .rooms import rooms
from .simulation import Game
from .simulation import SafeExpression,ExpressionError

async def handle_room_message(room,user,ws,msg):
    """Handle exactly one client message; callers isolate validation failures per message."""
    typ=msg.get("type");payload=msg.get("payload") or {}
    if not isinstance(payload,dict):raise ValueError("消息负载必须是对象")
    async with room.lock:
        slot=next((s for s in room.slots if s.get("user_id")==user.id),None)
        if typ=="leave":rooms.leave(room,user.id,explicit=True);await rooms.broadcast(room,"snapshot");return "leave"
        if typ=="ping":await ws.send_json({"v":1,"type":"pong","payload":{}});return
        if typ=="validate_expression":
            if not room.game:raise ValueError("对局尚未开始")
            mode=room.game.function_mode;expression=str(payload.get("expression",""));expression_y=str(payload.get("expression_y",""))
            try:
                variables={"normal":("x",),"first_order":("x","y"),"second_order":("x","y","yp"),"polar":("theta",),"parametric":("t",)}[mode]
                SafeExpression(expression,variables)
                if mode=="parametric":SafeExpression(expression_y,("t",))
                await rooms.send_user(room,user.id,"validation",{"ok":True,"message":"表达式有效"})
            except ExpressionError as exc:await rooms.send_user(room,user.id,"validation",{"ok":False,"message":str(exc)})
            return
        if not slot and typ not in ("ping","chat"):raise ValueError("观战者只能查看对局和聊天")
        if typ=="ready":
            if not slot or room.game or room.starting:raise ValueError("现在不能修改准备状态")
            slot["ready"]=bool(payload.get("ready"));await rooms.broadcast(room,"snapshot");return
        if typ=="chat":
            text=str(payload.get("text", ""))[:300].strip()
            if not text:return
            if not text.startswith("-"):
                key=(user.id,"chat");now=time.monotonic();last=room.last_actions.get(key,0)
                if now-last<.35:raise ValueError("聊天过于频繁，请稍后再试")
                room.last_actions[key]=now
            if text=="-sayfunc":room.say_functions.add(user.id);await rooms.send_user(room,user.id,"system",{"message":"已显示所有玩家使用的函数"});return
            elif text=="-stopsayfunc":room.say_functions.discard(user.id);await rooms.send_user(room,user.id,"system",{"message":"已停止显示其他玩家函数"});return
            elif text=="-shownext":room.show_next.add(user.id);await rooms.send_user(room,user.id,"preference",{"show_next":True});return
            elif text=="-stopshownext":room.show_next.discard(user.id);await rooms.send_user(room,user.id,"preference",{"show_next":False});return
            elif text=="-skip" and room.game:
                room.skip_votes.add(user.id);humans={s["user_id"] for s in room.slots if s.get("user_id")}
                text=f"请求跳过地图（{len(room.skip_votes)}/{len(humans)}）"
                if humans<=room.skip_votes:
                    room.seed+=1
                    axis_half_range=room.resolved_axis_half_range("skip")
                    room.game=Game(room.slots,room.mode,room.seed,units_per_player=room.units_per_player,function_mode=room.function_mode,axis_half_range=axis_half_range);room.skip_votes.clear();await rooms.broadcast(room,"started")
            room.chat.append({"from":user.username,"text":text});await rooms.broadcast(room,"chat",room.chat[-1]);return
        if typ=="configure":
            if user.id!=room.owner_id or room.game or room.starting:raise ValueError("只有房主能在开局前修改设置")
            if "mode" in payload:
                if payload["mode"] not in ("teams","ffa"):raise ValueError("无效对局模式")
                if room.ruleset=="classic" and payload["mode"]!="teams":raise ValueError("经典规则只支持 A/B 团队战")
                room.mode=payload["mode"]
            if "units_per_player" in payload:room.units_per_player=max(1,min(4,int(payload["units_per_player"])))
            if "axis_half_range" in payload:
                import math
                value=float(payload["axis_half_range"])
                if not math.isfinite(value) or not 1<=value<=100:raise ValueError("自定义坐标半范围必须在 1～100 之间")
                room.axis_half_range=round(value,2)
            if "axis_range_mode" in payload:
                if payload["axis_range_mode"] not in ("fixed","random"):raise ValueError("无效坐标范围模式")
                room.axis_range_mode=payload["axis_range_mode"]
            if "function_mode" in payload:
                allowed=("normal","first_order","second_order") if room.ruleset=="classic" else ("normal","first_order","second_order","polar","parametric")
                if payload["function_mode"] not in allowed:raise ValueError("该规则集不支持此函数模式")
                room.function_mode=payload["function_mode"]
            if slot_id:=payload.get("slot_id"):
                target=next((s for s in room.slots if s["id"]==slot_id),None)
                if not target:raise ValueError("席位不存在")
                if "team" in payload:
                    if payload["team"] not in ("A","B"):raise ValueError("原版模式只支持 A、B 两队")
                    target["team"]=payload["team"]
                if "soldiers" in payload:target["soldiers"]=max(1,min(4,int(payload["soldiers"])))
                if "color" in payload:
                    import re
                    if not re.fullmatch(r"#[0-9a-fA-F]{6}",str(payload["color"])):raise ValueError("颜色格式无效")
                    rgb=tuple(int(str(payload["color"])[i:i+2],16) for i in (1,3,5))
                    if sum(channel*channel for channel in rgb)>3*160*160:raise ValueError("颜色太亮，在白色地图上无法辨认")
                    target["color"]=str(payload["color"]).lower()
            await rooms.broadcast(room,"snapshot");return
        if typ=="add_ai":
            if user.id!=room.owner_id or room.game or room.starting:raise ValueError("现在不能添加电脑")
            if len(room.slots)>=room.max_players:raise ValueError("房间已满")
            difficulty=payload.get("difficulty","medium")
            if difficulty not in ("easy","medium","hard","adaptive"):raise ValueError("无效电脑难度")
            n=sum(bool(s.get("ai")) for s in room.slots)+1
            room.slots.append({"id":f"ai{n}","name":f"电脑 {n}","user_id":None,"team":"A" if len(room.slots)%2==0 else "B","soldiers":2,"ready":True,"ai":difficulty,"color":"#ffd166"});await rooms.broadcast(room,"snapshot");return
        if typ=="remove_ai":
            if user.id!=room.owner_id or room.game or room.starting:raise ValueError("现在不能移除电脑")
            before=len(room.slots);room.slots[:]=[s for s in room.slots if not(s["id"]==payload.get("slot_id") and s.get("ai"))]
            if len(room.slots)==before:raise ValueError("电脑席位不存在")
            await rooms.broadcast(room,"snapshot");return
        if typ=="kick":
            if user.id!=room.owner_id or room.game or room.starting:raise ValueError("现在不能踢出玩家")
            target_id=int(payload.get("user_id",0))
            if target_id==room.owner_id:raise ValueError("房主不能踢出自己")
            target=next((s for s in room.slots if s.get("user_id")==target_id),None)
            if not target:raise ValueError("玩家席位不存在")
            await rooms.send_user(room,target_id,"kicked",{"message":"你已被房主移出房间"});rooms.leave(room,target_id,explicit=True)
            target_ws=room.sockets.pop(target_id,None)
            if target_ws:
                try:await target_ws.close(code=4003)
                except Exception:pass
            await rooms.broadcast(room,"snapshot");return
        if typ=="start":
            if user.id!=room.owner_id or room.game or room.starting:raise ValueError("现在不能开始对局")
            if len(room.slots)<2:raise ValueError("至少需要两个参战者")
            if room.mode=="teams" and {s["team"] for s in room.slots}!={"A","B"}:raise ValueError("A、B 两队都必须至少有一名玩家")
            if any(not s["ready"] for s in room.slots if not s.get("ai") and s.get("user_id")!=room.owner_id):raise ValueError("仍有玩家未准备")
            await rooms.schedule_start(room);return
        if typ=="return_to_room":
            if user.id!=room.owner_id or not room.game or not room.game.finished:raise ValueError("现在不能返回房间")
            if room.turn_task:room.turn_task.cancel();room.turn_task=None
            room.game=None;room.match_recorded=False;room.skip_votes.clear();room.disconnected.clear()
            for member in room.slots:
                if member.get("user_id"):member["ready"]=False
            await rooms.broadcast(room,"snapshot");return
        if typ=="shoot":
            if not room.game:raise ValueError("对局尚未开始")
            if room.game.resolving:raise ValueError("上一发函数仍在结算")
            if room.game.active().user_id!=user.id:raise ValueError("还没有轮到你")
            result=room.game.shoot(str(payload.get("expression","")),float(payload.get("angle",0)),str(payload.get("expression_y","")));await rooms.broadcast(room,"shot",result)
            if room.game.finished:rooms.record_match(room)
            for uid in list(room.say_functions):await rooms.send_user(room,uid,"function_used",{"player":user.username,"expression":payload.get("expression","")})
            asyncio.create_task(rooms.resolve_shot(room,len(result["points"])));return
        if typ=="set_angle":
            if not room.game or room.game.function_mode!="second_order":raise ValueError("只有二阶微分方程模式可以调整角度")
            if room.game.resolving or room.game.active().user_id!=user.id:raise ValueError("现在不能调整角度")
            room.game.active().angle=max(-80,min(80,float(payload.get("angle",0))))
            await rooms.broadcast(room,"angle",{"unit":room.game.active().id,"angle":room.game.active().angle});return
        raise ValueError("未知消息类型")
