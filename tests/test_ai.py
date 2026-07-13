import time
from server.ai import choose_expression
from server.simulation import Game,SafeExpression

def make_game(mode="normal"):
    slots=[{"id":"a","name":"A","team":"A","soldiers":1,"ai":"hard"},{"id":"b","name":"B","team":"B","soldiers":1}]
    game=Game(slots,seed=91,units_per_player=1,function_mode=mode);game.obstacles=[]
    shooter=game.active();target=next(u for u in game.units if u.team!=shooter.team)
    shooter.x=-10 if shooter.team=="A" else 10;shooter.y=0;target.x=8 if shooter.team=="A" else -8;target.y=4
    return game,target

def test_hard_ai_uses_authoritative_simulation_and_hits_clear_target():
    game,target=make_game();expression=choose_expression(game,"hard")
    SafeExpression(expression);result=game.shoot(expression)
    assert any(d["unit"]==target.id for d in result["damages"])

def test_ai_difficulty_has_strict_time_budget():
    game,_=make_game();started=time.perf_counter();choose_expression(game,"adaptive")
    assert time.perf_counter()-started<2.5

def test_second_order_ai_sets_persistent_firing_angle():
    game,_=make_game("second_order");expression=choose_expression(game,"medium")
    assert expression and -80<=game.active().angle<=80

def test_extension_ai_uses_correct_variables():
    polar,_=make_game("polar");polar_expression=choose_expression(polar,"easy")
    assert "theta" in polar_expression;SafeExpression(polar_expression,("theta",))
    parametric,_=make_game("parametric");x_expr,y_expr=choose_expression(parametric,"hard")
    SafeExpression(x_expr,("t",));SafeExpression(y_expr,("t",))
