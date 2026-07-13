import math
import pytest
from server.simulation import SafeExpression,ExpressionError,Game,Obstacle

def test_safe_expression():
    assert SafeExpression("sin(pi/2)+x^2").eval(2)==pytest.approx(5)
    for bad in ["__import__('os')","x.__class__","[x for x in [1]]",""]:
        with pytest.raises(ExpressionError):SafeExpression(bad)

def test_original_parser_compatibility():
    assert SafeExpression("2x+3(x+1)").eval(2)==pytest.approx(13)
    assert SafeExpression("sen(pi/2)+tg(0)").eval(0)==pytest.approx(1)
    assert SafeExpression("1,5*x").eval(2)==pytest.approx(3)
    assert SafeExpression("log(100)+ln(e)").eval(0)==pytest.approx(3)
    assert SafeExpression("exp(1)").eval(0)==pytest.approx(math.e)
    with pytest.raises(ExpressionError):SafeExpression("x;import os")

def test_deterministic_game():
    slots=[{"name":"A","team":"A"},{"name":"B","team":"B"}]
    a,b=Game(slots,seed=42),Game(slots,seed=42)
    assert a.snapshot()==b.snapshot()
    assert a.shoot("0.3*x-0.005*x^2")["points"]==b.shoot("0.3*x-0.005*x^2")["points"]

def test_twenty_players():
    slots=[{"name":str(i),"team":str(i%3)} for i in range(20)]
    game=Game(slots,mode="ffa",seed=7,units_per_player=1)
    assert len(game.units)==20

def test_original_cartesian_rules_and_obstacles():
    slots=[{"id":"a","name":"A","team":"A"},{"id":"b","name":"B","team":"B"}]
    game=Game(slots,seed=11,units_per_player=3,function_mode="normal")
    assert len(game.units)==6
    assert len(game.obstacles)>=5
    assert game.snapshot()["bounds"][0:2]==(-25.0,25.0)
    assert game.snapshot()["bounds"][2]==pytest.approx(-14.6103896)
    shooter=game.active()
    result=game.shoot("0")
    assert result["points"][0][1]==pytest.approx(shooter.y,abs=.001)

def test_configurable_coordinate_range_scales_the_whole_simulation():
    slots=[{"id":"a","name":"A","team":"A"},{"id":"b","name":"B","team":"B"}]
    default=Game(slots,seed=111,units_per_player=1)
    compact=Game(slots,seed=111,units_per_player=1,axis_half_range=5)
    assert compact.snapshot()["bounds"][:2]==(-5.0,5.0)
    assert compact.snapshot()["bounds"][3]==pytest.approx(5*450/770)
    assert compact.soldier_radius==pytest.approx(default.soldier_radius/5)
    assert compact.explosion_radius==pytest.approx(default.explosion_radius/5)
    assert all(compact.bounds[0]<u.x<compact.bounds[1] and compact.bounds[2]<u.y<compact.bounds[3] for u in compact.units)
    compact.obstacles=[]
    result=compact.shoot("0")
    assert result["points"] and all(compact.bounds[0]<=p[0]<=compact.bounds[1] for p in result["points"])

def test_classic_spawn_uses_full_team_half_plane():
    slots=[{"id":"a","name":"A","team":"A","soldiers":4},{"id":"b","name":"B","team":"B","soldiers":4}]
    samples=[]
    for seed in range(10,30):samples.extend(Game(slots,seed=seed).units)
    assert all(u.x<0 for u in samples if u.team=="A") and all(u.x>0 for u in samples if u.team=="B")
    assert any(-10<u.x<0 for u in samples if u.team=="A")
    assert any(0<u.x<10 for u in samples if u.team=="B")

def test_differential_equation_modes():
    slots=[{"id":"a","name":"A","team":"A"},{"id":"b","name":"B","team":"B"}]
    first=Game(slots,seed=12,units_per_player=1,function_mode="first_order")
    assert first.shoot("0.5")["function_mode"]=="first_order"
    second=Game(slots,seed=12,units_per_player=1,function_mode="second_order")
    assert second.shoot("-y",angle=25)["angle"]==25

def test_original_direct_hit_kills_without_stopping_curve():
    slots=[{"id":"a","name":"A","team":"A"},{"id":"b","name":"B","team":"B"}]
    game=Game(slots,seed=4,units_per_player=1)
    game.obstacles=[];game.units[0].x=-10;game.units[0].y=0;game.units[1].x=0;game.units[1].y=0
    result=game.shoot("0")
    assert not game.units[1].alive and game.units[1].hp==0
    assert result["points"][-1][0]>game.units[1].x

def test_original_circle_obstacle_gets_crater():
    slots=[{"id":"a","name":"A","team":"A"},{"id":"b","name":"B","team":"B"}]
    game=Game(slots,seed=5,units_per_player=1)
    game.units[0].x=-10;game.units[0].y=0;game.units[1].y=10
    game.obstacles=[Obstacle("wall",0,0,2)];game.craters=[]
    result=game.shoot("0")
    assert result["impact"][0]==pytest.approx(-2,abs=.05)
    assert len(game.craters)==1

def test_varied_obstacle_shapes_use_authoritative_collision_and_local_craters():
    slots=[{"id":"a","name":"A","team":"A"},{"id":"b","name":"B","team":"B"}]
    game=Game(slots,seed=51,units_per_player=1)
    shapes=[
        Obstacle("ellipse",0,0,2,"ellipse",6,2,0),
        Obstacle("rectangle",8,0,2,"rectangle",4,6,0),
        Obstacle("diamond",-8,0,2,"diamond",6,4,0),
    ]
    game.obstacles=shapes;game.craters=[]
    assert game._collides_obstacle(2.5,0)
    assert game._collides_obstacle(8,2.5)
    assert game._collides_obstacle(-8,1.5)
    assert not game._collides_obstacle(0,1.5)
    game.craters=[[2.5,0,game.explosion_radius]]
    assert not game._collides_obstacle(2.5,0)
    assert game._collides_obstacle(-2.5,0)

