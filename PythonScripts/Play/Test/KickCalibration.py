"""Single blue robot, flat-kick power sweep. Simulation only, opt-in.

Measures both framework velocity and raw SSL positions/t_capture. Raw protocol:
https://github.com/RoboCup-SSL/ssl-vision/blob/master/src/shared/proto/messages_robocup_ssl_detection.proto
"""
import collections
import json
import math
import os
import socket
import struct
import threading
import time
import CppPackage as C
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Player
from WorldModel import kickStatus
from tools.preliminary_scene import number, integer, message


def fields(data):
    i = 0
    def vint():
        nonlocal i
        n = shift = 0
        while True:
            b = data[i]; i += 1
            n |= (b & 127) << shift
            if b < 128:
                return n
            shift += 7
    result = collections.defaultdict(list)
    while i < len(data):
        tag = vint(); field, wire = tag >> 3, tag & 7
        if wire == 0:
            value = vint()
        elif wire == 1:
            value = struct.unpack_from('<d', data, i)[0]; i += 8
        elif wire == 5:
            value = struct.unpack_from('<f', data, i)[0]; i += 4
        elif wire == 2:
            size = vint(); value = data[i:i+size]; i += size
        else:
            raise ValueError('unsupported protobuf wire type')
        result[field].append(value)
    return result


class RawVision:
    def __init__(self):
        self.samples = collections.deque(maxlen=5000)
        self.error = None
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.relay = os.environ.get('SRC_KICK_RAW_RELAY') == '1'
        self.forward = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.forward.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton('127.0.0.1'))
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            self.sock.bind(('', 10022 if self.relay else 10020))
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                                 socket.inet_aton('224.5.23.2')+socket.inet_aton('127.0.0.1'))
        except OSError as exc:
            self.error = str(exc)
            self.sock.close()
            print('CALIBRATION_NOTE raw UDP unavailable; reporting filtered velocity only: '+str(exc), flush=True)
            return
        threading.Thread(target=self.listen, daemon=True).start()

    def listen(self):
        try:
            while True:
                data, _ = self.sock.recvfrom(65535)
                if self.relay:
                    self.forward.sendto(data, ('224.5.23.2', 10020))
                packet = fields(data)
                for detection in packet.get(1, []):
                    f = fields(detection)
                    for ball in f.get(5, []):
                        b = fields(ball)
                        self.samples.append((time.monotonic(), f[4][0], f[2][0], b[3][0], b[4][0]))
        except Exception as exc:
            self.error = str(exc)

    def speeds(self, since):
        previous = {}
        values = []
        for wall, camera, timestamp, x, y in list(self.samples):
            if wall < since or not -1650 < x < 1000 or abs(y) > 300:
                continue
            old = previous.get(camera)
            previous[camera] = timestamp, x, y
            if old:
                dt = timestamp-old[0]
                if 0.001 < dt < .15:
                    values.append(math.hypot(x-old[1], y-old[2])/dt/1000)
        return values


def reset_scene():
    ball = number(1, -1.8)+number(2, 0)+number(3, 0)+number(4, 0)
    replacement = message(1, ball)
    for yellow in (False, True):
        for rid in range(16):
            on = not yellow and rid == 1
            x, y = (-2, 0) if on else (-4.7, -3.5-rid*.2)
            r = number(1, x)+number(2, y)+number(3, 0)+integer(4, rid)+integer(5, yellow)+integer(6, on)
            replacement += message(2, r)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(message(2, replacement), ('127.0.0.1', 20011))


class CalibrationState(State):
    def __init__(self):
        super().__init__()
        powers = [int(v) for v in os.environ.get('SRC_KICK_POWERS', '3000,5000,6500,8000,10000,12700').split(',')]
        if any(p < 0 or p > 12700 for p in powers):
            raise ValueError('Calibration power must be in 0..12700')
        self.trials = [(p, r+1) for p in powers for r in range(3)]
        self.index = 0
        self.stage = 'reset'
        self.entered = time.monotonic()
        self.raw = RawVision()
        self.peak = 0
        self.released = False
        self.results = []

    def getTasks(self):
        now = time.monotonic()
        C.setDribbleCommand(1, 0)
        kickStatus.clearAll()
        action = Skill.Stop()
        if self.index >= len(self.trials):
            return {'A': Task(action, fixedNumber=1)}
        power, repetition = self.trials[self.index]
        if self.stage == 'reset':
            reset_scene()
            self.stage, self.entered = 'settle', now
            self.peak, self.released = 0, False
        elif self.stage == 'settle':
            # Exclude reset/teleport velocity spikes; require stationary, valid ball.
            if now-self.entered > 2 and Ball.valid() and abs(Ball.posX()+1800) < 50 and Ball.velMod() < 100:
                self.stage, self.entered = 'kick', now
                self.armed = now
            elif now-self.entered > 12:
                print('CALIBRATION_FAULT ball did not settle: '+str((Ball.posX(), Ball.posY(), Ball.velMod())), flush=True)
                self.stage = 'fault'
        elif self.stage == 'kick':
            if Ball.valid() and Ball.posX() > -1650:
                self.released = True
                self.stage = 'measure'
            elif now-self.entered < 3:
                def execute(executor):
                    C.setDribbleCommand(executor, 3)
                    kickStatus.setKick(executor, power)
                    return C.makeItRushTo(executor, CGeoPoint(-1800, 0), 0, maxAcc=500, needDribble=True)
                action = execute, lambda executor: CGeoPoint(-2000, 0)
            else:
                self.stage = 'measure'
        if self.stage == 'measure':
            if Ball.valid() and -1650 < Ball.posX() < 1000 and abs(Ball.posY()) < 300:
                self.peak = max(self.peak, Ball.velMod()/1000)
            if now-self.entered > 4 or (self.released and Ball.posX() > 1500):
                raw = self.raw.speeds(self.armed)
                result = {'power': power, 'repeat': repetition, 'released': self.released,
                          'filtered_peak_m_s': self.peak,
                          'raw_peak_m_s': max(raw) if raw else None, 'raw_samples': len(raw),
                          'raw_error': self.raw.error}
                self.results.append(result)
                print('CALIBRATION '+json.dumps(result), flush=True)
                self.index += 1
                self.stage = 'reset'
                if self.index == len(self.trials):
                    print('CALIBRATION_DONE '+json.dumps(self.results), flush=True)
        return {'A': Task(action, fixedNumber=1)}

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''


@declare_state_machine(CalibrationState)
class KickCalibration(StateMachine):
    pass
