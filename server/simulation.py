import ast
import math
import random
import copy
import re
from dataclasses import asdict, dataclass

FUNCS = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin,
         "acos": math.acos, "atan": math.atan, "sqrt": math.sqrt, "abs": abs,
         "exp": math.exp, "log": math.log10, "ln": math.log, "floor": math.floor,
         "ceil": math.ceil}
CONSTS = {"pi": math.pi, "e": math.e}
PLANE_WIDTH=770
PLANE_HEIGHT=450
DEFAULT_AXIS_HALF_RANGE=25.0

class ExpressionError(ValueError): pass

class SafeExpression:
    """Small numeric AST evaluator supporting GraphWar's x, y and y' variables."""
    def __init__(self, source: str, variables=("x",)):
        if not source or len(source) > 180: raise ExpressionError("表达式长度必须为 1–180")
        self.source = self._normalize(source)
        self.variables = set(variables)
        try: self.tree = ast.parse(self.source, mode="eval")
        except SyntaxError as exc: raise ExpressionError(f"语法错误：{exc.msg}") from exc
        self._check(self.tree)
    @staticmethod
    def _normalize(source):
        raw=source.lower().replace("，", ",").replace(",", ".").replace("y'","yp").replace("sen","sin").replace("tg","tan").strip()
        raw=re.sub(r"\s+","",raw).replace("^","**")
        tokens=re.findall(r"\d+(?:\.\d*)?|\.\d+|[a-z]+|\*\*|[+\-*/%()]",raw)
        if "".join(tokens)!=raw:raise ExpressionError("包含无法识别的字符")
        functions=set(FUNCS);result=[]
        for token in tokens:
            if result:
                prev=result[-1]
                prev_value=bool(re.fullmatch(r"\d+(?:\.\d*)?|\.\d+|[a-z]+|\)",prev))
                next_value=bool(re.fullmatch(r"\d+(?:\.\d*)?|\.\d+|[a-z]+|\(",token))
                function_call=prev in functions and token=="("
                if prev_value and next_value and not function_call:result.append("*")
            result.append(token)
        return "".join(result)
    def _check(self, node):
        allowed=(ast.Expression,ast.BinOp,ast.UnaryOp,ast.Constant,ast.Name,ast.Call,
                 ast.Load,ast.Add,ast.Sub,ast.Mult,ast.Div,ast.Pow,ast.Mod,ast.USub,ast.UAdd)
        if not isinstance(node, allowed): raise ExpressionError("包含不允许的语法")
        if isinstance(node, ast.Name) and node.id not in self.variables|set(FUNCS)|set(CONSTS): raise ExpressionError(f"未知名称：{node.id}")
        if isinstance(node, ast.Call) and (not isinstance(node.func,ast.Name) or node.func.id not in FUNCS or len(node.args)!=1): raise ExpressionError("只允许单参数数学函数")
        if isinstance(node, ast.Constant) and not isinstance(node.value,(int,float)): raise ExpressionError("只允许数字常量")
        if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Pow) and isinstance(node.right,ast.Constant) and abs(node.right.value)>16: raise ExpressionError("幂指数过大")
        for child in ast.iter_child_nodes(node): self._check(child)
    def eval(self, *args, **values):
        if args:
            if len(args)!=1 or len(self.variables)!=1: raise ExpressionError("参数数量错误")
            values[next(iter(self.variables))]=args[0]
        try: result=self._eval(self.tree.body,values)
        except (ValueError,OverflowError,ZeroDivisionError,TypeError) as exc: raise ExpressionError("函数在该点无定义") from exc
        if not math.isfinite(result) or abs(result)>1e6: raise ExpressionError("函数值超出范围")
        return float(result)
    def _eval(self,node,v):
        if isinstance(node,ast.Constant): return node.value
        if isinstance(node,ast.Name): return v[node.id] if node.id in self.variables else CONSTS[node.id]
        if isinstance(node,ast.UnaryOp): return -self._eval(node.operand,v) if isinstance(node.op,ast.USub) else self._eval(node.operand,v)
        if isinstance(node,ast.Call): return FUNCS[node.func.id](self._eval(node.args[0],v))
        a,b=self._eval(node.left,v),self._eval(node.right,v)
        return {ast.Add:lambda:a+b,ast.Sub:lambda:a-b,ast.Mult:lambda:a*b,
                ast.Div:lambda:a/b,ast.Pow:lambda:a**b,ast.Mod:lambda:a%b}[type(node.op)]()

