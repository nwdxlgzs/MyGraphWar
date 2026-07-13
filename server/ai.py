import copy
import math
import random
import time

def _score(game,result,target):
    shooter=next(u for u in game.units if u.id==result["shooter"]);by_id={u.id:u for u in game.units}
    score=0.0
    for damage in result["damages"]:
        victim=by_id[damage["unit"]]
        score+=120 if victim.team!=shooter.team else -180
    points=result["points"]
    if points:
        distance=min(math.hypot(p[0]-target.x,p[1]-target.y) for p in points);score-=distance*3
        score+=min(len(points),3000)/3000
    else:score-=100
    return score

def _normal_candidates(game,shooter,target,rng,count):
    direction=1 if shooter.x<0 else -1;sx=direction*shooter.x;tx=direction*target.x;delta=tx-sx
    if abs(delta)<.01:return ["0"]
    candidates=[]
    curvatures=[0,.002,-.002,.005,-.005,.01,-.01,.02,-.02,.04,-.04]
    while len(curvatures)<count:curvatures.append(rng.uniform(-.08,.08))
    for curve in curvatures[:count]:
        slope=(target.y-shooter.y-curve*(tx*tx-sx*sx))/delta
        candidates.append(f"({slope:.8f})*x+({curve:.8f})*x^2")
    return candidates

def choose_expression(game,difficulty="medium"):
    shooter=game.active();enemies=[u for u in game.units if u.alive and u.team!=shooter.team]
    if not enemies:return "0"
    target=min(enemies,key=lambda u:math.hypot(u.x-shooter.x,u.y-shooter.y));rng=random.Random(game.seed*10000+game.turn)
    if game.function_mode=="parametric":
        direction=1 if shooter.x<0 else -1;dx=max(.01,direction*(target.x-shooter.x));slope=(target.y-shooter.y)/dx
        return ("t",f"{slope:.8f}*t")
    if difficulty=="easy":
        if game.function_mode=="polar":return rng.choice(["80*theta","200*theta","400*theta"])
        if game.function_mode=="second_order":shooter.angle=rng.uniform(-35,35);return "0"
        return rng.choice(["0","x/8","-x/10","sin(x/3)*2"])
    count={"medium":18,"hard":50,"adaptive":80}.get(difficulty,18);budget={"medium":.35,"hard":.9,"adaptive":1.5}.get(difficulty,.35)
    if game.function_mode=="normal":candidates=[(x,None) for x in _normal_candidates(game,shooter,target,rng,count)]
    elif game.function_mode=="polar":candidates=[(f"{rng.uniform(20,500):.7f}*theta",None) for _ in range(count)]
    elif game.function_mode=="first_order":
        direction=1 if shooter.x<0 else -1;delta=direction*(target.x-shooter.x);base=(target.y-shooter.y)/(delta or .01)
        candidates=[(f"{base+rng.uniform(-.8,.8):.7f}+{rng.uniform(-.12,.12):.7f}*sin(x)",None) for _ in range(count)];candidates[0]=(f"{base:.8f}",None)
    else:
        direction=1 if shooter.x<0 else -1;delta=direction*(target.x-shooter.x);base=math.degrees(math.atan2(target.y-shooter.y,max(.01,delta)))
        candidates=[]
        for i in range(count):
            angle=max(-80,min(80,base+(0 if i==0 else rng.uniform(-35,35))));accel=0 if i==0 else rng.uniform(-.15,.15)
            candidates.append((f"{accel:.7f}",angle))
    started=time.perf_counter();best=(float("-inf"),candidates[0])
    for expression,angle in candidates:
        if time.perf_counter()-started>budget:break
        trial=copy.deepcopy(game)
        try:result=trial.shoot(expression,angle);score=_score(game,result,target)
        except Exception:continue
        if score>best[0]:best=(score,(expression,angle))
    expression,angle=best[1]
    if angle is not None:shooter.angle=angle
    return expression
