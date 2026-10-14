"""Temporary, finite GoAndTurnKick retest through Client's normal Medusa launcher."""
import ctypes
import faulthandler
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import socket
import struct
import sys
import time

import CppPackage as C
import Global
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import Task, State, StateMachine, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Player, vision
from WorldModel import kickStatus

ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT.parent/'tmp/goandturnkick_retest_20261013'
REQUEST = json.loads((OUTPUT/'request.json').read_text(encoding='utf-8'))
RUN = OUTPUT/REQUEST['label']
RUN.mkdir(exist_ok=True)
_fault = (RUN/'fault.log').open('w',encoding='utf-8',buffering=1)
faulthandler.enable(_fault)
ctypes.windll.kernel32.SetErrorMode(0x0001|0x0002|0x8000)
metadata = dict(pid=os.getpid(),python=sys.version,executable=sys.executable,
    prefix=sys.prefix,base_prefix=sys.base_prefix,architecture=platform.architecture()[0],
    cwd=os.getcwd(),request=REQUEST,started=time.time(),cpp_module=C.__file__,
    isSimulation=Global.isSimulation,isYellow=Global.isYellow,isRight=Global.isRight)
for key,path in [('dll',ROOT/'MedusaCore.dll'),('pyd',ROOT/'PythonScripts/CppPackage/CppPackage.pyd')]:
    metadata[key+'_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
(RUN/'runtime.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')

def vi(n):
    out=bytearray()
    while n>127: out.append((n&127)|128); n>>=7
    out.append(n)
    return bytes(out)
def integer(n,v):return vi(n*8)+vi(int(v))
def message(n,v):return vi(n*8+2)+vi(len(v))+v
def double(n,v):return vi(n*8+1)+struct.pack('<d',v)

def reset_scene():
    # Standard grSim replacement packet. Only loopback simulation receives this.
    x,y,angle=REQUEST['robot']
    bx,by=REQUEST['ball']
    robots={(False,0):(-3.8,-2.4,0),(False,1):(x,y,angle),
            (False,2):(-3.8,2.4,0),(True,0):(4.2,2,180)}
    payload=message(1,double(1,bx)+double(2,by)+double(3,0)+double(4,0))
    for yellow in (False,True):
        for rid in range(16):
            enabled=(yellow,rid) in robots
            px,py,pa=robots.get((yellow,rid),(-4.7,-3.5-rid*.2,0))
            robot=double(1,px)+double(2,py)+double(3,pa)
            robot+=integer(4,rid)+integer(5,yellow)+integer(6,enabled)
            payload+=message(2,robot)
    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
        sock.sendto(message(2,payload),('127.0.0.1',20011))

class RetestState(State):
    def __init__(self):
        super().__init__()
        self.phase='initial'; self.started=0; self.rows=[]; self.count=0; self.stop_frames=0
        self.log=(RUN/'telemetry.jsonl').open('w',encoding='utf-8',buffering=1)

    def stops(self):
        kickStatus.clearAll()
        for number in (0,1,2):C.setDribbleCommand(number,0)
        return {name:Task(Skill.Stop(),fixedNumber=n) for name,n in [('A',1),('B',2),('G',0)]}

    def getTasks(self):
        if not Global.isSimulation or Global.isYellow or Global.isRight:
            raise RuntimeError('Retest requires simulation, blue, left')
        now=time.monotonic()
        if self.phase=='initial':
            reset_scene(); self.started=now; self.phase='settling'
            (RUN/'phase.txt').write_text('settling',encoding='utf-8')
        if self.phase=='settling':
            if now-self.started<1.5 or not (Ball.valid() and Player.isValid(1)):
                return self.stops()
            self.started=now; self.phase='running'
            (RUN/'phase.txt').write_text('running',encoding='utf-8')
            print('[GoAndTurnKickRetest] RUNNING '+REQUEST['label'],flush=True)
        if self.phase=='done':
            self.stop_frames+=1
            if REQUEST.get('auto_exit') and self.stop_frames>30:
                print('[GoAndTurnKickRetest] STOPPED; bounded test exit',flush=True)
                ctypes.CDLL('ucrtbase.dll').fflush(None)
                os._exit(0)
            return self.stops()
        p,b=Player.Pos(1),Ball.pos()
        row=dict(t=now-self.started,cycle=vision.getCycle(),valid=Ball.valid() and Player.isValid(1),
            robot=[p.x(),p.y()],ball=[b.x(),b.y()],angle=Player.direction(1),
            speed=Player.velMod(1),ball_speed=Ball.velMod(),infrared=Player.isInfraredOn(1))
        self.rows.append(row);self.log.write(json.dumps(row)+'\n')
        if row['t']>=REQUEST.get('seconds',15):
            self.finish();return self.stops()
        if not row['valid']:return self.stops()
        self.count+=1
        if self.count<=3:print('[GoAndTurnKickRetest] FRAME',self.count,flush=True)
        return {'A':Task(Skill.GoAndTurnKick(target=CGeoPoint(*REQUEST['target']),power=REQUEST['power']),fixedNumber=1),
                'B':Task(Skill.Stop(),fixedNumber=2),'G':Task(Skill.Stop(),fixedNumber=0)}

    def finish(self):
        rows=[r for r in self.rows if r['valid']]
        origin=rows[0]['ball'];delta=[REQUEST['target'][i]-origin[i] for i in (0,1)]
        norm=max(math.hypot(*delta),1)
        progress=[sum((r['ball'][i]-origin[i])*delta[i] for i in (0,1))/norm for r in rows]
        released=any(d>700 and r['ball_speed']>500 and math.dist(r['robot'],r['ball'])>350 for d,r in zip(progress,rows))
        result=dict(completed=True,frames=len(rows),duration=rows[-1]['t'],
            max_ball_speed=max(r['ball_speed'] for r in rows),max_forward_travel=max(progress),
            release_observed=released,infrared_samples=sum(r['infrared'] for r in rows),
            first=rows[0],last=rows[-1],skill_calls=self.count)
        result['pass_behavior']=released and result['max_ball_speed']>1000
        (RUN/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        self.phase='done';self.log.close()
        (RUN/'phase.txt').write_text('done',encoding='utf-8')
        print('[GoAndTurnKickRetest] DONE '+json.dumps(result),flush=True)
        try:ctypes.CDLL('ucrtbase.dll').fflush(None)
        except OSError:pass

    def getMatchString(self):return ''
    def transFunction(self):return ''

@declare_state_machine(RetestState)
class Test_GoAndTurnKickRetest(StateMachine):
    pass