@dataclass
class Unit:
    id:str; name:str; team:str; x:float; y:float; hp:int=1; ai:str|None=None
    user_id:int|None=None; alive:bool=True; player_key:str=""; soldier_index:int=0
    angle:float=0.0; last_function:str=""
    last_function_y:str=""
    color:str="#2496d8"

@dataclass
class Obstacle:
    id:str; x:float; y:float; radius:float
    shape:str="circle"; width:float|None=None; height:float|None=None; rotation:float=0.0

class Game:
    def __init__(self,slots,mode="teams",seed=1,width=1000,height=600,units_per_player=2,function_mode="normal",axis_half_range=DEFAULT_AXIS_HALF_RANGE):
        self.mode=mode; self.seed=seed; self.width=width; self.height=height
        self.axis_half_range=max(1.0,min(100.0,float(axis_half_range)))
        self.game_width=self.axis_half_range*2
        self.bounds=(-self.axis_half_range,self.axis_half_range,-(PLANE_HEIGHT/2)*self.game_width/PLANE_WIDTH,(PLANE_HEIGHT/2)*self.game_width/PLANE_WIDTH)
        self.scale=self.axis_half_range/DEFAULT_AXIS_HALF_RANGE
        self.soldier_radius=7*self.game_width/PLANE_WIDTH
        self.explosion_radius=12*self.game_width/PLANE_WIDTH
        self.base_step=.01*self.scale;self.edge_step=.001*self.scale;self.min_step=.00001*self.scale
        self.max_step_distance_squared=.001*self.scale*self.scale
        self.function_mode=function_mode if function_mode in ("normal","first_order","second_order","polar","parametric") else "normal"
        self.turn=0; self.finished=False; self.winner=None; self.history=[]; self.current=0;self.turn_deadline=None;self.resolving=False
        rng=random.Random(seed); self.obstacles=self._make_obstacles(rng);self.craters=[]
        slots=self._reorder_slots(slots,rng) if mode=="teams" else list(slots)
        units_per_player=max(1,min(4,units_per_player)); self.units=[];specs=[];self.player_order=[str(s.get("user_id") or s.get("id") or s["name"]) for s in slots];self.player_cursor=rng.randrange(len(self.player_order)) if self.player_order else 0;self.soldier_cursors={key:0 for key in self.player_order}
        for round_index in range(4):
            for slot in slots:
                if round_index<int(slot.get("soldiers",units_per_player)):specs.append((slot,round_index))
        positions=self._spawn_positions(specs,rng)
        for i,(slot_round,position) in enumerate(zip(specs,positions)):
                slot,round_index=slot_round;x,y=position
                team=slot["team"] if mode=="teams" else str(slot.get("user_id") or slot.get("id") or slot["name"])
                suffix=f" #{round_index+1}" if int(slot.get("soldiers",units_per_player))>1 else ""
                key=str(slot.get("user_id") or slot.get("id") or slot["name"])
                self.units.append(Unit(str(i+1),slot["name"]+suffix,team,x,y,ai=slot.get("ai"),user_id=slot.get("user_id"),player_key=key,soldier_index=round_index,color=slot.get("color","#2496d8")))
        if self.units:
            start_key=self.player_order[self.player_cursor];self.current=next(i for i,u in enumerate(self.units) if u.player_key==start_key);self.soldier_cursors[start_key]=1
        self.initial_state=copy.deepcopy(self.snapshot())
    def replay(self):return {"version":1,"initial":self.initial_state,"shots":copy.deepcopy(self.history),"final":self.snapshot()}
    @staticmethod
    def _reorder_slots(slots,rng):
        queues={"A":[s for s in slots if s.get("team")=="A"],"B":[s for s in slots if s.get("team")=="B"]};team=rng.choice(("A","B"));result=[]
        while queues["A"] or queues["B"]:
            if queues[team]:result.append(queues[team].pop(0))
            team="B" if team=="A" else "A"
            if not queues[team] and queues["B" if team=="A" else "A"]:team="B" if team=="A" else "A"
        return result
    def _make_obstacles(self,rng):
        result=[];style_rng=random.Random(f"{self.seed}:obstacle-style")
        count=max(1,int(round(rng.gauss(15,7))))
        for i in range(count):
            radius=max(.15*self.scale,rng.gauss(40,25)*self.game_width/PLANE_WIDTH)
            x=rng.uniform(self.bounds[0],self.bounds[1]);y=rng.uniform(self.bounds[2],self.bounds[3])
            shape=style_rng.choice(("circle","circle","ellipse","rectangle","diamond"))
            width=radius*2*style_rng.uniform(.85,1.65);height=radius*2*style_rng.uniform(.65,1.35)
            result.append(Obstacle(str(i+1),x,y,radius,shape,round(width,4),round(height,4),round(style_rng.uniform(0,math.pi),4)))
        return result
    def _spawn_positions(self,specs,rng):
        positions=[]
        for i,(slot,_round) in enumerate(specs):
            side=-1 if slot.get("team","A")=="A" else 1
            for _ in range(1000):
                x=side*rng.uniform(self.soldier_radius,self.axis_half_range-self.soldier_radius);y=rng.uniform(self.bounds[2]+self.soldier_radius,self.bounds[3]-self.soldier_radius)
                if not self._collides_obstacle(x,y,15*self.game_width/PLANE_WIDTH) and all(abs(x-a)>=20*self.game_width/PLANE_WIDTH or abs(y-b)>=20*self.game_width/PLANE_WIDTH for a,b in positions):break
            positions.append((round(x,3),round(y,3)))
        return positions
    def _collides_obstacle(self,x,y,padding=0):
        solid=any(self._inside_obstacle(o,x,y,padding) for o in self.obstacles)
        removed=any(math.hypot(x-c[0],y-c[1])<=c[2] for c in self.craters)
        return solid and not removed
    @staticmethod
    def _inside_obstacle(obstacle,x,y,padding=0):
        dx=x-obstacle.x;dy=y-obstacle.y
        if obstacle.shape=="circle":return math.hypot(dx,dy)<=obstacle.radius+padding
        angle=-obstacle.rotation;local_x=dx*math.cos(angle)-dy*math.sin(angle);local_y=dx*math.sin(angle)+dy*math.cos(angle)
        half_width=(obstacle.width or obstacle.radius*2)/2+padding;half_height=(obstacle.height or obstacle.radius*2)/2+padding
        if obstacle.shape=="ellipse":return (local_x/half_width)**2+(local_y/half_height)**2<=1
        if obstacle.shape=="diamond":return abs(local_x)/half_width+abs(local_y)/half_height<=1
        return abs(local_x)<=half_width and abs(local_y)<=half_height
    def active(self): return self.units[self.current]
    def snapshot(self):
        return {"mode":self.mode,"function_mode":self.function_mode,"seed":self.seed,"bounds":self.bounds,
                "width":self.width,"height":self.height,"obstacles":[asdict(o) for o in self.obstacles],"craters":self.craters,
                "units":[asdict(u) for u in self.units],"current":self.active().id if not self.finished else None,
                "next_units":self.next_units(),"turn":self.turn,"turn_deadline":self.turn_deadline,"resolving":self.resolving,"finished":self.finished,"winner":self.winner}
    def next_units(self):
        result=[]
        for key in self.player_order:
            alive=[u for u in self.units if u.player_key==key and u.alive]
            if not alive:continue
            wanted=self.soldier_cursors[key]%max(1,len([u for u in self.units if u.player_key==key]))
            result.append(min(alive,key=lambda u:(u.soldier_index-wanted)%4).id)
        return result
    def skip_turn(self):
        if self.finished:return
        skipped=self.active().id;self.turn+=1;self._advance();self._winner();return {"skipped":skipped,"state":self.snapshot()}
    def shoot(self,expression,angle=None,expression_y=None):
        if self.finished: raise ExpressionError("对局已结束")
        if self.function_mode in ("polar","parametric"):return self._shoot_extended(expression,expression_y)
        shooter=self.active(); direction=1 if shooter.x<0 else -1
        if angle is None:angle=shooter.angle
        angle=max(-80,min(80,float(angle)));shooter.angle=angle;shooter.last_function=expression
        expr=SafeExpression(expression,("x",)) if self.function_mode=="normal" else SafeExpression(expression,("x","y") if self.function_mode=="first_order" else ("x","y","yp"))
        points=[]; hit=None; exploded=False; x=shooter.x; y=shooter.y;hit_units=[]
        local_x=direction*x;h=self.base_step
        try:
            if self.function_mode=="normal":
                epsilon=.0001;slope=(expr.eval(x=local_x+epsilon)-expr.eval(x=local_x-epsilon))/(2*epsilon);fire_angle=math.atan(slope)
                local_x+=self.soldier_radius*math.cos(fire_angle);y+=self.soldier_radius*math.sin(fire_angle);x=direction*local_x;offset=y-expr.eval(x=local_x)
            elif self.function_mode=="first_order":
                center_x,center_y=local_x,y;edge_step=self.edge_step
                while math.hypot(local_x-center_x,y-center_y)<self.soldier_radius:
                    k1=expr.eval(x=local_x,y=y);k2=expr.eval(x=local_x+edge_step/2,y=y+edge_step*k1/2);k3=expr.eval(x=local_x+edge_step/2,y=y+edge_step*k2/2);k4=expr.eval(x=local_x+edge_step,y=y+edge_step*k3)
                    y+=edge_step*(k1+2*k2+2*k3+k4)/6;local_x+=edge_step
                fire_angle=math.atan2(y-center_y,local_x-center_x);x=direction*local_x
            else:
                fire_angle=math.radians(angle);yp=math.tan(fire_angle);local_x+=self.soldier_radius*math.cos(fire_angle);y+=self.soldier_radius*math.sin(fire_angle);x=direction*local_x
            for _ in range(20000):
                old=(x,y);old_local=local_x;step=h
                if self.function_mode=="normal":
                    while True:
                        next_local=old_local+step;next_y=expr.eval(x=next_local)+offset
                        if (step*step+(next_y-y)**2)<=self.max_step_distance_squared or step<=self.min_step:break
                        step/=2
                    local_x=next_local;x=direction*local_x;y=next_y
                elif self.function_mode=="first_order":
                    while True:
                        k1=expr.eval(x=old_local,y=old[1]);k2=expr.eval(x=old_local+step/2,y=old[1]+step*k1/2);k3=expr.eval(x=old_local+step/2,y=old[1]+step*k2/2);k4=expr.eval(x=old_local+step,y=old[1]+step*k3)
                        next_y=old[1]+step*(k1+2*k2+2*k3+k4)/6
                        if step*step+(next_y-old[1])**2<=self.max_step_distance_squared or step<=self.min_step:break
                        step/=2
                    y=next_y;local_x=old_local+step;x=direction*local_x
                else:
                    def acceleration(lx,ly,slope):return expr.eval(x=lx,y=ly,yp=slope)
                    while True:
                        k1y=yp;k1v=acceleration(old_local,old[1],yp)
                        k2y=yp+step*k1v/2;k2v=acceleration(old_local+step/2,old[1]+step*k1y/2,yp+step*k1v/2)
                        k3y=yp+step*k2v/2;k3v=acceleration(old_local+step/2,old[1]+step*k2y/2,yp+step*k2v/2)
                        k4y=yp+step*k3v;k4v=acceleration(old_local+step,old[1]+step*k3y,yp+step*k3v)
                        next_y=old[1]+step*(k1y+2*k2y+2*k3y+k4y)/6;next_yp=yp+step*(k1v+2*k2v+2*k3v+k4v)/6
                        if step*step+(next_y-old[1])**2<=self.max_step_distance_squared or step<=self.min_step:break
                        step/=2
                    y=next_y;yp=next_yp;local_x=old_local+step;x=direction*local_x
                if not (self.bounds[0]<=x<=self.bounds[1] and self.bounds[2]<=y<=self.bounds[3]): break
                points.append([round(x,4),round(y,4)])
                for u in self.units:
                    if u.alive and u.id!=shooter.id and u.id not in hit_units and math.hypot(x-u.x,y-u.y)<=self.soldier_radius:hit_units.append(u.id)
                if self._collides_obstacle(x,y):hit=(x,y);break
        except ExpressionError: exploded=True; hit=(x,y)
        damages=[]
        for u in self.units:
            if u.id in hit_units:u.hp=0;u.alive=False;damages.append({"unit":u.id,"damage":1,"hp":0})
        if hit:self.craters.append([round(hit[0],4),round(hit[1],4),round(self.explosion_radius,4)])
        self.turn+=1;self._advance();self._winner();self.resolving=not self.finished;self.turn_deadline=None
        result={"function_mode":self.function_mode,"expression":expression,"angle":angle,"shooter":shooter.id,
                "points":points,"impact":[round(v,4) for v in hit] if hit else (points[-1] if points else [shooter.x,shooter.y]),
                "exploded":exploded,"damages":damages,"state":self.snapshot()}
        self.history.append(result);return result
    def _shoot_extended(self,expression,expression_y=None):
        shooter=self.active();direction=1 if shooter.x<0 else -1;points=[];hit=None;hit_units=[];exploded=False
        if self.function_mode=="polar":
            radial=SafeExpression(expression,("theta",));base=radial.eval(theta=0);samples=[]
            for i in range(1,20001):
                theta=i*.0025;r=radial.eval(theta=theta)-base+self.soldier_radius
                samples.append((shooter.x+direction*r*math.cos(theta),shooter.y+r*math.sin(theta)))
                if theta>=math.tau*3:break
        else:
            fx=SafeExpression(expression,("t",));fy=SafeExpression(expression_y or "0",("t",));x0=fx.eval(t=0);y0=fy.eval(t=0);samples=[]
            for i in range(1,20001):
                t=i*.005*self.scale;lx=fx.eval(t=t)-x0;ly=fy.eval(t=t)-y0
                samples.append((shooter.x+direction*lx,shooter.y+ly))
        try:
            for x,y in samples:
                if not (self.bounds[0]<=x<=self.bounds[1] and self.bounds[2]<=y<=self.bounds[3]):break
                if math.hypot(x-shooter.x,y-shooter.y)<self.soldier_radius:continue
                points.append([round(x,4),round(y,4)])
                for u in self.units:
                    if u.alive and u.id!=shooter.id and u.id not in hit_units and math.hypot(x-u.x,y-u.y)<=self.soldier_radius:hit_units.append(u.id)
                if self._collides_obstacle(x,y):hit=(x,y);break
        except ExpressionError:exploded=True
        damages=[]
        for u in self.units:
            if u.id in hit_units:u.hp=0;u.alive=False;damages.append({"unit":u.id,"damage":1,"hp":0})
        if hit:self.craters.append([round(hit[0],4),round(hit[1],4),round(self.explosion_radius,4)])
        shooter.last_function=expression;shooter.last_function_y=expression_y or "";self.turn+=1;self._advance();self._winner();self.resolving=not self.finished;self.turn_deadline=None
        result={"function_mode":self.function_mode,"expression":expression,"expression_y":expression_y,"angle":0,"shooter":shooter.id,"points":points,"impact":[round(v,4) for v in hit] if hit else (points[-1] if points else [shooter.x,shooter.y]),"exploded":exploded,"damages":damages,"state":self.snapshot()}
        self.history.append(result);return result
    def _advance(self):
        for _ in self.player_order:
            self.player_cursor=(self.player_cursor+1)%len(self.player_order);key=self.player_order[self.player_cursor]
            alive=[(i,u) for i,u in enumerate(self.units) if u.player_key==key and u.alive]
            if not alive:continue
            wanted=self.soldier_cursors[key]%max(1,len([u for u in self.units if u.player_key==key]))
            choices=sorted(alive,key=lambda pair:(pair[1].soldier_index-wanted)%4)
            self.current=choices[0][0];self.soldier_cursors[key]=self.units[self.current].soldier_index+1;return
    def _winner(self):
        alive={u.team for u in self.units if u.alive}
        if len(alive)<=1:self.finished=True;self.winner=next(iter(alive),None)