def test_turn_timeout_skips_without_firing():
    slots=[{"id":"a","name":"A","team":"A"},{"id":"b","name":"B","team":"B"}]
    game=Game(slots,seed=8,units_per_player=1)
    first=game.active().id;result=game.skip_turn()
    assert result["skipped"]==first and game.turn==1 and game.active().id!=first

def test_rk4_first_order_accuracy():
    slots=[{"id":"a","name":"A","team":"A"},{"id":"b","name":"B","team":"B"}]
    game=Game(slots,seed=20,units_per_player=1,function_mode="first_order")
    game.current=next(i for i,u in enumerate(game.units) if u.player_key=="a")
    game.obstacles=[];game.units[game.current].x=-10;game.units[game.current].y=1
    for i,u in enumerate(game.units):
        if i!=game.current:u.y=12
    points=game.shoot("y")["points"]
    local_delta=abs(points[99][0]-(-10))
    assert points[99][1]==pytest.approx(math.exp(local_delta),rel=.002)

def test_right_team_uses_mirrored_function_coordinates():
    slots=[{"id":"a","name":"A","team":"A"},{"id":"b","name":"B","team":"B"}]
    left=Game(slots,seed=21,units_per_player=1);right=Game(slots,seed=21,units_per_player=1)
    for game in (left,right):game.obstacles=[];game.units[0].x=-10;game.units[0].y=0;game.units[1].x=10;game.units[1].y=0
    right.current=1
    lp=left.shoot("x^2/20")["points"][0];rp=right.shoot("x^2/20")["points"][0]
    assert lp[1]==pytest.approx(rp[1],abs=1e-6)
    assert lp[0]+rp[0]==pytest.approx(0,abs=1e-6)

def test_rk4_second_order_accuracy():
    slots=[{"id":"a","name":"A","team":"A"},{"id":"b","name":"B","team":"B"}]
    game=Game(slots,seed=22,units_per_player=1,function_mode="second_order")
    game.obstacles=[];game.units[0].x=-10;game.units[0].y=1;game.units[1].y=12
    points=game.shoot("-y",angle=0)["points"]
    assert points[99][1]==pytest.approx(math.cos(1),rel=.002)
    assert game.resolving and game.turn_deadline is None

def test_players_alternate_even_with_different_soldier_counts():
    slots=[{"id":"a","name":"A","team":"A","soldiers":1},{"id":"b","name":"B","team":"B","soldiers":3}]
    game=Game(slots,seed=30)
    sequence=[]
    for _ in range(6):
        sequence.append(game.active().player_key);game.skip_turn()
    assert all(sequence[i]!=sequence[i+1] for i in range(len(sequence)-1))
    b_indices=[]
    game=Game(slots,seed=30)
    for _ in range(6):
        if game.active().player_key=="b":b_indices.append(game.active().soldier_index)
        game.skip_turn()
    assert sorted(b_indices)==[0,1,2]

def test_soldier_remembers_angle_and_last_function():
    slots=[{"id":"a","name":"A","team":"A","soldiers":1},{"id":"b","name":"B","team":"B","soldiers":1}]
    game=Game(slots,seed=71,function_mode="second_order");game.obstacles=[]
    shooter=game.active();game.shoot("-y",angle=27)
    assert shooter.angle==27 and shooter.last_function=="-y"
    snapshot=game.snapshot();saved=next(u for u in snapshot["units"] if u["id"]==shooter.id)
    assert saved["angle"]==27 and saved["last_function"]=="-y"

def test_snapshot_lists_each_players_next_soldier():
    slots=[{"id":"a","name":"A","team":"A","soldiers":2},{"id":"b","name":"B","team":"B","soldiers":2}]
    game=Game(slots,seed=72);snapshot=game.snapshot()
    assert len(snapshot["next_units"])==2
    assert all(any(u.id==unit_id and u.alive for u in game.units) for unit_id in snapshot["next_units"])

def test_extended_polar_curve_uses_soldier_local_origin():
    slots=[{"id":"a","name":"A","team":"A","soldiers":1},{"id":"b","name":"B","team":"B","soldiers":1}]
    game=Game(slots,mode="ffa",seed=401,units_per_player=1,function_mode="polar");game.obstacles=[]
    shooter=game.active();target=next(u for u in game.units if u.id!=shooter.id);shooter.x=-10;shooter.y=0;target.x=0;target.y=.25
    result=game.shoot("400*theta")
    assert result["function_mode"]=="polar" and any(d["unit"]==target.id for d in result["damages"])

def test_extended_parametric_curve_and_replay_preserve_both_expressions():
    slots=[{"id":"a","name":"A","team":"A","soldiers":1},{"id":"b","name":"B","team":"B","soldiers":1}]
    game=Game(slots,mode="ffa",seed=402,units_per_player=1,function_mode="parametric");game.obstacles=[]
    shooter=game.active();target=next(u for u in game.units if u.id!=shooter.id);shooter.y=0;direction=1 if shooter.x<0 else -1;target.x=shooter.x+direction*8;target.y=2
    result=game.shoot("t",expression_y="t/4")
    assert any(d["unit"]==target.id for d in result["damages"])
    assert game.replay()["shots"][0]["expression_y"]=="t/4"
    assert shooter.last_function=="t" and shooter.last_function_y=="t/4"
