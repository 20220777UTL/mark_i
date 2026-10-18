"""Two-pass play: orchestration only; movement, ball skills and power are supplied.

first_pass is a deliberate test checkpoint. full enables the complete combination.
Vision/IR checks are estimates, not referee decisions or guarantees of one-touch shots.
"""
import json
import math
import time
from pathlib import Path

import CppPackage
import Global
from Geometry import CGeoPoint
from Vision import Ball, Player, vision
from Utils import DebugColor
from WorldModel import Params, Flags, Precision, kickStatus
from WorldModel.PowerCalculator import evalPower, P
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import RushTo, SimpleGoTo, Stop, GetBallV4, GoAndTurnKick, Shoot

ROLES = ('A', 'B')  # A collects/finishes; B receives/returns.
PASS_POINT = (4200, -1500)
FIRST_PASS_TIMEOUT = 1.5
SETUP_VISION_GRACE = .12  # Keep collection continuous through brief ball-only gaps.
RETURN_VISION_GRACE = .12  # Seconds, only with fresh robot vision and a nearby last-seen ball.
KICK_POWER_SCALE = 0.85  # Command scaling; verify physical ball speed in simulation.
RETURN_POWER_FACTOR = 0.90  # Reduce only the return command by 10% for comparison.
RECEIVE_DISTANCE = 1200
RECEIVE_ENTER_DISTANCE = 110
RECEIVE_EXIT_DISTANCE = 120
RECEIVE_GAP_GRACE = .12
RECEIVE_CONFIRM_DURATION = .15
SHOT_POINT = (3200, 1400)
RETURN_AIM_POINT = (3270, 1330)  # Ball target at the shooting mouth; body still uses SHOT_POINT.
FINISH_ADJUST_LEAD_SECONDS = 1.2  # Estimated time to mouth; delay unstable launch predictions.
MOVE_FLAGS = Flags.allow_dss | Flags.dodge_our_defense_box


def xy(p):
    return p.x(), p.y()


def dist(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])


def bearing(a, b):
    return math.atan2(b[1]-a[1], b[0]-a[0])


def angle_error(a, b):
    return abs((a-b+math.pi) % (2*math.pi)-math.pi)


