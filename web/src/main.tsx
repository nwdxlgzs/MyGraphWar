import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
type User = { id: number; username: string };
type Slot = {
  id: string;
  name: string;
  user_id: number | null;
  team: string;
  soldiers: number;
  ready: boolean;
  ai: string | null;
  color: string;
};
type Unit = {
  id: string;
  name: string;
  team: string;
  x: number;
  y: number;
  hp: number;
  alive: boolean;
  ai: string | null;
  user_id: number | null;
  angle: number;
  last_function: string;
  last_function_y: string;
  color: string;
};
type Obstacle = { id: string; x: number; y: number; radius: number; shape?: "circle"|"ellipse"|"rectangle"|"diamond"; width?: number|null; height?: number|null; rotation?: number };
type Game = {
  bounds: number[];
  function_mode: string;
  obstacles: Obstacle[];
  craters: number[][];
  units: Unit[];
  current: string | null;
  next_units: string[];
  turn: number;
  turn_deadline: number | null;
  resolving: boolean;
  finished: boolean;
  winner: string | null;
};
type Room = {
  id: string;
  name: string;
  owner_id: number;
  mode: string;
  ruleset: string;
  max_players: number;
  units_per_player: number;
  function_mode: string;
  axis_half_range: number;
  axis_range_mode: "fixed"|"random";
  slots: Slot[];
  spectators: { id: number; name: string }[];
  starting: boolean;
  start_deadline: number | null;
  game: Game | null;
  chat: { from: string; text: string }[];
};
const api = async (path: string, init: RequestInit = {}) => {
  const r = await fetch("/api/v1" + path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) throw new Error((await r.json()).detail || "请求失败");
  return r.json();
};
let audioContext:AudioContext|null=null;
function playSound(kind:"shot"|"blast",muted:boolean){if(muted)return;try{audioContext??=new AudioContext();void audioContext.resume();const o=audioContext.createOscillator(),g=audioContext.createGain(),now=audioContext.currentTime;o.connect(g);g.connect(audioContext.destination);if(kind==="shot"){o.type="square";o.frequency.setValueAtTime(520,now);o.frequency.exponentialRampToValueAtTime(150,now+.16);g.gain.setValueAtTime(.08,now);g.gain.exponentialRampToValueAtTime(.001,now+.18);o.start(now);o.stop(now+.19)}else{o.type="sawtooth";o.frequency.setValueAtTime(110,now);o.frequency.exponentialRampToValueAtTime(38,now+.38);g.gain.setValueAtTime(.13,now);g.gain.exponentialRampToValueAtTime(.001,now+.42);o.start(now);o.stop(now+.43)}}catch{}}
function Auth({ done }: { done: (u: User) => void }) {
  const [reg, setReg] = useState(false),
    [name, setName] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState("");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      done(
        await api(`/auth/${reg ? "register" : "login"}`, {
          method: "POST",
          body: JSON.stringify({ username: name, password }),
        }),
      );
    } catch (x) {
      setError((x as Error).message);
    }
  }
  return (
    <main className="center">
      <form className="card auth" onSubmit={submit}>
        <div className="logo">
          ∫ <b>MyGraphWar</b>
        </div>
        <p>在直角坐标系中用数学函数战斗</p>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="用户名"
        />
        <input
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          type="password"
          placeholder="密码（至少 8 位）"
        />
        {error && <div className="error">{error}</div>}
        <button>{reg ? "注册并进入" : "登录"}</button>
        <button type="button" className="ghost" onClick={() => setReg(!reg)}>
          {reg ? "已有账号？登录" : "没有账号？注册"}
        </button>
      </form>
    </main>
  );
}
function Lobby({
  user,
  enter,
  logout,
  openReplay,
}: {
  user: User;
  enter: (id: string) => void;
  logout: () => void;
  openReplay: (data: any) => void;
}) {
  const [rooms, setRooms] = useState<any[]>([]),
    [stats, setStats] = useState<any>(null),
    [matches, setMatches] = useState<any[]>([]),
    [oldPassword,setOldPassword]=useState(""),
    [newPassword,setNewPassword]=useState(""),
    [accountMessage,setAccountMessage]=useState(""),
    [replayError,setReplayError]=useState(""),
    [name, setName] = useState("函数战场"),
    [mode, setMode] = useState("teams"),
    [max, setMax] = useState(8);
  const load = () => {
    api("/rooms").then(setRooms).catch(() => {});
    api("/stats").then(setStats).catch(() => {});
    api("/matches").then(setMatches).catch(() => {});
  };
  useEffect(() => {
    load();
    const t = setInterval(load, 2000);
    return () => clearInterval(t);
  }, []);
  async function create() {
    const r = await api("/rooms", {
      method: "POST",
      body: JSON.stringify({ name, mode, ruleset: mode === "teams" ? "classic" : "extended", max_players: max }),
    });
    enter(r.id);
  }
  return (
    <main className="shell">
      <header>
        <div className="logo">
          ∫ <b>MyGraphWar</b>
        </div>
        <span>{user.username}</span>
        <button className="ghost" onClick={logout}>
          退出
        </button>
      </header>
      <section className="lobby">
        <div className="card create">
          <h2>创建战场</h2>
          <input value={name} onChange={(e) => setName(e.target.value)} />
          <div className="row">
            <select value={mode} onChange={(e) => {setMode(e.target.value);if(e.target.value==="teams")setMax(Math.min(max,10))}}>
              <option value="teams">经典规则 · A/B 团队战</option>
              <option value="ffa">扩展规则 · 自由混战</option>
            </select>
            <input
              type="number"
              min="2"
              max={mode === "teams" ? 10 : 20}
              value={max}
              onChange={(e) => setMax(+e.target.value)}
            />
          </div>
          <button onClick={create}>创建房间</button>
          {stats && <div className="stats"><b>个人战绩</b><span>{stats.matches} 场 · {stats.wins} 胜 · {stats.kills} 击杀</span></div>}
          <details><summary>账号设置</summary><div className="account-settings"><input type="password" placeholder="当前密码" value={oldPassword} onChange={e=>setOldPassword(e.target.value)}/><input type="password" placeholder="新密码（至少 8 位）" value={newPassword} onChange={e=>setNewPassword(e.target.value)}/><button onClick={async()=>{try{await api("/auth/password",{method:"POST",body:JSON.stringify({current_password:oldPassword,new_password:newPassword})});setAccountMessage("密码修改成功");setOldPassword("");setNewPassword("")}catch(e){setAccountMessage((e as Error).message)}}}>修改密码</button>{accountMessage&&<small>{accountMessage}</small>}</div></details>
        </div>
        <div className="rooms">
          <h2>在线房间</h2>
          {rooms.length ? (
            rooms.map((r) => (
              <button
                className="room card"
                key={r.id}
                onClick={() => enter(r.id)}
              >
                <b>{r.name}</b>
                <span>
                  {r.players}/{r.max_players} ·{" "}
                  {r.ruleset === "classic" ? "经典" : "扩展"} · {r.mode === "teams" ? "团队" : "混战"} ·{" "}
                  {r.status === "playing" ? "战斗中" : "等待中"}
                </span>
              </button>
            ))
          ) : (
            <div className="empty">暂无房间</div>
          )}
          <h2>最近比赛</h2>
          <label className="import-replay">导入重放 JSON<input type="file" accept="application/json,.json" onChange={async e=>{const file=e.target.files?.[0];if(!file)return;try{const data=JSON.parse(await file.text());if(data.version!==1||!data.initial||!Array.isArray(data.shots)||!data.final)throw new Error("不是有效的 MyGraphWar v1 重放");setReplayError("");openReplay(data)}catch(error){setReplayError((error as Error).message)}}}/></label>
          {replayError&&<small className="invalid">{replayError}</small>}
          {matches.length ? matches.map((m) => (
            <div className="room card" key={m.id}>
              <b>#{m.id} · {m.mode === "teams" ? "团队战" : "自由混战"}</b>
              <span>{m.turns} 回合 · 胜方 {m.winner || "无"}</span>
              <button className="tiny" onClick={async () => openReplay(await api(`/matches/${m.id}/replay`))}>播放重放</button>
            </div>
          )) : <div className="empty">暂无已完成比赛</div>}
        </div>
      </section>
    </main>
  );
}
const color = (t: string) =>
  ["#2496d8", "#df3b3b", "#dfac13", "#32a861", "#8d5fc7", "#e77c24"][
    Math.abs(t.charCodeAt(0) || 0) % 6
  ];