class PassCombo(State):
    def __init__(self):
        super().__init__()
        setting = Path('combo_stage.txt')
        self.checkpoint = setting.read_text(encoding='utf-8').strip() if setting.exists() else 'first_pass'
        if self.checkpoint not in ('first_pass', 'full'):
            raise ValueError('combo_stage.txt must be first_pass or full')
        self.attackers = ()
        self.last_reset_cycle = None
        self.reset()

    def reset(self, round_number=1):
        self.round_number = round_number
        self.restart_ball = None
        self.restart_elapsed = 0.0
        self.restart_last = None
        self.restart_gap = False
        self.phase = 'SETUP'
        self.reason = 'P1 collect and hold; P2 move to pass point'
        self.p1, self.p2 = self.attackers if len(self.attackers) == 2 else (None, None)
        self.entered = None
        self.since = {}
        self.hold = {}
        self.origin = None
        self.shot_origin = None
        self.shot_skill_started = False
        self.finish_request_time = None
        self.finish_attempt_since = None
        self.stationary_shot_diagnostic = None
        self.finish_target = SHOT_POINT
        self.finish_contact = False
        self.finish_recover = False
        self.ball_velocity = (0,0)
        self.previous = {}
        self.carry = {n: 0.0 for n in self.attackers}
        self.max_speed = 0
        self.cached_cycle = None
        self.cached_tasks = None
        self.cached_time = 0
        self.setup_skills = None
        self.setup_labels = {}
        self.setup_held = False
        self.setup_elapsed = 0.0
        self.setup_last = None
        self.last_log = -1e9
        self.last_logged_phase = None
        self.labels = {}
        self.powers = {}
        self.last_requested = {}
        self.pause = None
        self.recovered_since = None
        self.last_valid_ball = None
        self.last_valid_time = None
        self.last_valid_speed = 0
        self.return_skill = None
        self.return_skill_label = None
        self.return_power = None
        self.return_grace_active = False
        self.ball_valid = False
        self.shoot_diagnostic = None
        self.last_shoot_log = -1e9
        self.last_shoot_status = None
        self.last_finish_log = -1e9
        self.last_finish_status = None
        self.first_pass_kick_requested = False
        self.first_pass_reacquiring = False
        self.first_pass_anchor = None
        self.first_aim_since = None
        self.first_aim_last = None
        self.first_aim_gap = False
        self.corner_slow = False
        self.escape_targets = {}
        self.watch_phase = None
        self.watch_started = None
        self.round_started = None
        self.receive_missing_since = {}
        self.receiver_wait_pos = None
        self.reception = dict(latched=False, elapsed=0.0, last=None, gap=None)
        self.receiver_recovery = False
        self.return_diagnostic = None
        self.last_return_log = -1e9
        self.last_return_status = None

    def stop_tasks(self):
        return {n: Stop() for n in self.attackers}

    def restart_failed_round(self, now, own, ball):
        # Receiver failures retain their owner, including turning and kicking.
        # Only a settled ball replaced in the center starts a new first pass.
        center_reset = dist(ball,(0,0)) <= 500 and math.hypot(*self.ball_velocity) < 150
        retry_reception = (not center_reset and (
            self.watch_phase in ('RECEIVE1','WAIT_RETURN','PASS2')
            or (self.watch_phase == 'FINISH' and self.receiver_side(ball))))
        self.reset(self.round_number+1)
        if retry_reception:
            self.p1,self.p2 = self.attackers
            self.receiver_recovery = True
            self.change('RECEIVE1','retry reception: P2 collect; P1 stay at shot point',now)
        else:
            self.reason = 'new round: retry failed combination'

    def restart_after_shot(self, now, own, ball, speed, valid):
        """Restart a completed or failed combination; never count a goal."""
        if self.escape_targets:
            return False
        retryable = (self.phase == 'FAULT' and self.reason in (
            'phase timed out: SETUP', 'phase timed out: PASS1',
            'phase timed out: RECEIVE1', 'phase timed out: WAIT_RETURN',
            'phase timed out: PASS2', 'phase timed out: FINISH',
            'first pass did not depart', 'return pass did not depart',
            'receive visibility unavailable too long',
            'vision unavailable too long: reset round',
            'vision recovery timed out: reset round',
            'return outcome unclear after vision recovery',
            'pass outcome unclear after vision recovery',
            'speed / carry / field guard: reset round',
            'robot field margin / penalty guard', 'ball speed / field guard',
            'round deadline: restart attack',
            'return stayed on receiver side: retry reception',
            'contact shot did not depart: retry attack',
            'final shot interrupted: inspect before reset'))
        if (self.phase != 'DONE' and not retryable) or self.checkpoint != 'full':
            return False
        playable = (abs(ball[0]) < Params.pitchLength/2-110
                    and abs(ball[1]) < Params.pitchWidth/2-110
                    and not self.near_penalty(ball))
        safe_robots = (len(own) == 2 and all(not self.near_penalty(r['pos'])
                       and abs(r['pos'][0]) < Params.pitchLength/2-110
                       and abs(r['pos'][1]) < Params.pitchWidth/2-110
                       and r['speed'] < 150 for r in own.values()))
        if (retryable and self.entered is not None and now-self.entered >= 1.0
                and valid and playable and speed < 6200 and safe_robots):
            self.restart_failed_round(now,own,ball)
            return True
        # A blocked shot returning into playable space is a new attack now,
        # rather than waiting for the moving ball to settle for half a second.
        if (self.phase == 'DONE' and valid and len(own) == 2 and playable
                and self.ball_velocity[0] < -200 and 200 < speed < 6200
                and all(not self.near_penalty(r['pos'])
                        and abs(r['pos'][0]) < Params.pitchLength/2-110
                        and abs(r['pos'][1]) < Params.pitchWidth/2-110
                        for r in own.values())):
            self.reset(self.round_number+1)
            self.reason = 'rebound in play: collect for next attack'
            return True
        if (self.entered is None or now-self.entered < 1.0
                or not valid or len(own) != 2 or not playable or speed >= 150
                or any(self.near_penalty(r['pos'])
                       or abs(r['pos'][0])>Params.pitchLength/2-110
                       or abs(r['pos'][1])>Params.pitchWidth/2-110
                       or r['speed']>=150 for r in own.values())):
            # Brief ball gaps freeze confirmation; motion/unsafe locations or
            # missing robots invalidate it. Unseen time is never accumulated.
            if (valid or len(own) != 2 or self.entered is None
                    or now-self.entered < 1.0):
                self.restart_ball = None
                self.restart_elapsed = 0.0
            elif self.restart_last is not None and now-self.restart_last > .12:
                self.restart_ball = None
                self.restart_elapsed = 0.0
            self.restart_gap = True
            if not retryable:
                self.reason = 'shot finished: waiting for a settled playable ball'
            return False
        if (self.restart_ball is None or dist(ball,self.restart_ball) > 50
                or self.restart_last is None or now-self.restart_last > .12):
            self.restart_ball = ball
            self.restart_elapsed = 0.0
        elif not self.restart_gap:
            self.restart_elapsed += now-self.restart_last
        self.restart_last = now
        self.restart_gap = False
        if not retryable:
            self.reason = 'next round: confirming settled ball'
        if self.restart_elapsed < .5:
            return False
        if retryable:
            self.restart_failed_round(now,own,ball)
        else:
            self.reset(self.round_number+1)
            self.reason = 'new round: collect replaced or settled ball'
        return True

    def recovery_skills(self, now, own, valid):
        """Exit a triggered robot guard without kicking or pursuing the ball."""
        if (self.phase not in ('FAULT','DONE') or not valid or len(own) != 2
                or self.entered is None or now-self.entered < .5):
            return {}
        skills = {}
        edge_x = Params.pitchLength/2-110
        edge_y = Params.pitchWidth/2-110
        box_x = Params.pitchLength/2-Params.penaltyDepth-150
        box_y = Params.penaltyWidth/2+150
        for n,r in own.items():
            x,y = r['pos']
            unsafe = self.near_penalty((x,y)) or abs(x)>=edge_x or abs(y)>=edge_y
            if n not in self.escape_targets and unsafe and r['speed'] < 150:
                target = (max(-edge_x+100,min(edge_x-100,x)),
                          max(-edge_y+100,min(edge_y-100,y)))
                if self.near_penalty(target):
                    candidates = [(math.copysign(box_x-120,x),target[1]),
                                  (target[0],math.copysign(box_y+120,y or 1))]
                    target = min(candidates,key=lambda p:dist(p,r['pos']))
                self.escape_targets[n] = target
            if n in self.escape_targets:
                target = self.escape_targets[n]
                if dist(r['pos'],target)<40 and r['speed']<150 and not unsafe:
                    del self.escape_targets[n]
                else:
                    skills[n] = SimpleGoTo(CGeoPoint(*target),angle=r['heading'],flag=Flags.slowly)
        return skills

    def stable(self, key, condition, now, duration=.15):
        if not condition:
            self.since.pop(key, None)
            return False
        return now-self.since.setdefault(key, now) >= duration

    def check_deadline(self, now):
        """Bound real elapsed time, including brief vision pauses and recovery."""
        if self.phase in ('FAULT','DONE','FIRST_PASS_OK'):
            return
        phase = self.pause['phase'] if self.phase == 'VISION_WAIT' and self.pause else self.phase
        limits = {'SETUP':12, 'PASS1':FIRST_PASS_TIMEOUT, 'RECEIVE1':6,
                  'WAIT_RETURN':5, 'PASS2':5, 'FINISH':5}
        if self.round_started is None:
            self.round_started = now
        if self.watch_phase != phase:
            self.watch_phase, self.watch_started = phase, now
        reason = None
        if now-self.round_started > 30:
            reason = 'round deadline: restart attack'
        elif now-self.watch_started > limits.get(phase,5):
            reason = 'phase timed out: '+phase
        if reason:
            self.pause = None
            self.first_aim_since = self.first_aim_last = None
            self.change('FAULT',reason,now)

    def first_pass_aligned(self, now, n, target, ball, theta):
        """IR may hold a ball, but cannot bypass the first pass direction check."""
        own = getattr(self,'own',{})
        r, receiver = own.get(n), own.get(self.p2)
        good = False
        if r is not None and receiver is not None and self.ball_valid:
            dx,dy = ball[0]-r['pos'][0],ball[1]-r['pos'][1]
            forward = dx*math.cos(r['heading'])+dy*math.sin(r['heading'])
            lateral = -dx*math.sin(r['heading'])+dy*math.cos(r['heading'])
            good = (angle_error(r['heading'],theta) <= Precision.HIGH
                    and angle_error(theta,bearing(ball,target)) <= Precision.HIGH
                    and 0 < forward < 130 and abs(lateral) < 20
                    and math.hypot(dx,dy) < 130 and r['speed'] < 150
                    and math.hypot(*self.ball_velocity) < 180
                    and self.ready(self.p2,target,r['pos'],own))
        if not good:
            self.first_aim_since = self.first_aim_last = None
            self.first_aim_gap = False
            return False
        # SETUP already confirmed settled possession and receiver readiness.
        # A fresh frame must meet every accuracy/contact/speed check above,
        # but must not miss that valid aim window by waiting another 0.15 s.
        self.first_aim_since = now
        self.first_aim_gap = False
        self.first_aim_last = now
        return True

    def first_pass_mouth_ready(self, n, own, ball):
        """Use the existing release envelope when deciding whether to re-collect."""
        r = own[n]
        dx,dy = ball[0]-r['pos'][0],ball[1]-r['pos'][1]
        forward = dx*math.cos(r['heading'])+dy*math.sin(r['heading'])
        lateral = -dx*math.sin(r['heading'])+dy*math.cos(r['heading'])
        return 0 < forward < 130 and abs(lateral) < 20 and math.hypot(dx,dy) < 130

    def change(self, phase, reason, now):
        self.phase, self.reason, self.entered = phase, reason, now
        self.since.clear()
    
    def contact(self, n, own, ball):
        r = own[n]
        gap = dist(r['pos'], ball)
        # Proximity alone is not enough: ball must be in front, slow and near mouth.
        return gap < 125 and (r['ir'] or (gap < 105 and
            angle_error(r['heading'], bearing(r['pos'],ball)) < .22))

    def confirm_reception(self, now, own=None, ball=None, speed=0):
        """Accumulate only adjacent valid observations; missing intervals never count."""
        state = self.reception
        if own is None:
            state['last'] = None
            if state['gap'] is None:
                state['gap'] = now
            if now-state['gap'] > RECEIVE_GAP_GRACE:
                state['latched'], state['elapsed'] = False, 0.0
            return False
        if ((state['gap'] is not None and now-state['gap'] > RECEIVE_GAP_GRACE)
                or (state['last'] is not None and now-state['last'] > RECEIVE_GAP_GRACE)):
            state['latched'], state['elapsed'], state['last'] = False, 0.0, None
        state['gap'] = None
        r = own[self.p2]
        limit = RECEIVE_EXIT_DISTANCE if state['latched'] else RECEIVE_ENTER_DISTANCE
        close = (dist(r['pos'],ball) < limit and (r['ir'] or
                 angle_error(r['heading'],bearing(r['pos'],ball)) < .22))
        if not (close and speed < 200 and r['speed'] < 200):
            state['latched'], state['elapsed'], state['last'] = False, 0.0, None
            return False
        if state['last'] is not None:
            state['elapsed'] += max(0.0,now-state['last'])
        state['last'], state['latched'] = now, True
        return state['elapsed'] >= RECEIVE_CONFIRM_DURATION

    def ready(self, n, target, face, own):
        r = own[n]
        return (dist(r['pos'], target) < 100 and r['speed'] < 150
                and angle_error(r['heading'], bearing(r['pos'],face)) < .18)

    def departed(self, n, own, ball, speed):
        return (self.origin is not None and dist(ball,self.origin) > 100
                and dist(own[n]['pos'],ball) > 180 and speed > 250)

    def near_penalty(self, p):
        return (abs(p[0]) >= Params.pitchLength/2-Params.penaltyDepth-150
                and abs(p[1]) <= Params.penaltyWidth/2+150)

    def receiver_side(self, ball):
        return dist(ball,PASS_POINT) < dist(ball,SHOT_POINT)

    def move(self, n, target, face, dribble=False, slow=False):
        self.labels[n] = 'RushTo hold' if dribble else 'RushTo position'
        return RushTo(CGeoPoint(*target), angle=bearing(self.own[n]['pos'],face),
                      maxAcc=1200, flag=MOVE_FLAGS | (0 if dribble else Flags.dodge_ball)
                      | (Flags.slowly if slow else 0),
                      needDribble=dribble)

    def corner_move(self, n, face):
        """Keep SimpleGoTo; use its slow flag for the final approach to the edge."""
        if self.phase == 'SETUP' and dist(self.own[n]['pos'],PASS_POINT) < 1200:
            self.corner_slow = True
        self.labels[n] = 'SimpleGoTo corner'
        if self.corner_slow:
            self.labels[n] = 'SimpleGoTo corner / slow approach'
            return SimpleGoTo(CGeoPoint(*PASS_POINT),angle=bearing(PASS_POINT,face),flag=Flags.slowly)
        return SimpleGoTo(CGeoPoint(*PASS_POINT),angle=bearing(PASS_POINT,face))

    def shot_move(self, n, face):
        """Use the same supplied movement skill throughout the off-ball run."""
        self.labels[n] = 'SimpleGoTo shot'
        return SimpleGoTo(CGeoPoint(*SHOT_POINT), angle=bearing(SHOT_POINT,face))

    def stationary_finish(self, n, goal, own, ball):
        """Meet the return near SHOT_POINT, then hold on contact; never dribble."""
        r = own[n]
        target = self.finish_target
        vx,vy = self.ball_velocity
        v2 = vx*vx+vy*vy
        arrival_seconds = None
        gap = dist(r['pos'],ball)
        dx,dy = ball[0]-r['pos'][0],ball[1]-r['pos'][1]
        forward = dx*math.cos(r['heading'])+dy*math.sin(r['heading'])
        lateral = -dx*math.sin(r['heading'])+dy*math.cos(r['heading'])
        mouth_ready = 0 < forward < 180 and abs(lateral) < 55 and gap < 180
        # Arming the kicker does not prove contact or ball departure. If the
        # request did not produce an outgoing shot, re-center behind the ball.
        # plan() handles observed departure before calling this function.
        now = time.monotonic()
        if (self.shot_skill_started and self.finish_request_time is not None
                and now-self.finish_request_time >= .25):
            gx,gy = goal[0]-r['pos'][0],goal[1]-r['pos'][1]
            goal_distance = max(math.hypot(gx,gy),1)
            outgoing = (vx*gx+vy*gy)/goal_distance > 500 and gap > 180
            if not outgoing:
                self.shot_skill_started = False
                self.finish_request_time = None
                self.finish_contact = False
                self.finish_recover = True
        if not mouth_ready and not self.shot_skill_started:
            # A stopped, passed, or clearly off-line return cannot be met by
            # holding the original 250 mm receiving circle. Go behind that ball.
            t = -(dx*vx+dy*vy)/v2 if v2 > 200**2 else None
            miss = math.hypot(dx+vx*t,dy+vy*t) if t is not None else gap
            if (v2 <= 200**2 or (t is not None and
                    (t <= 0 or (t <= FINISH_ADJUST_LEAD_SECONDS and miss > 250)))):
                self.finish_recover = True
                self.finish_contact = False
        if self.finish_recover:
            # A failed return still beside P2 is P2's job. Never send P1 back
            # across the pitch to take over collection from the receiver.
            if self.receiver_side(ball):
                self.watch_phase = 'FINISH'
                self.change('FAULT','return stayed on receiver side: retry reception',now)
                self.labels[n] = 'Stop: receiver owns failed return'
                CppPackage.setDribbleCommand(n,0)
                return Stop()
            facing = bearing(ball,goal)
            # A nearby stationary ball still needs contact. Merely arming the
            # kicker at 98 mm must not lock us just short of the ball forever.
            if not self.shot_skill_started or (v2 < 200**2 and mouth_ready):
                target = (ball[0]-90*math.cos(facing),ball[1]-90*math.sin(facing))
            if (self.near_penalty(ball) or self.near_penalty(target)
                    or abs(target[0]) >= Params.pitchLength/2-110
                    or abs(target[1]) >= Params.pitchWidth/2-110):
                self.labels[n] = 'Stop: loose return in protected area'
                CppPackage.setDribbleCommand(n,0)
                return Stop()
        elif not self.finish_contact:
            if (r.get('ir',False)
                    or (gap < 110 and 0 < forward <= 90 and abs(lateral) <= 15)):
                # Freeze translation when the ball reaches the mouth, not when
                # it brushes the side (52 mm lateral in the failed recording).
                # isBallKicked is a command indicator here, not physical contact.
                self.finish_contact = True
                if dist(r['pos'],SHOT_POINT) <= 250 and not self.near_penalty(r['pos']):
                    target = r['pos']
            elif gap < 110 and forward > 0 and abs(lateral) < 55:
                # Close but off-center: make a local mouth correction, not a
                # jump back to the nominal shooting point or a permanent lock.
                if v2 > 200**2 and abs(lateral) <= 15:
                    target = r['pos']
                else:
                    facing = bearing(ball,goal)
                    candidate = (ball[0]-90*math.cos(facing),ball[1]-90*math.sin(facing))
                    if dist(candidate,SHOT_POINT)<=250 and not self.near_penalty(candidate):
                        target = candidate
            elif v2 > 200**2:
                theta0 = bearing(SHOT_POINT,goal)
                mouth = (SHOT_POINT[0]+100*math.cos(theta0),
                         SHOT_POINT[1]+100*math.sin(theta0))
                t = ((mouth[0]-ball[0])*vx+(mouth[1]-ball[1])*vy)/v2
                arrival_seconds = t
                # Hold the original receiving point while the ball is far away.
                # Once close, retain the existing small correction and contact stop.
                if 0 < t <= FINISH_ADJUST_LEAD_SECONDS:
                    hit = (ball[0]+vx*t,ball[1]+vy*t)
                    facing = bearing(hit,goal)
                    candidate = (hit[0]-100*math.cos(facing),hit[1]-100*math.sin(facing))
                    dx,dy = candidate[0]-SHOT_POINT[0],candidate[1]-SHOT_POINT[1]
                    scale = min(1.0,250/max(math.hypot(dx,dy),1.0))
                    candidate = (SHOT_POINT[0]+dx*scale,SHOT_POINT[1]+dy*scale)
                    if not self.near_penalty(candidate):
                        target = candidate
        self.finish_target = target
        theta = bearing(r['pos'],goal)
        move_task = SimpleGoTo(CGeoPoint(*target),angle=theta)
        self.labels[n] = 'SimpleGoTo meet return / no dribble'
        error = angle_error(r['heading'],theta)
        can_kick = ((self.finish_recover or dist(r['pos'],SHOT_POINT) <= 250)
                    and not self.near_penalty(r['pos']) and error <= Precision.MIDDLE
                    and 0 < forward < 180 and abs(lateral) < 55 and gap < 180)
        if self.finish_recover:
            self.labels[n] = 'SimpleGoTo loose return / no dribble'
        power = None
        if can_kick:
            # A ball passing the side can arm the kicker without ever touching
            # it. Allow the existing local correction to finish before starting
            # the one-second failed-contact clock; the five-second phase cap remains.
            if (self.finish_attempt_since is None and 0 < forward < 110
                    and abs(lateral) < 20 and gap < 110):
                self.finish_attempt_since = now
            power = evalPower(CGeoPoint(*ball),CGeoPoint(*goal),P.HIGH)*KICK_POWER_SCALE
            if not math.isfinite(power) or power <= 0:
                raise ValueError('PowerCalculator returned invalid power')
            self.powers[n] = self.last_requested[n] = power
            # A kicker request, not confirmation of a physical kick.
            if not self.shot_skill_started:
                self.finish_request_time = now
            self.shot_skill_started = True
            self.labels[n] = 'SimpleGoTo meet return + kick / no dribble'
        self.stationary_shot_diagnostic = dict(cycle=vision.getCycle(),robot=n,stage='planned',
            hold_point=target,target=goal,ball_gap=gap,heading_error=error,
            ball_forward=forward,ball_lateral=lateral,contact_locked=self.finish_contact,
            position_error=dist(r['pos'],SHOT_POINT),robot_speed=r['speed'],
            precision_rad=Precision.MIDDLE,
            arrival_seconds=arrival_seconds,adjust_lead_seconds=FINISH_ADJUST_LEAD_SECONDS,
            loose_return_recovery=self.finish_recover,
            kick_requested=can_kick,power=self.powers.get(n))
        diagnostic = self.stationary_shot_diagnostic
        move_execute,match = move_task
        def execute(number):
            value = move_execute(number)
            CppPackage.setDribbleCommand(number,0)
            # StateMachine clears kickStatus on EVERY execution, even when the
            # vision cycle and cached movement task are unchanged.
            if power is not None:
                kickStatus.setKick(number,power)
            diagnostic.update(stage='after_SimpleGoTo_execution',
                need_kick=bool(kickStatus.needKick(number)),
                kick_status_power=kickStatus.getKickPower(number),
                force_closed=bool(kickStatus.isForceClosed()))
            status = (diagnostic['need_kick'],self.finish_recover,diagnostic['force_closed'])
            stamp = time.monotonic()
            if status != self.last_finish_status or stamp-self.last_finish_log >= .1:
                self.last_finish_log,self.last_finish_status = stamp,status
                with Path('LOG/prelim_combo_finish_blue.jsonl').open('a',encoding='utf-8') as output:
                    output.write(json.dumps(dict(diagnostic,time=time.time(),
                        version='combo_2.32_dynamic_roles',round_number=self.round_number))+'\n')
            return value
        return execute,match

    def receive_visibility(self, now, own):
        """After departure, localize each robot separately; never chase an unseen ball."""
        missing = {'ball':not self.ball_valid, self.p1:self.p1 not in own, self.p2:self.p2 not in own}
        for key,lost in missing.items():
            if lost:
                self.receive_missing_since.setdefault(key,now)
            else:
                self.receive_missing_since.pop(key,None)
        if any(now-t > 2 for t in self.receive_missing_since.values()):
            self.change('FAULT','receive visibility unavailable too long',now)
            return None
        if not any(missing.values()):
            self.receiver_wait_pos = None
            self.reason = ('P2 receive; P1 run to shot point' if self.phase=='RECEIVE1'
                           else 'P2 turn to shot point; wait for P1' if self.phase=='WAIT_RETURN'
                           else 'first pass received; P1 finish run; no return pass')
            return None
        self.reason = 'receive visibility gap: P1 runs if visible; P2 holds if visible'
        if self.phase == 'RECEIVE1':
            self.confirm_reception(now)
        skills = {}
        if self.p1 in own:
            skills[self.p1] = self.shot_move(self.p1,PASS_POINT)
        if self.p2 in own:
            if self.phase == 'WAIT_RETURN':
                # Continue the supplied non-kicking ball-control skill through brief gaps.
                skills[self.p2] = GetBallV4(CGeoPoint(*RETURN_AIM_POINT))
                self.labels[self.p2] = 'GetBallV4 face shot / no kick'
            else:
                if self.receiver_wait_pos is None:
                    self.receiver_wait_pos = own[self.p2]['pos']
                skills[self.p2] = self.move(self.p2,self.receiver_wait_pos,
                    self.last_valid_ball or self.origin or (0,0),dribble=True,slow=True)
                self.labels[self.p2] = 'RushTo hold / no blind chase'
        return skills

    def held_contact(self, n, own, ball):
        r = own[n]
        return (dist(r['pos'],ball) < 125 and (r['ir'] or
            angle_error(r['heading'],bearing(r['pos'],ball)) < .28))

    def setup_contact(self, n, own, ball):
        # Enter with the original contact rule; leave only outside the wider
        # mouth envelope. This hysteresis is exclusive to preparation.
        if self.setup_held:
            self.setup_held = self.held_contact(n,own,ball)
        else:
            self.setup_held = self.contact(n,own,ball)
        return self.setup_held

    def setup_ready(self, now, prepared):
        if not prepared:
            self.setup_elapsed, self.setup_last = 0.0, None
            return False
        if self.setup_last is not None:
            self.setup_elapsed += max(0.0,now-self.setup_last)
        self.setup_last = now
        return self.setup_elapsed >= .15

    def collect_hold(self, n, face, own, ball, secured=None):
        if self.near_penalty(ball):
            self.labels[n] = 'Stop: ball in protected area'
            return Stop()
        if secured is None:
            secured = self.contact(n,own,ball)
        if secured:
            anchor = self.hold.setdefault(n,own[n]['pos'])
            return self.move(n,anchor,face,True)
        self.hold.pop(n,None)
        self.labels[n] = 'GetBallV4'
        return GetBallV4(CGeoPoint(*face))

    def pass_skill(self, n, target, ball, intercept=False, shot=False, first_pass=False):
        is_return = not first_pass and not shot and not intercept
        # Change return aim only; retain the previous distance-based power reference.
        power_target = SHOT_POINT if is_return else target
        power = evalPower(CGeoPoint(*ball), CGeoPoint(*power_target),
                          P.HIGH if (shot or first_pass or is_return) else P.NORMAL)
        power *= KICK_POWER_SCALE * (RETURN_POWER_FACTOR if is_return else 1.0)
        self.powers[n] = power
        self.last_requested[n] = power
        if not math.isfinite(power) or power <= 0:
            raise ValueError('PowerCalculator returned invalid power')
        if is_return:
            self.labels[n] = 'Shoot return pass'
            theta = bearing(ball,target)
            skill,match = Shoot(CGeoPoint(*target), direction=theta, power=power,
                                flag=MOVE_FLAGS, precision=Precision.HIGH)
            def execute_return(number):
                value = skill(number)
                fresh_ball = xy(Ball.pos())
                error = angle_error(Player.direction(number),theta)
                # Supplied Shoot permits IR to bypass its direction check.
                # Keep its motion and power; veto that shortcut at execution.
                aimed = (self.ball_valid and bool(vision.ball().Valid())
                         and error <= Precision.HIGH
                         and angle_error(theta,bearing(fresh_ball,target)) <= Precision.HIGH)
                if not aimed:
                    kickStatus.clearAll()
                record = dict(time=time.time(),cycle=vision.getCycle(),
                    version='combo_2.32_dynamic_roles',phase='PASS2',robot=number,
                    target=target,power_target=power_target,angle_error_rad=error,precision_rad=Precision.HIGH,
                    ball_valid=bool(self.ball_valid),infrared=bool(Player.isInfraredOn(number)),
                    aim_ready=aimed,need_kick=bool(kickStatus.needKick(number)),
                    requested_power=power,round_number=self.round_number)
                self.return_diagnostic = record
                stamp = time.monotonic()
                status = (aimed,record['need_kick'])
                if status != self.last_return_status or stamp-self.last_return_log >= .1:
                    self.last_return_status,self.last_return_log = status,stamp
                    with Path('LOG/prelim_combo_return_blue.jsonl').open('a',encoding='utf-8') as output:
                        output.write(json.dumps(record)+'\n')
                return value
            return execute_return,match
        if first_pass:
            self.labels[n] = 'SimpleGoTo stationary first pass'
            theta = bearing(ball,target)
            # Shoot moves to Ball.pos() whenever IR is off, even while its kick
            # is blocked by our accuracy check. Hold the body at a fresh anchor
            # instead; neither ball drift nor a vision resume may advance it.
            if self.first_pass_anchor is None:
                self.first_pass_anchor = tuple(self.own[n]['pos'])
            anchor = self.first_pass_anchor
            skill, match = SimpleGoTo(CGeoPoint(*anchor), angle=theta)
            def execute(number):
                kickStatus.clearAll()
                value = skill(number)
                CppPackage.setDribbleCommand(number,3)
                error = angle_error(Player.direction(number),theta)
                now = time.monotonic()
                aimed = self.first_pass_aligned(now,number,target,xy(Ball.pos()),theta)
                if error > Precision.HIGH:
                    self.first_aim_since = self.first_aim_last = None
                    aimed = False
                if aimed:
                    # Issue after motion execution, which runs after the state
                    # machine clears KickStatus. No chase skill or IR shortcut.
                    kickStatus.setKick(number,power)
                record = dict(time=time.time(),cycle=vision.getCycle(),version='combo_2.32_dynamic_roles',
                    phase='PASS1',robot=number,skill='SimpleGoTo',hold_position=anchor,
                    target=target,target_heading=theta,
                    angle_error_rad=error,precision_rad=Precision.HIGH,
                    geometric_aligned=error <= Precision.HIGH,
                    infrared=bool(Player.isInfraredOn(number)),
                    kick_feedback=bool(Player.isBallKicked(number)),
                    requested_power=power,need_kick=bool(kickStatus.needKick(number)),
                    kick_status_power=kickStatus.getKickPower(number),
                    force_closed=bool(kickStatus.isForceClosed()),
                    aim_ready=aimed,
                    stage='after_stationary_first_pass_execution')
                self.first_pass_kick_requested |= record['need_kick']
                self.shoot_diagnostic = record
                status = (number,record['geometric_aligned'],record['infrared'],
                          record['need_kick'],record['force_closed'])
                if status != self.last_shoot_status or now-self.last_shoot_log >= .1:
                    self.last_shoot_log,self.last_shoot_status = now,status
                    with Path('LOG/prelim_combo_shoot_blue.jsonl').open('a',encoding='utf-8') as output:
                        output.write(json.dumps(record)+'\n')
                return value
            return execute, match
        self.labels[n] = 'GoAndTurnKick intercept' if intercept else 'GoAndTurnKick pass'
        return GoAndTurnKick(CGeoPoint(*target), registerRole='leader', power=power,
                             flag=MOVE_FLAGS, useInter=intercept)

    def pause_vision(self, now, reason):
        if self.phase in ('FAULT','DONE'):
            return
        if self.phase == 'PASS1' or (self.pause and self.pause['phase']=='PASS1'):
            self.first_aim_gap = True
        else:
            self.first_aim_since = self.first_aim_last = None
        if self.phase=='SETUP':
            # Full pause (long ball loss, missing robot, stalled vision) must
            # revalidate possession and readiness when observations return.
            self.setup_held = False
            self.setup_elapsed, self.setup_last = 0.0, None
        if self.phase == 'RECEIVE1':
            self.reception = dict(latched=False, elapsed=0.0, last=None, gap=None)
        if self.pause is None:
            self.pause = dict(time=now, phase=self.phase, reason=self.reason,
                              entered=self.entered, ball=self.last_valid_ball,
                              kick_seen=False, max_recovery_moved=0)
        if self.pause['phase']=='PASS2' and 'anchor' not in self.pause:
            receiver = getattr(self,'own',{}).get(self.p2)
            if receiver is not None:
                x,y = receiver['pos']
                heading = receiver['heading']
                self.pause['anchor'] = (x,y)
                self.pause['face'] = (x+1000*math.cos(heading),y+1000*math.sin(heading))
        passer = self.p1 if self.pause['phase']=='PASS1' else self.p2
        if self.pause['phase'] in ('PASS1','PASS2'):
            self.pause['kick_seen'] |= bool(getattr(self,'own',{}).get(passer,{}).get('kicked',False))
        self.phase, self.reason = 'VISION_WAIT', reason
        self.recovered_since = None
        self.since.clear()
        # SETUP can safely wait without kicking: remain stopped until fresh
        # ball AND attacker observations return, rather than latching FAULT.
        if self.pause['phase'] != 'SETUP' and now-self.pause['time'] > 2:
            self.change('FAULT','vision unavailable too long: reset round',now)

    def resume_vision(self, now, own, ball, speed):
        """Return only after fresh stable visibility; never blindly replay a pass."""
        saved = self.pause
        if saved['phase'] == 'SETUP':
            # getTasks calls this only on a new valid ball/attacker frame.
            # Do not require 0.2 s uninterrupted visibility before collecting.
            self.phase, self.reason = 'SETUP', saved['reason']
            self.entered = (saved['entered']+now-saved['time']
                            if saved['entered'] is not None else now)
            self.since.clear()
            self.pause = None
            self.recovered_since = None
            return True
        if saved['ball'] is not None:
            saved['max_recovery_moved'] = max(saved['max_recovery_moved'],dist(ball,saved['ball']))
        if saved['phase'] in ('PASS1','PASS2'):
            passer = self.p1 if saved['phase']=='PASS1' else self.p2
            saved['kick_seen'] |= own[passer]['kicked']
        if now-saved['time'] > 2:
            self.change('FAULT','vision recovery timed out: reset round',now)
            return False
        if (saved['phase']=='PASS1' and self.origin is not None
                and dist(ball,self.origin) > 100
                and dist(own[self.p1]['pos'],ball) > 180):
            # A fresh observation already proves departure. Resume reception
            # without waiting for uninterrupted visibility or reissuing Shoot.
            self.carry[self.p1] = 0
            self.hold.pop(self.p1,None)
            self.shot_origin = None
            self.change('RECEIVE1','first pass departure seen after vision recovery',now)
            self.pause = None
            self.recovered_since = None
            return True
        if (saved['phase']=='PASS1' and not saved['kick_seen']
                and not self.first_pass_kick_requested):
            if dist(own[self.p1]['pos'],ball) < 180:
                # Keep the same body anchor through a vision gap. Fresh direction,
                # contact and speed are still required before any kick is issued.
                self.phase = 'PASS1'
                self.reason = 'un-kicked first pass visible: resume stationary aim'
                self.entered = saved['entered']+now-saved['time']
                self.since.clear()
            else:
                # A genuinely distant, un-kicked ball needs collection again.
                self.hold.pop(self.p1,None)
                self.setup_held = False
                self.setup_elapsed, self.setup_last = 0.0, None
                self.first_aim_since = self.first_aim_last = None
                self.first_aim_gap = False
                self.first_pass_anchor = None
                self.change('SETUP','un-kicked ball visible: recollect and aim',now)
            self.pause = None
            self.recovered_since = None
            return True
        if saved['phase']=='PASS2':
            # A fresh visible observation can resolve this pause. Requiring 0.2 s
            # uninterrupted visibility starves recovery when the ball flickers.
            gap = dist(own[self.p2]['pos'],ball)
            moved = dist(ball,self.origin) if self.origin is not None else 0
            if moved > 100 and gap > 180:
                self.carry[self.p2] = 0
                self.hold.pop(self.p2,None)
                self.shot_origin = None
                self.change('FINISH','return departure seen after vision recovery',now)
            elif gap < 180 and not saved['kick_seen']:
                # The supplied return skill handles a nearby moving ball. A small
                # dribbling velocity is not evidence that the return has failed.
                self.phase = 'PASS2'
                self.reason = 'nearby ball visible: resume Shoot'
                self.entered = saved['entered']+now-saved['time']
                self.since.clear()
            else:
                self.change('FAULT','return outcome unclear after vision recovery',now)
            self.pause = None
            self.recovered_since = None
            return self.phase != 'FAULT'
        if self.recovered_since is None:
            self.recovered_since = now
        if now-self.recovered_since < .2:
            self.reason = 'vision restored: checking fresh frames'
            return False
        phase = saved['phase']
        if phase in ('PASS1','PASS2'):
            passer = self.p1 if phase=='PASS1' else self.p2
            gap = dist(own[passer]['pos'],ball)
            moved = dist(ball,self.origin) if self.origin is not None else 0
            if moved > 100 and gap > 180:
                # Ball may already have stopped while invisible: do not require speed.
                self.carry[passer] = 0
                self.hold.pop(passer,None)
                self.shot_origin = None
                self.change('RECEIVE1' if phase=='PASS1' else 'FINISH',
                            'pass departure seen after vision recovery',now)
            elif (saved['ball'] is not None and saved['max_recovery_moved'] < 50 and speed < 180
                  and self.contact(passer,own,ball) and not saved['kick_seen']
                  and (phase!='PASS1' or not self.first_pass_kick_requested)):
                # Go through the readiness checks again before allowing the native skill.
                self.change('SETUP' if phase=='PASS1' else 'WAIT_RETURN',
                            'ball still at passer: recheck readiness',now)
                self.hold[passer] = own[passer]['pos']
            else:
                self.change('FAULT','pass outcome unclear after vision recovery',now)
        elif phase == 'FINISH':
            if self.shot_skill_started:
                # Preserve the existing behavior once the shooting skill was issued.
                self.change('FAULT','final shot interrupted: inspect before reset',now)
            else:
                # FINISH also includes waiting for the return ball, before any shot.
                self.phase = 'FINISH'
                self.reason = 'return ball visible: resume waiting for reception'
                self.entered = (saved['entered']+now-saved['time']
                                if saved['entered'] is not None else now)
                self.since.clear()
        else:
            self.phase, self.reason = phase, saved['reason']
            self.entered = (saved['entered']+now-saved['time']
                            if saved['entered'] is not None else now)
            self.since.clear()
        self.pause = None
        self.recovered_since = None
        return self.phase not in ('FAULT','DONE')

    def paused_return_tasks(self, own):
        # No kick task while perception is missing. Keep the visible receiver's
        # mouth/heading fixed with the existing supplied dribbling position skill.
        skills = {}
        if self.p1 in own:
            skills[self.p1] = self.shot_move(self.p1,(Params.pitchLength/2,0))
        if self.p2 in own and 'anchor' in self.pause:
            skills[self.p2] = self.move(self.p2,self.pause['anchor'],self.pause['face'],True)
            self.labels[self.p2] = 'Return paused / hold / no kick'
        return skills

    def can_continue_return(self, now, own):
        return (self.phase=='PASS2' and len(own)==2 and self.return_skill is not None
                and self.last_valid_time is not None
                and 0 <= now-self.last_valid_time <= RETURN_VISION_GRACE
                and self.last_valid_ball is not None
                and dist(own[self.p2]['pos'],self.last_valid_ball) < 180
                and not own[self.p2]['kicked'] and now-self.entered <= 5)

    def getTasks(self):
        # State.run matches roles before evaluating these delayed skills.
        # Never read a physical robot or plan a kick before that match completes.
        cycle = vision.getCycle()
        if Global.isPlaySwitched and cycle != self.last_reset_cycle:
            self.attackers = ()
            self.reset()
            self.last_reset_cycle = cycle
        if not self.attackers:
            self.achedMatchPos['A'] = Ball.pos()
            self.achedMatchPos['B'] = CGeoPoint(*PASS_POINT)
        return {role: Task(lambda runner, role=role: self.role_skill(role, runner))
                for role in ROLES}

    def role_skill(self, role, runner):
        assigned = tuple(Global.getRoleNumber(name) for name in ROLES)
        if min(assigned) < 0 or len(set(assigned)) != 2:
            kickStatus.clearAll()
            for number in assigned:
                if number >= 0:
                    CppPackage.setDribbleCommand(number, 0)
            self.reason = 'waiting for two assigned robots'
            self.draw({})
            # State also queries matchPos for an unassigned runner (-1).
            return Stop()[0], lambda _n: self.achedMatchPos[role]
        if assigned != self.attackers:
            # A new Play (or completion of an initial partial match) starts clean.
            # Normal round resets never change the identity mapping.
            self.attackers = assigned
            self.reset()
        skills = self.plan_tasks()
        selected = skills.get(runner, Stop())
        # Skills with executor-dependent match positions must not query missing
        # robot vision. The retained position is sufficient for Never matching.
        if not Player.isValid(runner):
            return Stop()[0], lambda _n: self.achedMatchPos[role]
        return selected

    def plan_tasks(self):
        now, cycle = time.monotonic(), vision.getCycle()
        if cycle == self.cached_cycle:
            if now-self.cached_time <= .12:
                return self.cached_tasks
            kickStatus.clearAll()
            for n in self.attackers:
                CppPackage.setDribbleCommand(n,0)
            self.powers = {}
            self.labels = {n:'Stop' for n in self.attackers}
            self.return_grace_active = False
            self.pause_vision(now,'vision cycle stalled: all robots paused')
            return self.stop_tasks()
        kickStatus.clearAll()
        for n in self.attackers:
            CppPackage.setDribbleCommand(n,0)
        own = {n: dict(pos=xy(Player.Pos(n)), heading=Player.direction(n),
                       speed=Player.velMod(n), ir=bool(Player.isInfraredOn(n)),
                       kicked=bool(Player.isBallKicked(n)))
               for n in self.attackers if Player.isValid(n)}
        ball, velocity = xy(Ball.pos()), xy(Ball.vel())
        speed = math.hypot(*velocity)
        ball_valid = bool(vision.ball().Valid())
        self.ball_velocity = velocity
        escape_skills = self.recovery_skills(now,own,ball_valid)
        self.restart_after_shot(now,own,ball,speed,ball_valid)
        self.ball_velocity = velocity
        self.own = own
        self.labels = {n:'Stop' for n in self.attackers}
        self.powers = {}
        self.ball_valid = ball_valid
        if self.ball_valid:
            self.max_speed = max(self.max_speed,speed)
        if self.entered is None:
            self.entered = now
        self.check_deadline(now)
        self.return_grace_active = False
        invalid = (not self.ball_valid or len(own) != 2)
        can_plan = True
        receive_skills = None
        if self.phase in ('RECEIVE1','FIRST_PASS_OK','WAIT_RETURN'):
            receive_skills = self.receive_visibility(now,own)
            can_plan = receive_skills is None and not invalid
        elif (invalid and self.phase=='SETUP' and len(own)==2
              and self.setup_skills is not None and self.last_valid_time is not None
              and 0 <= now-self.last_valid_time <= SETUP_VISION_GRACE):
            # Reissue only the preceding SETUP skills, never a pass or kick.
            # Do not infer possession/readiness from a stale ball observation.
            receive_skills = self.setup_skills
            self.labels = self.setup_labels.copy()
            self.reason = 'brief ball gap: continue same setup skills'
            self.setup_last = None  # Freeze confirmed time; do not count unseen time.
            can_plan = False
        elif invalid and self.can_continue_return(now,own):
            # Reissue the exact supplied skill, target and power from the fresh frame.
            # Do not infer reception or departure from a stale ball observation.
            self.return_grace_active = True
            self.labels[self.p2] = self.return_skill_label
            if self.return_power is not None:
                self.powers[self.p2] = self.return_power
            self.reason = 'brief ball gap: continue same return skill'
            receive_skills = {self.p1:self.shot_move(self.p1,(Params.pitchLength/2,0)),
                              self.p2:self.return_skill}
            can_plan = False
        elif invalid:
            self.pause_vision(now,'ball or attacker missing: all robots paused')
            can_plan = False
        elif self.phase == 'VISION_WAIT':
            can_plan = self.resume_vision(now,own,ball,speed)
        if (self.phase=='VISION_WAIT' and self.pause is not None
                and self.pause['phase']=='PASS2'):
            receive_skills = self.paused_return_tasks(own)
        elif (self.phase=='VISION_WAIT' and self.pause is not None
              and self.pause['phase']=='FINISH' and not self.shot_skill_started):
            # Keep the last receiving target through a gap; do not jump back to SHOT_POINT.
            receive_skills = ({self.p1:SimpleGoTo(CGeoPoint(*self.finish_target),
                angle=bearing(own[self.p1]['pos'],(Params.pitchLength/2,0)))}
                              if self.p1 in own else {})
        if not invalid and self.phase not in ('FAULT','DONE'):
            for n in self.attackers:
                if self.contact(n,own,ball) and n in self.previous:
                    self.carry[n] += dist(own[n]['pos'],self.previous[n])
                self.previous[n] = own[n]['pos']
            if (speed > 6200 or any(v >= 800 for v in self.carry.values())
                or any(self.near_penalty(r['pos']) for r in own.values())
                or abs(ball[0]) > Params.pitchLength/2 or abs(ball[1]) > Params.pitchWidth/2):
                self.change('FAULT','speed / carry / field guard: reset round',now)
        # Penalty buffers constrain robots, not a ball passing through them.
        # Robot positions remain meaningful when only ball visibility is lost.
        if self.phase not in ('FAULT','DONE') and any(
            self.near_penalty(r['pos']) or abs(r['pos'][0])>Params.pitchLength/2-110
            or abs(r['pos'][1])>Params.pitchWidth/2-110 for r in own.values()):
            self.change('FAULT','robot field margin / penalty guard',now)
        if self.ball_valid and self.phase not in ('FAULT','DONE') and (
            speed>6200 or abs(ball[0])>Params.pitchLength/2
            or abs(ball[1])>Params.pitchWidth/2):
            self.change('FAULT','ball speed / field guard',now)
        if not invalid:
            self.last_valid_ball = ball
            self.last_valid_time = now
            self.last_valid_speed = speed
        tasks = self.stop_tasks()
        if self.phase in ('FAULT','DONE') and escape_skills:
            for n in escape_skills:
                self.labels[n] = 'SimpleGoTo exit guard / no kick / no dribble'
            tasks = {n: escape_skills.get(n,Stop()) for n in self.attackers}
        elif receive_skills is not None and self.phase not in ('FAULT','DONE'):
            tasks = {n: receive_skills.get(n,Stop()) for n in self.attackers}
        elif can_plan and self.phase not in ('FAULT','DONE','VISION_WAIT'):
            try:
                skills = self.plan(now,own,ball,speed)
                if self.phase=='SETUP':
                    self.setup_skills = skills.copy()
                    self.setup_labels = self.labels.copy()
                if self.phase=='PASS2' and self.labels.get(self.p2)=='Shoot return pass':
                    self.return_skill = skills[self.p2]
                    self.return_skill_label = self.labels[self.p2]
                    self.return_power = self.powers.get(self.p2)
                else:
                    self.return_skill = None

                tasks = {n: skills.get(n,Stop()) for n in self.attackers}
            except ValueError as error:
                self.change('FAULT',str(error),now)
                tasks = self.stop_tasks()
        self.draw(own)
        self.log(now,cycle,own,ball,velocity)
        self.cached_cycle, self.cached_time, self.cached_tasks = cycle, now, tasks
        return tasks

    def plan(self, now, own, ball, speed):
        if self.p1 is None:
            # Reuse the role assignment across every round and receiver retry.
            self.p1, self.p2 = self.attackers
        a,b = self.p1,self.p2
        goal = (Params.pitchLength/2,0)
        if self.phase not in ('FIRST_PASS_OK',) and now-self.entered > (18 if self.phase=='SETUP' else 10):
            self.change('FAULT','phase timed out: '+self.phase,now)
            return {}
        if self.phase == 'SETUP':
            secured = self.setup_contact(a,own,ball)
            if self.first_pass_reacquiring and not self.first_pass_mouth_ready(a,own,ball):
                # Proximity/IR alone must not re-lock the same off-center ball.
                secured = self.setup_held = False
            skills = {a:self.collect_hold(a,PASS_POINT,own,ball,secured=secured),
                      b:self.corner_move(b,own[a]['pos'])}
            prepared = (secured and own[a]['speed']<150 and speed<180
                        and angle_error(own[a]['heading'],bearing(own[a]['pos'],PASS_POINT))<.18
                        and self.ready(b,PASS_POINT,own[a]['pos'],own))
            if self.setup_ready(now,prepared):
                self.origin = ball
                self.first_pass_anchor = tuple(own[a]['pos'])
                self.first_pass_reacquiring = False
                self.change('PASS1','P1 pass to P2',now)
                self.setup_held = False
                self.setup_elapsed, self.setup_last = 0.0, None
            return skills
        if self.phase == 'PASS1':
            if self.departed(a,own,ball,speed):
                self.change('RECEIVE1','P2 receive; P1 run to shot point',now)
                self.carry[a] = 0
                self.hold.pop(a,None)
                return {a:self.shot_move(a,PASS_POINT),b:self.receive(b,ball,own,ball)}
            if now-self.entered > FIRST_PASS_TIMEOUT:
                self.change('FAULT','first pass did not depart',now)
                return {}
            if (not self.first_pass_kick_requested and not own[a]['kicked']
                    and speed < 180 and dist(own[a]['pos'],ball) < 180
                    and not self.first_pass_mouth_ready(a,own,ball)):
                # This un-kicked, nearby ball cannot be centered by rotating a
                # fixed body anchor. Let supplied GetBallV4 re-seat it, then use
                # the unchanged preparation and accurate stationary release.
                self.first_pass_reacquiring = True
                self.first_pass_anchor = None
                self.hold.pop(a,None)
                self.setup_held = False
                self.setup_elapsed, self.setup_last = 0.0, None
                self.first_aim_since = self.first_aim_last = None
                self.first_aim_gap = False
                self.change('SETUP','un-kicked first pass off mouth: reacquire locally',now)
                return {a:self.collect_hold(a,PASS_POINT,own,ball,secured=False),
                        b:self.corner_move(b,own[a]['pos'])}
            return {a:self.pass_skill(a,PASS_POINT,ball,first_pass=True),
                    b:self.corner_move(b,own[a]['pos'])}
        if self.phase == 'RECEIVE1':
            # Face the visible incoming ball until contact is stable; turn only afterwards.
            skills = {a:self.shot_move(a,PASS_POINT),b:self.receive(b,ball,own,ball)}
            if self.confirm_reception(now,own,ball,speed):
                self.hold[b] = own[b]['pos']
                if self.checkpoint == 'first_pass':
                    self.change('FIRST_PASS_OK','first pass received; checkpoint holds ball',now)
                else:
                    self.change('WAIT_RETURN','P2 turn to shot point; wait for P1',now)
            return skills
        if self.phase == 'FIRST_PASS_OK':
            # Complete the authorized off-ball run, but never return-pass in checkpoint mode.
            # Keep the same zero-terminal-velocity position task in visible and
            # brief ball-loss frames, including after arrival; do not alternate Stop.
            return {a:self.shot_move(a,PASS_POINT),
                    b:self.move(b,self.hold[b],SHOT_POINT,True)}
        if self.phase == 'WAIT_RETURN':
            # GetBallV4's argument is the facing target, not the ball location.
            # It owns collection and turning; keep calling it while P1 runs.
            self.labels[b] = 'GetBallV4 face shot / no kick'
            skills = {a:self.shot_move(a,own[b]['pos']),
                      b:GetBallV4(CGeoPoint(*RETURN_AIM_POINT))}
            aligned = angle_error(own[b]['heading'],bearing(own[b]['pos'],RETURN_AIM_POINT)) < .18
            held = (dist(own[b]['pos'],ball) < RECEIVE_EXIT_DISTANCE and
                    (own[b]['ir'] or angle_error(own[b]['heading'],
                                                bearing(own[b]['pos'],ball)) < .22))
            self.reason = 'P2 turn to shot point; wait for P1'
            # No second reception timer and no consecutive-visible-frame gate.
            if held and aligned and self.ready(a,SHOT_POINT,own[b]['pos'],own):
                self.origin = ball
                self.change('PASS2','P1 ready: return to shot point',now)
                skills[b] = self.pass_skill(b,RETURN_AIM_POINT,ball)
                skills[a] = self.shot_move(a,goal)
            return skills
        if self.phase == 'PASS2':
            if self.departed(b,own,ball,speed):
                self.carry[b] = 0
                self.shot_origin = None
                self.change('FINISH','P1 adjust to incoming ball; contact shot',now)
                return {a:self.stationary_finish(a,goal,own,ball)}
            if now-self.entered > 5:
                self.change('FAULT','return pass did not depart',now)
                return {}
            return {a:self.shot_move(a,goal),b:self.pass_skill(b,RETURN_AIM_POINT,ball)}
        if self.phase == 'FINISH':
            gap = dist(own[a]['pos'],ball)
            if gap < 180:
                self.shot_origin = ball
            if (self.shot_skill_started and self.shot_origin and gap>220 and dist(ball,self.shot_origin)>100
                and ball[0]>self.shot_origin[0]+80 and speed>500):
                self.change('DONE','shot finished: waiting for a settled playable ball',now)
                return {}
            # A requested kick is not a physical shot. Do not repeat close-ball
            # positioning for the full FINISH timeout when contact never fires.
            if self.finish_attempt_since is not None and now-self.finish_attempt_since >= 1.0:
                self.change('FAULT','contact shot did not depart: retry attack',now)
                return {}
            return {a:self.stationary_finish(a,goal,own,ball)}
        return {}

    def receive(self, n, face, own, ball):
        if self.receiver_recovery:
            # Recovery may require leaving the original receiving circle.
            # The designated receiver collects; P1 keeps its shooting task.
            return self.collect_hold(n,face,own,ball)
        # Once the first pass has departed, meet its trajectory early instead
        # of waiting at PASS_POINT until it enters the 1.2 m collection radius.
        # Before departure keep the original point for first-pass aim/readiness.
        vx,vy = self.ball_velocity
        v2 = vx*vx+vy*vy
        if self.phase == 'RECEIVE1' and v2 > 200**2 and dist(own[n]['pos'],ball) > 250:
            t = ((PASS_POINT[0]-ball[0])*vx+(PASS_POINT[1]-ball[1])*vy)/v2
            if 0 < t <= 1.5:
                hit = (ball[0]+vx*t,ball[1]+vy*t)
                speed = math.sqrt(v2)
                candidate = (hit[0]+100*vx/speed,hit[1]+100*vy/speed)
                dx,dy = candidate[0]-PASS_POINT[0],candidate[1]-PASS_POINT[1]
                scale = min(1.0,250/max(math.hypot(dx,dy),1))
                candidate = (PASS_POINT[0]+dx*scale,PASS_POINT[1]+dy*scale)
                if (not self.near_penalty(candidate)
                        and abs(candidate[0]) < Params.pitchLength/2-110
                        and abs(candidate[1]) < Params.pitchWidth/2-110):
                    self.labels[n] = 'SimpleGoTo meet first pass'
                    return SimpleGoTo(CGeoPoint(*candidate),angle=bearing(own[n]['pos'],ball))
        if dist(ball,PASS_POINT) < RECEIVE_DISTANCE:
            return self.collect_hold(n,face,own,ball)
        return self.corner_move(n,ball)

    def draw(self,own):
        debug = Global.debugEngine
        if self.phase == 'SETUP':
            debug.gui_debug_line(CGeoPoint(-700,0),CGeoPoint(700,0),debug_color=DebugColor.Green)
            debug.gui_debug_x(CGeoPoint(0,0),debug_color=DebugColor.Green)
            debug.gui_debug_msg(CGeoPoint(100,180),'RESET (0,0) / y=0',debug_color=DebugColor.Green)
        debug.gui_debug_msg(CGeoPoint(-4200,-2400),f'COMBO 2.32 DYNAMIC-ROLES {self.checkpoint} | {self.phase} | round {self.round_number}',
                            debug_color=DebugColor.White,size=150)
        debug.gui_debug_msg(CGeoPoint(-4200,-2600),self.reason,debug_color=DebugColor.Yellow,size=125)
        debug.gui_debug_msg(CGeoPoint(-4200,-2200),
                            f'A collect/finish -> {self.p1} | B receive/return -> {self.p2}',
                            debug_color=DebugColor.Cyan,size=125)
        power_text = ', '.join(f'#{n} {p:.0f}' for n,p in self.last_requested.items()) or '-'
        debug.gui_debug_msg(CGeoPoint(-4200,-2800),
                            f'Last power {power_text} | peak {self.max_speed/1000:.2f} m/s',
                            debug_color=DebugColor.Yellow,size=125)
        if self.shoot_diagnostic:
            d = self.shoot_diagnostic
            debug.gui_debug_msg(CGeoPoint(-4200,2700),
                f'Last Shoot #{d["robot"]} | dir {math.degrees(d["angle_error_rad"]):.1f} deg | '
                f'kick request {int(d["need_kick"])} | power {d["kick_status_power"]:.0f}',
                debug_color=DebugColor.White,size=130)
        for n,r in own.items():
            role='P1 collect / finish' if n==self.p1 else 'P2 corner / return'
            debug.gui_debug_msg(CGeoPoint(r['pos'][0]-180,r['pos'][1]+250),f'{role} #{n}',
                                debug_color=DebugColor.Orange if n==self.p1 else DebugColor.Cyan,size=140)
        for p,label in ((PASS_POINT,'PASS fixed'),(SHOT_POINT,'SHOT fixed')):
            debug.gui_debug_x(CGeoPoint(*p),debug_color=DebugColor.Green)
            debug.gui_debug_msg(CGeoPoint(min(p[0]-300,2900),p[1]+200),
                                f'{label} ({p[0]}, {p[1]})',debug_color=DebugColor.Green,size=130)
        debug.gui_debug_x(CGeoPoint(*RETURN_AIM_POINT),debug_color=DebugColor.Cyan)
        debug.gui_debug_msg(CGeoPoint(2200,1050),
                            f'RETURN aim ({RETURN_AIM_POINT[0]}, {RETURN_AIM_POINT[1]})',
                            debug_color=DebugColor.Cyan,size=130)

    def log(self,now,cycle,own,ball,velocity):
        interval = .05 if self.phase in ('SETUP','PASS1','RECEIVE1','WAIT_RETURN','PASS2','FINISH') else .25
        if now-self.last_log < interval and self.phase==self.last_logged_phase:
            return
        self.last_log,self.last_logged_phase=now,self.phase
        record=dict(time=time.time(),cycle=cycle,version='combo_2.32_dynamic_roles',mode=self.checkpoint,
                    round_number=self.round_number,restart_ready_seconds=self.restart_elapsed,
                    phase=self.phase,reason=self.reason,ball_valid=self.ball_valid,vision_pause=self.pause,
                    setup_held=self.setup_held,setup_ready_seconds=self.setup_elapsed,
                    first_pass_kick_requested=self.first_pass_kick_requested,
                    first_pass_reacquiring=self.first_pass_reacquiring,
                    pass_point=PASS_POINT,shot_point=SHOT_POINT,corner_slow_distance=1200,corner_slow=self.corner_slow,
                    return_aim_point=RETURN_AIM_POINT,
                    corner_max_acc=None,corner_motion_mode="SimpleGoTo",receive_distance=RECEIVE_DISTANCE,
                    first_aim_since=self.first_aim_since,first_aim_gap=self.first_aim_gap,escape_targets=self.escape_targets,
                    receive_missing_since=self.receive_missing_since,reception=self.reception,
                    receiver_recovery=self.receiver_recovery,return_diagnostic=self.return_diagnostic,
                    shot_skill_started=self.shot_skill_started,
                    finish_attempt_since=self.finish_attempt_since,
                    stationary_shot=self.stationary_shot_diagnostic,
                    return_grace_active=self.return_grace_active,
                    return_ball_age=None if self.last_valid_time is None else now-self.last_valid_time,
                    role_numbers=dict(zip(ROLES,self.attackers)),
                    p1=self.p1,p2=self.p2,robots=own,ball=ball,velocity=velocity,skills=self.labels,
                    requested_power=self.powers,carry=self.carry,peak_speed=self.max_speed,
                    last_shoot_diagnostic=self.shoot_diagnostic)
        with Path('LOG/prelim_combo_blue.jsonl').open('a',encoding='utf-8') as output:
            output.write(json.dumps(record)+'\n')

    def getMatchString(self):
        return '{AB}'

    def transFunction(self):
        return ''


@declare_state_machine(PassCombo)
class PreliminaryPassCombo(StateMachine):
    pass