type Effect = { x: number; y: number; start: number; kind: "blast" | "death" };
function Battlefield({ game, trail, effects, now, showNext=false, trailFinishedAt=null, trailColor="#e52f2f" }: { game: Game; trail: number[][]; effects: Effect[]; now: number; showNext?: boolean; trailFinishedAt?: number|null;trailColor?:string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const c = ref.current;
    if (!c) return;
    const d = c.getContext("2d")!,
      minX=game.bounds?.[0]??-25,maxX=game.bounds?.[1]??25,
      minY=game.bounds?.[2]??-14.6104,maxY=game.bounds?.[3]??14.6104,
      gameWidth=maxX-minX,
      labelStep=maxX<=10?1:maxX<=25?5:10,
      px = (x: number) => ((x-minX)/gameWidth) * c.width,
      py = (y: number) => ((maxY - y) / (maxY-minY)) * c.height;
    d.fillStyle = "#ffffff";
    d.fillRect(0, 0, c.width, c.height);
    d.strokeStyle = "#e1e1e1";
    d.lineWidth = 1;
    d.font = "10px sans-serif";
    d.fillStyle = "#666";
    for (let x = Math.ceil(minX); x <= Math.floor(maxX); x++) {
      d.beginPath();
      d.moveTo(px(x), 0);
      d.lineTo(px(x), c.height);
      d.stroke();
      if (x % labelStep === 0) d.fillText(String(x), px(x) + 2, py(0) + 12);
    }
    for (let y = Math.ceil(minY); y <= Math.floor(maxY); y++) {
      d.beginPath();
      d.moveTo(0, py(y));
      d.lineTo(c.width, py(y));
      d.stroke();
      if (y % labelStep === 0 && y) d.fillText(String(y), px(0) + 4, py(y) - 2);
    }
    d.strokeStyle = "#222";
    d.lineWidth = 2;
    d.beginPath();
    d.moveTo(0, py(0));
    d.lineTo(c.width, py(0));
    d.moveTo(px(0), 0);
    d.lineTo(px(0), c.height);
    d.stroke();
    for (const o of game.obstacles) {
      const rx=((o.width??o.radius*2)/gameWidth)*c.width/2,
        ry=((o.height??o.radius*2)/(maxY-minY))*c.height/2;
      d.save();d.translate(px(o.x),py(o.y));d.rotate(-(o.rotation??0));
      d.beginPath();
      if(!o.shape||o.shape==="circle")d.arc(0,0,(o.radius/gameWidth)*c.width,0,Math.PI*2);
      else if(o.shape==="ellipse")d.ellipse(0,0,rx,ry,0,0,Math.PI*2);
      else if(o.shape==="diamond"){d.moveTo(0,-ry);d.lineTo(rx,0);d.lineTo(0,ry);d.lineTo(-rx,0);d.closePath()}
      else d.rect(-rx,-ry,rx*2,ry*2);
      d.fillStyle = "#000000";
      d.fill();
      d.restore();
    }
    for (const crater of game.craters || []) {
      d.beginPath();
      d.arc(px(crater[0]), py(crater[1]), (crater[2]/gameWidth)*c.width, 0, Math.PI * 2);
      d.fillStyle = "#ffffff";
      d.fill();
    }
    if (trail.length) {
      d.beginPath();
      trail.forEach((p, i) =>
        i ? d.lineTo(px(p[0]), py(p[1])) : d.moveTo(px(p[0]), py(p[1])),
      );
      d.strokeStyle = trailColor;
      d.lineWidth = 3;
      d.globalAlpha=trailFinishedAt===null?1:Math.max(0,1-(now-trailFinishedAt)/1000);
      d.stroke();
      d.globalAlpha=1;
    }
    for (const u of game.units) {
      if (!u.alive) continue;
      const x = px(u.x),
        y = py(u.y);
      const body=u.color||color(u.team),direction=u.x<0?1:-1,angle=(u.angle||0)*Math.PI/180;
      if(u.id===game.current){d.beginPath();d.arc(x,y,11,0,Math.PI*2);d.fillStyle="#fff";d.fill();d.strokeStyle="#222";d.stroke()}
      d.strokeStyle=body;d.fillStyle=body;d.lineWidth=3;d.lineCap="round";
      d.beginPath();d.arc(x,y-5,3.5,0,Math.PI*2);d.fill();
      d.beginPath();d.moveTo(x,y-1);d.lineTo(x,y+7);d.moveTo(x,y+7);d.lineTo(x-5,y+13);d.moveTo(x,y+7);d.lineTo(x+5,y+13);d.moveTo(x,y+1);d.lineTo(x+direction*Math.cos(angle)*15,y-Math.sin(angle)*15);d.stroke();
      d.fillStyle = "#222";
      d.textAlign = "center";
      d.font = "12px sans-serif";
      d.fillText(u.name, x, y - 14);
      if(showNext&&game.next_units?.includes(u.id)){d.beginPath();d.arc(x,y,14,0,Math.PI*2);d.strokeStyle="#181818";d.lineWidth=3;d.stroke()}
    }
    for (const effect of effects) {
      const age=(now-effect.start)/1000;if(age<0||age>1.2)continue;
      const x=px(effect.x),y=py(effect.y),progress=Math.min(1,age/.65);
      if(effect.kind==="blast"){
        const radius=8+30*progress;d.beginPath();d.arc(x,y,radius,0,Math.PI*2);d.fillStyle=`rgba(255,${Math.floor(210*(1-progress))},40,${1-progress})`;d.fill();d.strokeStyle=`rgba(180,40,10,${1-progress})`;d.lineWidth=3;d.stroke();
      }else{
        d.fillStyle=`rgba(190,30,30,${1-progress})`;
        for(let i=0;i<10;i++){const a=i*Math.PI/5,dist=35*progress;d.fillRect(x+Math.cos(a)*dist-2,y+Math.sin(a)*dist-2,4,4)}
      }
    }
  }, [game, trail, effects, now,trailFinishedAt,trailColor]);
  return <canvas ref={ref} width="770" height="450" />;
}
function RoomPage({
  id,
  user,
  leave,
}: {
  id: string;
  user: User;
  leave: () => void;
}) {
  const [room, setRoom] = useState<Room | null>(null),
    [error, setError] = useState(""),
    [expr, setExpr] = useState("sin(x/4)*5"),
    [exprY,setExprY]=useState("0.4*t"),
    [angle, setAngle] = useState(0),
    [now, setNow] = useState(Date.now()),
    [trail, setTrail] = useState<number[][]>([]),
    [trailFinishedAt,setTrailFinishedAt]=useState<number|null>(null),
    [trailColor,setTrailColor]=useState("#e52f2f"),
    [effects, setEffects] = useState<Effect[]>([]),
    [showNext,setShowNext]=useState(false),
    [muted,setMuted]=useState(()=>localStorage.getItem("mgw_muted")==="1"),
    [chat, setChat] = useState(""),
    [history, setHistory] = useState<string[]>([]),
    [validation,setValidation]=useState<{ok:boolean;message:string}|null>(null),
    socket = useRef<WebSocket | null>(null),
    animation = useRef<number | null>(null),mutedRef=useRef(muted);
  const send = (type: string, payload: any = {}) =>
    socket.current?.send(
      JSON.stringify({ v: 1, type, request_id: crypto.randomUUID(), payload }),
    );
  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 50);
    const heartbeat=window.setInterval(()=>{if(socket.current?.readyState===WebSocket.OPEN)send("ping")},5000);
    let stopped=false,retry:number|undefined,attempts=0;
    const connect=()=>{
    const ws = new WebSocket(
      `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/v1/rooms/${id}`,
    );
    socket.current = ws;
    (window as any).__mgwSocket=ws;
    ws.onopen=()=>{if(attempts>0)setError("连接已恢复，状态已同步");attempts=0};
    ws.onmessage = (e) => {
      const m = JSON.parse(e.data);
      if (m.type === "snapshot" || m.type === "started" || m.type === "countdown") {
        setRoom(m.payload);
        const u=m.payload.game?.units?.find((x:Unit)=>x.id===m.payload.game.current);if(u){setAngle(u.angle||0);if(u.last_function)setExpr(u.last_function);if(u.last_function_y)setExprY(u.last_function_y)}
      }
      if (m.type === "turn") {
        setRoom((r: any) => ({ ...r, game: m.payload }));
        const u=m.payload.units?.find((x:Unit)=>x.id===m.payload.current);if(u){setAngle(u.angle||0);setExpr(u.last_function||(m.payload.function_mode==="polar"?"80*theta":m.payload.function_mode==="parametric"?"t":"sin(x/4)*5"));setExprY(u.last_function_y||"0.25*t")}
      }
      if(m.type==="angle"){
        setRoom((r:any)=>({...r,game:{...r.game,units:r.game.units.map((u:Unit)=>u.id===m.payload.unit?{...u,angle:m.payload.angle}:u)}}));setAngle(m.payload.angle)
      }
      if(m.type==="preference")setShowNext(Boolean(m.payload.show_next));
      if(m.type==="system")setError(m.payload.message);
      if(m.type==="kicked"){setError(m.payload.message);window.setTimeout(leave,600)}
      if(m.type==="function_used")setRoom((r:any)=>r&&({...r,chat:[...r.chat,{from:m.payload.player,text:`函数：${m.payload.expression}`}].slice(-50)}));
      if(m.type==="validation")setValidation(m.payload);
      if (m.type === "timeout")
        setRoom((r: any) => ({ ...r, game: m.payload.state }));
      if (m.type === "shot") {
        playSound("shot",mutedRef.current);
        setRoom((r:any)=>{const shooter=r?.game?.units?.find((u:Unit)=>u.id===m.payload.shooter);if(shooter)setTrailColor(shooter.color||color(shooter.team));return r});
        if (animation.current !== null) clearInterval(animation.current);
        const points: number[][] = m.payload.points;
        const finalState:Game=m.payload.state;
        let shown = 0;
        setTrail([]);
        setTrailFinishedAt(null);
        animation.current = window.setInterval(() => {
          shown = Math.min(points.length, shown + 25);
          setTrail(points.slice(0, shown));
          if (shown >= points.length && animation.current !== null) {
            clearInterval(animation.current);
            animation.current = null;
            setTrailFinishedAt(Date.now());
            playSound("blast",mutedRef.current);
            const started=Date.now(),ids=new Set((m.payload.damages||[]).map((d:any)=>d.unit));
            setRoom((r:any)=>{
              const deaths=(r?.game?.units||[]).filter((u:Unit)=>ids.has(u.id)).map((u:Unit)=>({x:u.x,y:u.y,start:started,kind:"death" as const}));
              const blast=m.payload.impact?[{x:m.payload.impact[0],y:m.payload.impact[1],start:started,kind:"blast" as const}]:[];
              setEffects(old=>[...old.filter(e=>started-e.start<1200),...deaths,...blast]);
              return {...r,game:finalState};
            });
          }
        }, 16);
        setHistory((h) => [m.payload.expression, ...h].slice(0, 12));
      }
      if (m.type === "chat")
        setRoom(
          (r: any) => r && { ...r, chat: [...r.chat, m.payload].slice(-50) },
        );
      if (m.type === "error") setError(m.payload.message);
    };
    ws.onclose = (event) => {if(stopped||event.code===4003)return;attempts++;setError(`连接中断，正在第 ${attempts} 次重连…`);retry=window.setTimeout(connect,Math.min(5000,500*2**Math.min(attempts,3)))};
    };
    connect();
    return () => {
      stopped=true;if(retry)clearTimeout(retry);socket.current?.close();
      clearInterval(clock);
      clearInterval(heartbeat);
      if (animation.current !== null) clearInterval(animation.current);
    };
  }, [id]);
  useEffect(()=>{mutedRef.current=muted;localStorage.setItem("mgw_muted",muted?"1":"0")},[muted]);
  useEffect(()=>{
    if(!room?.game||room.game.finished||room.game.resolving)return;
    const active=room.game.units.find(u=>u.id===room.game?.current);if(active?.user_id!==user.id)return;
    setValidation(null);const timer=window.setTimeout(()=>send("validate_expression",{expression:expr,expression_y:exprY}),300);return()=>clearTimeout(timer)
  },[expr,exprY,room?.game?.current,room?.game?.function_mode,room?.game?.resolving,user.id]);
  useEffect(()=>{
    const key=(e:KeyboardEvent)=>{
      if(!room?.game||room.game.function_mode!=="second_order"||room.game.resolving)return;
      const active=room.game.units.find(u=>u.id===room.game?.current);if(active?.user_id!==user.id)return;
      if(e.key!=="ArrowUp"&&e.key!=="ArrowDown")return;e.preventDefault();
      const next=Math.max(-80,Math.min(80,angle+(e.key==="ArrowUp"?1:-1)));setAngle(next);send("set_angle",{angle:next});
    };window.addEventListener("keydown",key);return()=>window.removeEventListener("keydown",key)
  },[room,angle,user.id]);
  if (!room)
    return (
      <main className="center">
        <div className="card">正在连接战场……</div>
      </main>
    );
  const mine = room.slots.find((s) => s.user_id === user.id),
    active = room.game?.units.find((u) => u.id === room.game?.current),
    myTurn = active?.user_id === user.id && !room.game?.resolving,
    owner = room.owner_id === user.id,
    seconds = room.game?.turn_deadline
      ? Math.max(0, Math.ceil(room.game.turn_deadline - now / 1000))
      : 60;
  const startSeconds=room.start_deadline?Math.max(0,Math.ceil(room.start_deadline-now/1000)):0;
  const leaveRoom=()=>{send("leave");window.setTimeout(leave,80)};
  const downloadReplay=async()=>{const data=await api(`/rooms/${id}/replay`);const blob=new Blob([JSON.stringify(data,null,2)],{type:"application/json"});const url=URL.createObjectURL(blob),a=document.createElement("a");a.href=url;a.download=`mygraphwar-${id}.json`;a.click();URL.revokeObjectURL(url)};
  return (
    <main className="game">
      <header>
        <button className="ghost" onClick={leaveRoom}>
          ← 大厅
        </button>
        <b>{room.name}</b>
        <span>
          {room.mode === "teams" ? "团队战" : "自由混战"} · {room.slots.length}/
          {room.max_players}
        </span>
        {room.game&&<button className="ghost" onClick={downloadReplay}>下载重放</button>}
        <button className="ghost" aria-label="声音开关" onClick={()=>setMuted(!muted)}>{muted?"🔇 静音":"🔊 声音"}</button>
      </header>
      {room.game ? (
        <div className="battle">
          <Battlefield game={room.game} trail={trail} effects={effects} now={now} showNext={showNext} trailFinishedAt={trailFinishedAt} trailColor={trailColor} />
          <aside className="card">
            <h3>第 {room.game.turn + 1} 回合 · {room.game.resolving ? "结算中" : `${seconds}s`}</h3>
            {!mine&&<div className="victory">观战模式 · {room.spectators.length} 人观战</div>}
            <p>
              当前：<b>{active?.name || "结束"}</b>
            </p>
            {room.game.finished && (
              <div className="victory">胜方：{room.game.winner}{owner?<button onClick={()=>send("return_to_room")}>返回房间 / 再来一局</button>:<small>等待房主开始下一局</small>}</div>
            )}
            <label>
              {room.game.function_mode === "normal"
                ? "普通函数 y = f(x)"
                : room.game.function_mode === "first_order"
                  ? "一阶方程 y' = f(x,y)"
                  : room.game.function_mode === "second_order"
                    ? "二阶方程 y'' = f(x,y,y')"
                    : room.game.function_mode === "polar"
                      ? "极坐标 r = f(theta)"
                      : "参数方程 x = f(t), y = g(t)"}
            </label>
            <input
              value={expr}
              placeholder={room.game.function_mode==="parametric"?"x(t)":undefined}
              onChange={(e) => setExpr(e.target.value)}
              disabled={!myTurn}
            />
            {room.game.function_mode === "parametric" && <input value={exprY} onChange={e=>setExprY(e.target.value)} disabled={!myTurn} placeholder="y(t)"/>}
            {validation&&<small className={validation.ok?"valid":"invalid"}>{validation.ok?"✓":"⚠"} {validation.message}</small>}
            {room.game.function_mode === "second_order" && (
              <>
                <label>发射角：{angle}°</label>
                <input
                  type="range"
                  min="-80"
                  max="80"
                  value={angle}
                  onChange={(e) => {const value=+e.target.value;setAngle(value);send("set_angle",{angle:value})}}
                  disabled={!myTurn}
                />
              </>
            )}
            <button
              disabled={!myTurn||validation?.ok===false}
              onClick={() => {
                setTrail([]);
                send("shoot", { expression: expr, expression_y:exprY, angle });
              }}
            >
              发射函数
            </button>
            <small>
              坐标范围
              x={room.game.bounds[0]}…{room.game.bounds[1]}、y={room.game.bounds[2].toFixed(1)}…{room.game.bounds[3].toFixed(1)}。普通函数仅纵向平移以经过士兵，士兵不在原点。
            </small>
            <small>命令：-sayfunc / -stopsayfunc 显示函数；-shownext / -stopshownext 标记下一名士兵；-skip 全员投票换图。</small>
            {history.length > 0 && (
              <div>
                <h4>函数历史</h4>
                {history.map((x, i) => (
                  <button
                    className="ghost history"
                    key={i}
                    onClick={() => setExpr(x)}
                  >
                    {x}
                  </button>
                ))}
              </div>
            )}
            <div className="units">
              {room.game.units.map((u) => (
                <div className={u.alive ? "" : "dead"} key={u.id}>
                  {u.name}
                  <span>
                    {u.alive ? "存活" : "阵亡"} · {u.team}
                  </span>
                </div>
              ))}
            </div>
          </aside>
        </div>
      ) : (
        <div className="waiting">
          <section className="card">
            <h2>房间设置</h2>
            {room.starting&&<div className="victory">比赛将在 {startSeconds} 秒后开始，正在生成地图……</div>}
            {owner && (
              <div className="config">
                {room.ruleset === "extended" && <><label>对局模式</label><select value={room.mode} onChange={e=>send("configure",{mode:e.target.value})}><option value="ffa">自由混战</option><option value="teams">A/B 团队战</option></select></>}
                <label>坐标范围方式</label>
                <select aria-label="坐标范围方式" value={room.axis_range_mode} onChange={e=>send("configure",{axis_range_mode:e.target.value})}>
                  <option value="fixed">房主自定义</option>
                  <option value="random">每局随机（±5～±50）</option>
                </select>
                <label>横轴半范围（±）</label>
                <input aria-label="横轴半范围" type="number" min="1" max="100" step="0.1" disabled={room.axis_range_mode==="random"} value={room.axis_half_range} onChange={e=>{const value=e.currentTarget.valueAsNumber;if(Number.isFinite(value))send("configure",{axis_half_range:value})}}/>
                <label>函数模式</label>
                <select
                  aria-label="函数模式"
                  value={room.function_mode}
                  onChange={(e) => {const mode=e.target.value;if(mode==="polar")setExpr("80*theta");else if(mode==="parametric"){setExpr("t");setExprY("0.25*t")}else setExpr("sin(x/4)*5");send("configure", { function_mode: mode })}}
                >
                  <option value="normal">普通函数</option>
                  <option value="first_order">一阶微分方程</option>
                  <option value="second_order">二阶微分方程</option>
                  {room.ruleset === "extended" && <option value="polar">极坐标曲线</option>}
                  {room.ruleset === "extended" && <option value="parametric">参数方程</option>}
                </select>
              </div>
            )}
            <h2>参战席位</h2>
            {room.slots.map((s) => (
              <div className="slot" key={s.id}>
                <b>{s.name}</b>
                {owner ? (
                  <select
                    value={s.team}
                    onChange={(e) =>
                      send("configure", { slot_id: s.id, team: e.target.value })
                    }
                  >
                    <option value="A">A 队</option>
                    <option value="B">B 队</option>
                  </select>
                ) : (
                  <span>{s.team} 队</span>
                )}
                {owner ? (
                  <select
                    value={s.soldiers}
                    onChange={(e) =>
                      send("configure", {
                        slot_id: s.id,
                        soldiers: +e.target.value,
                      })
                    }
                  >
                    {[1, 2, 3, 4].map((n) => (
                      <option value={n} key={n}>{n} 名士兵</option>
                    ))}
                  </select>
                ) : (
                  <span>{s.soldiers} 名士兵</span>
                )}
                {owner ? <input aria-label={`${s.name}颜色`} type="color" value={s.color} onChange={e=>send("configure",{slot_id:s.id,color:e.target.value})}/> : <span className="dot" style={{background:s.color}}/>}
                <em>
                  {s.ai
                    ? s.ai.toUpperCase()
                    : s.user_id === room.owner_id
                      ? "房主"
                      : s.ready
                        ? "已准备"
                        : "未准备"}
                </em>
                {owner && s.ai && (
                  <button
                    className="tiny"
                    onClick={() => send("remove_ai", { slot_id: s.id })}
                  >
                    移除
                  </button>
                )}
                {owner && s.user_id && s.user_id !== room.owner_id && <button className="tiny" onClick={()=>send("kick",{user_id:s.user_id})}>踢出</button>}
              </div>
            ))}
            {owner ? (
              <div className="actions">
                <select id="aidiff">
                  <option value="easy">简单 AI</option>
                  <option value="medium">中等 AI</option>
                  <option value="hard">困难 AI</option>
                  <option value="adaptive">自适应 AI</option>
                </select>
                <button
                  onClick={() =>
                    send("add_ai", {
                      difficulty: (
                        document.getElementById("aidiff") as HTMLSelectElement
                      ).value,
                    })
                  }
                >
                  添加电脑
                </button>
                <button disabled={room.starting} onClick={() => send("start")}>{room.starting?"即将开始":"开始对局"}</button>
              </div>
            ) : (
              <button onClick={() => send("ready", { ready: !mine?.ready })}>
                {mine?.ready ? "取消准备" : "准备"}
              </button>
            )}
          </section>
        </div>
      )}
      <footer>
        <div className="messages">
          {room.chat.map((m, i) => (
            <span key={i}>
              <b>{m.from}：</b>
              {m.text}
            </span>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            send("chat", { text: chat });
            setChat("");
          }}
        >
          <input
            value={chat}
            onChange={(e) => setChat(e.target.value)}
            placeholder="房间聊天"
          />
          <button>发送</button>
        </form>
      </footer>
      {error && (
        <div className="toast" onClick={() => setError("")}>
          {error}
        </div>
      )}
    </main>
  );
}
function ReplayViewer({data,close}:{data:any;close:()=>void}){
  const[index,setIndex]=useState(-1),[playing,setPlaying]=useState(false),[now,setNow]=useState(Date.now());
  useEffect(()=>{const clock=setInterval(()=>setNow(Date.now()),50);return()=>clearInterval(clock)},[]);
  useEffect(()=>{if(!playing)return;const timer=setInterval(()=>setIndex(i=>{if(i>=data.shots.length-1){setPlaying(false);return i}return i+1}),1600);return()=>clearInterval(timer)},[playing,data.shots.length]);
  const shot=index>=0?data.shots[index]:null,game:Game=shot?.state||data.initial,trail=shot?.points||[];
  const replayShooter=shot?game.units.find(u=>u.id===shot.shooter):null;
  return <main className="shell replay"><header><button className="ghost" onClick={close}>← 返回大厅</button><b>比赛重放</b><span>{index+1}/{data.shots.length} 发</span></header><div className="battle"><Battlefield game={game} trail={trail} effects={[]} now={now} trailColor={replayShooter?.color||"#e52f2f"}/><aside className="card"><h3>{shot?`第 ${index+1} 发`:`初始地图`}</h3>{shot&&<><p>函数：<code>{shot.expression}</code></p><p>模式：{shot.function_mode} · 角度 {shot.angle}°</p><p>击杀：{shot.damages?.length||0}</p></>}<input type="range" min="-1" max={Math.max(-1,data.shots.length-1)} value={index} onChange={e=>{setPlaying(false);setIndex(+e.target.value)}}/><div className="actions"><button onClick={()=>setIndex(i=>Math.max(-1,i-1))}>上一发</button><button onClick={()=>setPlaying(!playing)}>{playing?"暂停":"自动播放"}</button><button onClick={()=>setIndex(i=>Math.min(data.shots.length-1,i+1))}>下一发</button></div><p>胜方：<b>{data.final.winner||"未决"}</b></p></aside></div></main>
}
function App() {
  const [user, setUser] = useState<User | null>(null),
    [room, setRoom] = useState<string | null>(null),
    [replay,setReplay]=useState<any>(null),
    [loading, setLoading] = useState(true);
  useEffect(() => {
    api("/auth/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);
  if (loading) return null;
  if (!user) return <Auth done={setUser} />;
  if(replay)return <ReplayViewer data={replay} close={()=>setReplay(null)}/>;
  if (room)
    return <RoomPage id={room} user={user} leave={() => setRoom(null)} />;
  return (
    <Lobby
      user={user}
      enter={setRoom}
      openReplay={setReplay}
      logout={() =>
        api("/auth/logout", { method: "POST" }).then(() => setUser(null))
      }
    />
  );
}
createRoot(document.getElementById("root")!).render(<App />);
