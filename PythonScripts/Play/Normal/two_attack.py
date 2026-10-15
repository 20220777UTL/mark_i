"""蓝 0 主攻、蓝 1 接应：传球、换位、回传、主动拦接后预测射门。

解围后持续补射，直到进球、门将解围出界或手动切换 Play。
由 Client / Medusa 启动。所有距离 mm，速度 mm/s。POWER_CAP 尚需球速标定。
"""
import math
from Play.Normal import AttackParams as A
import CppPackage as C
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import Task, State, StateMachine, declare_state_machine
from Vision import Ball, Player, Enemy
from WorldModel import Params, Flags, kickStatus
from WorldModel.PowerCalculator import evalPower, P
from Play.Normal.AttackGeometry import (
    angle_error, direction, distance, intercept, clearance, kick_ball_pos,
    choose_corner_shot, redirect_heading, redirect_possible, touch_intercept, ball_at,
    crossed_goal, static_clearance,
)

mainshoot, assistant = 0, 1
# 兼容现有调用；全部可调值在 AttackParams.py。
POWER_CAP, CARRY_LIMIT = A.POWER_CAP, A.CARRY_LIMIT
MOUTH_OFFSET, CAPTURE_FRAMES = A.MOUTH_OFFSET, A.CAPTURE_FRAMES
SHOT_SPEED, INCOMING_RETAIN = A.SHOT_SPEED, A.INCOMING_RETAIN
PENALTY_FRONT_X = Params.pitchLength / 2 - Params.penaltyDepth
ASSISTANT_POS = CGeoPoint(PENALTY_FRONT_X - A.ASSISTANT_FRONT_CLEARANCE, A.ASSISTANT_SIDE_OFFSET)
# 回传瞄准球的触点，主射手的实际车心还要按接射朝向减去吸球口偏移。
SHOT_CONTACT = (PENALTY_FRONT_X - A.SHOT_CONTACT_CLEARANCE, A.SHOT_SIDE_OFFSET)
MAINSHOOT_POS = CGeoPoint(SHOT_CONTACT[0] - MOUTH_OFFSET, SHOT_CONTACT[1])
RECEIVE_RADIUS = A.RECEIVE_RADIUS


def xy(p):
    return p.x(), p.y()


def point(p):
    return CGeoPoint(*p)


def legal(p, margin=None):
    """保守限制在两侧禁区前沿之间，路径不穿禁区，并核对原生禁区。"""
    margin = Params.playerRadius + A.BOUNDARY_EXTRA if margin is None else margin
    return (abs(p[0]) <= Params.pitchLength / 2 - Params.penaltyDepth - margin
            and abs(p[1]) <= Params.pitchWidth / 2 - margin
            and not C.InTheirPenaltyArea(point(p), margin)
            and not C.InOurPenaltyArea(point(p), margin))


def mouth(number):
    pos, angle = xy(Player.Pos(number)), Player.direction(number)
    return (pos[0] + MOUTH_OFFSET * math.cos(angle),
            pos[1] + MOUTH_OFFSET * math.sin(angle))


def movement_bounds(number):
    # 仅在速度指向的边界一侧预留制动和指令延迟距离，向场内撤回时不会被另一侧误拦。
    vx, vy = xy(Player.vel(number))
    margin = Params.playerRadius + A.BOUNDARY_EXTRA
    bound, width = PENALTY_FRONT_X - margin, Params.pitchWidth / 2 - margin
    def reserve(v):
        return max(0, v) * A.COMMAND_DELAY + max(0, v) ** 2 / (2 * A.BRAKE_ACCEL)
    return -bound + reserve(-vx), bound - reserve(vx), -width + reserve(-vy), width - reserve(vy)


def motion_legal(number, p):
    left, right, bottom, top = movement_bounds(number)
    return left <= p[0] <= right and bottom <= p[1] <= top and legal(p)


def ball_recoverable(p):
    # 收球触点也留出缓冲，防止合法车心前方的球被继续顶进禁区；正常射门不受此限制。
    return (abs(p[0]) <= PENALTY_FRONT_X - A.TOUCH_BALL_CLEARANCE
            and abs(p[1]) <= Params.pitchWidth / 2 - A.BALL_RADIUS - A.BOUNDARY_EXTRA)


def contact_destination(number, destination, facing):
    """接射和降级收球共用近球保护：未对准或接近过快时先停住车心。"""
    robot, ball = xy(Player.Pos(number)), xy(Ball.pos())
    toward_ball = direction(robot, ball)
    vx, vy = xy(Player.vel(number))
    approach_speed = max(0, vx * math.cos(toward_ball) + vy * math.sin(toward_ball))
    brake_distance = approach_speed * A.COMMAND_DELAY + approach_speed ** 2 / (2 * A.BRAKE_ACCEL)
    if distance(robot, ball) <= A.TOUCH_APPROACH_DISTANCE + brake_distance:
        if (angle_error(Player.direction(number), facing) > A.TOUCH_APPROACH_ANGLE
                or approach_speed > A.TOUCH_APPROACH_SPEED):
            return robot
    return destination


def ball_local(number):
    p, b, h = Player.Pos(number), Ball.pos(), Player.direction(number)
    dx, dy = b.x() - p.x(), b.y() - p.y()
    return dx * math.cos(h) + dy * math.sin(h), -dx * math.sin(h) + dy * math.cos(h)


def has_ball(number):
    forward, sideways = ball_local(number)
    # 只有球落在车头狭窄的吸球窗口内才计为连续控球帧。
    return A.CAPTURE_FRONT_MIN <= forward <= A.CAPTURE_FRONT_MAX and abs(sideways) <= A.CAPTURE_SIDE_MAX


def can_kick(number):
    forward, sideways = ball_local(number)
    # 击球窗口比吸球窗口宽，允许准备出球时有少量纵向偏差。
    return A.KICK_FRONT_MIN <= forward <= A.KICK_FRONT_MAX and abs(sideways) <= A.KICK_SIDE_MAX


def ball_relative_speed(number):
    # 转动中的吸球口也有切向速度，不能只比较球和车心的平移速度。
    vx, vy = xy(Player.vel(number))
    h, omega = Player.direction(number), Player.rotVel(number)
    return math.hypot(Ball.vel().x() - vx + omega * MOUTH_OFFSET * math.sin(h),
                      Ball.vel().y() - vy - omega * MOUTH_OFFSET * math.cos(h))


def keeper():
    # 无有效门将观测时返回 None，调用方据此跳过门将避让几何检测。
    return (xy(Enemy.pos(0)), xy(Enemy.vel(0))) if Enemy.valid(0) else (None, (0, 0))


def halt(number):
    C.setDribbleCommand(number, 0)
    kickStatus.setBothKick(number, 0, 0)
    C.makeItStop(number)


def stop(number):
    return Task((halt, lambda n: Player.Pos(n)), fixedNumber=number)


class Control:
    """跨状态保存控球、收球阶段和目标；不依赖红外。"""
    def __init__(self):
        self.carry = {mainshoot: 0, assistant: 0}
        self.previous = {}
        self.cap = POWER_CAP
        self.last_power = 0
        self.shot_target = None
        self.capture_frames = {mainshoot: 0, assistant: 0}
        self.held = {mainshoot: False, assistant: False}
        self.return_contact = None
        self.shot_locked = False
        self.receive_near = {mainshoot: False, assistant: False}
        self.outcome = None
        self.ball_available = False
        self.ball_in_field = True
        self.previous_ball = None
        self.previous_velocity = None
        self.previous_keeper = None
        self.keeper_cleared = False
        self.shot_origin = None
        self.shot_departed = False
        self.rebound_ready = False
        self.direct_rebound = False

    def observe_ball(self):
        """每帧追踪真实结果；丢球观测不当作进球/出界，也不跨丢帧插值。"""
        self.ball_available = Ball.valid()
        if self.ball_available:
            ball, velocity = xy(Ball.pos()), xy(Ball.vel())
            self.ball_available = all(math.isfinite(v) for v in (*ball, *velocity))
        if not self.ball_available:
            self.previous_ball = self.previous_velocity = self.previous_keeper = None
            return False

        goal_x, half_width = Params.pitchLength / 2, Params.pitchWidth / 2
        self.ball_in_field = (abs(ball[0]) <= goal_x + A.BALL_RADIUS
                              and abs(ball[1]) <= half_width + A.BALL_RADIUS)
        keeper_pos, _ = keeper()
        if keeper_pos is not None and not all(math.isfinite(v) for v in keeper_pos):
            keeper_pos = None
        if self.previous_ball is not None:
            # 用球段到门将的距离捕捉两帧之间的碰撞；还需速度突变，不能只因球路经过门将。
            def near_keeper(p):
                # static_clearance 对退化球段返回负无穷；静止球须改用真实点距，避免误记远处门将触球。
                if distance(self.previous_ball, ball) < 1:
                    return distance(ball, p) <= Params.playerRadius + A.BALL_RADIUS + A.KEEPER_CONTACT_MARGIN
                return static_clearance(self.previous_ball, ball, p, Params.playerRadius) <= A.KEEPER_CONTACT_MARGIN
            nearby = any(near_keeper(p) for p in (self.previous_keeper, keeper_pos) if p is not None)
            changed = distance(velocity, self.previous_velocity) >= A.KEEPER_VELOCITY_CHANGE
            if nearby and changed:
                self.keeper_cleared = True
            # 必须先判进球，再判出界，否则穿过球门的球会被误记成底线出界。
            if self.outcome is None and crossed_goal(self.previous_ball, ball, goal_x, Params.goalWidth):
                self.outcome = 'goal'

        # 我方重新触球后，不能再把后续我方传球/射偏出界归因于上一次门将解围。
        if any(has_ball(n) for n in (mainshoot, assistant)):
            self.keeper_cleared = False
        if self.outcome is None and not self.ball_in_field and self.keeper_cleared:
            self.outcome = 'keeper_clearance_out'

        if self.shot_origin is not None and not self.outcome:
            # 不要求仍向前飞：近距离被挡回的球也可能已离脚，不能卡在旧射门的释放检测中。
            if not can_kick(mainshoot) and distance(self.shot_origin, ball) > A.TOUCH_TOLERANCE:
                self.shot_departed = True
            if self.shot_departed:
                vx, vy = velocity
                speed = math.hypot(vx, vy)
                projected_y = ball[1] + (goal_x - ball[0]) * vy / vx if vx > 0 else float('inf')
                # 球仍朝门内飞就观察；回弹、停下或偏离门框后立即组织下一次进攻。
                if (vx < -A.REBOUND_MOVING_SPEED or speed <= A.REBOUND_MOVING_SPEED
                        or abs(projected_y) > Params.goalWidth / 2 - A.BALL_RADIUS):
                    self.rebound_ready = True

        self.previous_ball, self.previous_velocity, self.previous_keeper = ball, velocity, keeper_pos
        return True

    def start_shot(self, ball):
        self.shot_origin = ball
        self.shot_departed = self.rebound_ready = self.direct_rebound = False
        self.keeper_cleared = False

    def start_rebound(self):
        # 每次补射都重选门角、重新规划触点；保留带球里程和解围来源，避免绕过保护。
        self.shot_origin = None
        self.shot_departed = self.rebound_ready = False
        self.shot_locked = False
        self.shot_target = self.return_contact = None
        self.receive_near = {mainshoot: False, assistant: False}
        self.direct_rebound = not rebound_needs_pass()
        return 'InterceptAndShoot' if self.direct_rebound else 'ReceiveAndReturn'

    def update(self):
        # 只附加结果追踪；原有持球确认、带球里程和力度逻辑保持原样。
        self.observe_ball()
        for n in self.carry:
            # 连续满足吸球几何条件若干帧后才确认持球，抑制单帧视觉抖动。
            self.capture_frames[n] = min(CAPTURE_FRAMES, self.capture_frames[n] + 1) if has_ball(n) else 0
            forward, sideways = ball_local(n)
            # 低相对速度、连续两帧在吸球窗口内可提前确认；擦碰/高速来球沿用三帧检测。
            settled = (self.capture_frames[n] >= A.FAST_CAPTURE_FRAMES
                       and ball_relative_speed(n) <= A.CAPTURE_STABLE_SPEED)
            if self.capture_frames[n] >= CAPTURE_FRAMES or settled:
                self.held[n] = True
            # 球已跑到车后、离车过远或偏角过大时立即撤销持球状态。
            elif forward <= 0 or math.hypot(forward, sideways) > A.HELD_DISTANCE_MAX or abs(math.atan2(sideways, forward)) > A.HELD_ANGLE_MAX:
                self.held[n] = False
            pos = xy(Player.Pos(n))
            # 球远离时清空本轮带球里程；持球期间累计机器人实际位移用于限制连续带球。
            if distance(pos, xy(Ball.pos())) > A.CARRY_RESET_DISTANCE:
                self.carry[n] = 0
            elif self.held[n] and n in self.previous:
                self.carry[n] += distance(pos, self.previous[n])
            self.previous[n] = pos
        speed = Ball.velMod()
        # 超速时按最近一次出球功率下调上限；此保护仅在配置开关开启时生效。
        if A.ENFORCE_BALL_SPEED and speed > A.BALL_SPEED_LIMIT and self.last_power:
            self.cap = min(self.cap, self.last_power * A.POWER_REDUCTION)
            self.last_power = 0
            print(f'TWO_ATTACK: ball speed {speed/1000:.2f} m/s exceeds limit; power cap -> {self.cap:.0f}', flush=True)

    def allowed(self, n):
        # 任务继续前同时检查带球里程、含刹车距离的场地边界和禁区合法性。
        return self.carry[n] < CARRY_LIMIT and motion_legal(n, xy(Player.Pos(n)))


def move_to(number, target, control, angle=None, velocity=None, fetching=False, flags=None, max_acc=None):
    flags = Flags.allow_dss if flags is None else flags
    destination = xy(target)
    left, right, bottom, top = movement_bounds(number)
    # 先裁剪目标以给机器人留出制动空间，再对裁剪后的点做边界/禁区校验。
    destination = (max(left, min(right, destination[0])),
                   max(bottom, min(top, destination[1])))
    # 目标仍非法或机器人已触发场地/带球限制时直接停车，不执行越界移动。
    if not legal(destination) or not control.allowed(number):
        return stop(number)
    angle = Player.toBallDir(number) if angle is None else angle
    target = point(destination)
    def execute(n):
        C.setDribbleCommand(n, A.DRIBBLE_COMMAND)
        # 只为当前取球者注册，普通跑位不争用 fetchBall 角色。
        if fetching:
            C.TaskMediator.Instance().registerRole(n, "fetchBall")
        C.makeItRushTo(n, target, angle, flag=flags,
                       maxAcc=A.RUSH_MAX_ACC if max_acc is None else max_acc, needDribble=True,
                       vel=C.CVector(*(velocity or (0, 0))))
    return Task((execute, lambda n: target), fixedNumber=number)


def receive(number, control, *, press=True):
    """远处预测拦截，近处先对球再小幅收球；全程 RushTo。"""
    robot, ball = xy(Player.Pos(number)), xy(Ball.pos())
    if not control.allowed(number):
        return stop(number)
    # 已确认持球时保持原地和当前朝向，避免接球任务继续追逐球导致推球。
    if control.held[number]:
        return move_to(number, Player.Pos(number), control, Player.direction(number),
                       max_acc=None if press else A.TOUCH_MAX_ACC)
    # 进入和退出近球模式使用不同距离阈值，形成滞回，减少模式频繁切换。
    threshold = A.RECEIVE_NEAR_EXIT if control.receive_near[number] else A.RECEIVE_NEAR_ENTER
    control.receive_near[number] = (distance(robot, ball) <= threshold
                                    and Ball.velMod() <= A.RECEIVE_MOVING_SPEED
                                    and ball_recoverable(ball))
    velocity = None
    if control.receive_near[number]:
        angle = direction(robot, ball)
        destination = robot
        # 只有车头已基本对准球时才前压；否则先原地转向，避免侧面碰球。
        if angle_error(Player.direction(number), angle) <= A.RECEIVE_ALIGN_ANGLE:
            # 正面来球仍在靠近时留在接触距离；静止/远离时才小幅前压。
            closing = (Ball.vel().x() * math.cos(angle) + Ball.vel().y() * math.sin(angle)
                       < -A.RECEIVE_INCOMING_SPEED)
            offset = MOUTH_OFFSET if closing or not press else MOUTH_OFFSET - A.RECEIVE_PRESS
            if not closing and press:
                velocity = (A.RECEIVE_PRESS_SPEED * math.cos(angle),
                            A.RECEIVE_PRESS_SPEED * math.sin(angle))
            destination = (ball[0] - offset * math.cos(angle), ball[1] - offset * math.sin(angle))
    else:
        destination, angle = intercept(ball, xy(Ball.vel()), robot, xy(Player.vel(number)),
                                       lambda p: motion_legal(number, p), MOUTH_OFFSET,
                                       with_heading=True, robot_heading=Player.direction(number),
                                       contact_legal=ball_recoverable)
    flags = 0 if control.receive_near[number] else Flags.allow_dss
    if not press:
        # 降级收球也必须减速/先转向，不能绕过接射时的防顶球保护。
        destination = contact_destination(number, destination, angle)
        if distance(robot, ball) > A.TOUCH_APPROACH_DISTANCE:
            flags |= Flags.dodge_ball
    return move_to(number, point(destination), control, angle, velocity, fetching=True,
                   flags=flags, max_acc=None if press else A.TOUCH_MAX_ACC)


def lane_clear(target):
    pos, velocity = keeper()
    # 门将无效时不阻挡通道；有效时要求所有候选球速下的最小净空仍为正。
    return pos is None or min(clearance(xy(Ball.pos()), xy(target), pos, velocity, A.LANE_DELAY, s,
                                       Params.playerRadius) for s in A.LANE_SPEEDS) > 0


def kick_to(number, target, state, level=P.HIGH, shooting=False, allow_kick=True):
    """拿到球才转向；按预计出球方向判断，不等固定转速阈值。"""
    if not state.control.allowed(number):
        return stop(number)
    # 尚未持球时先执行接球；球已离开且未重新控住时停止，防止重复触发同一次射门。
    if not state.control.held[number] and state.fired is None:
        return receive(number, state.control)
    if state.fired is not None and not state.control.held[number]:
        return stop(number)
    ball = xy(Ball.pos())
    desired = direction(ball, xy(target))
    def execute(n):
        kickStatus.setBothKick(n, 0, 0)
        C.setDribbleCommand(n, A.DRIBBLE_COMMAND)
        centre = Player.Pos(n)
        # 转向结束后补齐球在车头的偏移，避免带着侧向滞后的球空踢。
        if angle_error(Player.direction(n), desired) < A.KICK_PREP_ANGLE:
            offset = MOUTH_OFFSET if can_kick(n) else MOUTH_OFFSET - A.RECEIVE_PRESS
            _, aligned = kick_ball_pos(ball, xy(target), offset)
            if legal(aligned):
                centre = point(aligned)
        C.makeItSimpleGoTo(n, centre, desired, 0)
        predicted = Player.direction(n) + Player.rotVel(n) * A.COMMAND_DELAY
        # 出球条件同时要求控稳、球在击球窗口内且短时预测朝向已对齐。
        ready = allow_kick and state.control.held[n] and can_kick(n) and angle_error(predicted, desired) < A.KICK_ANGLE
        if shooting and ready:
            # 实际预计射线也必须落在门柱内，并避开运动门将。
            dx = Params.pitchLength / 2 - Ball.posX()
            # 射线必须朝向对方球门，再检查预测交点是否在两门柱内且射门通道无遮挡。
            if math.cos(predicted) <= 0:
                ready = False
            else:
                y = Ball.posY() + dx * math.tan(predicted)
                ready = abs(y) < Params.goalWidth / 2 - A.GOAL_RAY_MARGIN and lane_clear(CGeoPoint(Params.pitchLength / 2, y))
        elif ready:
            ready = lane_clear(target)
        if ready:
            power = evalPower(Ball.pos(), target, level)
            if A.ENFORCE_BALL_SPEED:
                power = min(state.control.cap, power)
            if power > 0 and math.isfinite(power):
                # 只记录有效正功率；首次触发时保存球位置供后续“球已释放”检测使用。
                kickStatus.setKick(n, power)
                state.control.last_power = power
                state.control.keeper_cleared = False
                if state.fired is None:
                    state.fired = xy(Ball.pos())
    return Task((execute, lambda n: Ball.pos()), fixedNumber=number)


class AttackState(State):
    def __init__(self):
        super().__init__()
        self.reset_attempt()

    def reset_attempt(self):
        # 状态实例会复用；再次进入时必须清掉上一脚的 fired/target，才能继续传射。
        self.fired = self.target = None
        self.incoming_seen = False

    def run(self, isStateSwitched):
        # 只附加终止检测；结束当帧先停车，原有任务执行与状态切换顺序保持不变。
        if self.control.outcome:
            halt(mainshoot)
            halt(assistant)
            return 'Done'
        return super().run(isStateSwitched)

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''

    def released(self, number):
        if self.fired is None:
            return False
        ball = xy(Ball.pos())
        travel, separation = distance(self.fired, ball), Player.Pos(number).dist(Ball.pos())
        # 慢球保留原距离确认；正常快速传球离开击球口且方向、速度一致时尽早开始换位。
        if travel > A.RELEASE_TRAVEL and separation > A.RELEASE_DISTANCE:
            return True
        target = xy(self.target) if self.target is not None else self.control.shot_target
        if target is None or travel <= A.RELEASE_FAST_TRAVEL or separation <= A.RELEASE_FAST_DISTANCE:
            return False
        intended = direction(self.fired, target)
        return (angle_error(direction(self.fired, ball), intended) < A.RELEASE_FAST_ANGLE
                and angle_error(direction((0, 0), xy(Ball.vel())), intended) < A.RELEASE_FAST_ANGLE
                and Ball.velMod() >= A.RELEASE_FAST_SPEED)


class GetFirstBall(AttackState):
    def getTasks(self):
        # 控球后即可预转向接应点，与接应者跑位并行；到位条件满足前不出球。
        return {'A': kick_to(mainshoot, ASSISTANT_POS, self, allow_kick=False),
                'B': move_to(assistant, ASSISTANT_POS, self.control)}

    def transFunction(self):
        # 主攻手确认控球、接应者到位且传球通道畅通后才启动传球状态。
        if self.control.held[mainshoot] and Player.Pos(assistant).dist(ASSISTANT_POS) < RECEIVE_RADIUS and lane_clear(point(mouth(assistant))):
            return 'PassToAssistant'
        return ''


class PassToAssistant(AttackState):
    def getTasks(self):
        if self.released(mainshoot):
            # 状态切换在任务执行后发生，这一帧先启动换位和接球，不额外空等一帧。
            centre, angle = prepare_return(self.control)
            return {'A': move_to(mainshoot, point(centre), self.control, angle, flags=Flags.allow_dss | Flags.dodge_ball),
                    'B': receive(assistant, self.control)}
        if self.fired is None:
            # 出脚前跟随接应车的实际吸球口，避免锁定过早留下转向/位置误差。
            self.target = point(mouth(assistant))
        return {'A': kick_to(mainshoot, self.target, self),
                'B': move_to(assistant, Player.Pos(assistant), self.control)}

    def transFunction(self):
        # 球确实离开主攻手并拉开距离后，才认为传球完成并开始接应回传。
        return 'ReceiveAndReturn' if self.released(mainshoot) else ''


class ReceiveAndReturn(AttackState):
    def getTasks(self):
        centre, angle = prepare_return(self.control)
        # 接应者拿稳球后立即预转向回传点；与主射手的跑位/对准同时进行。
        return {'A': move_to(mainshoot, point(centre), self.control, angle, flags=Flags.allow_dss | Flags.dodge_ball),
                'B': kick_to(assistant, point(self.control.return_contact), self, allow_kick=False)}

    def transFunction(self):
        if self.control.held[assistant] and return_ready(self.control):
            return 'PassBack'
        return ''


class PassBack(AttackState):
    def getTasks(self):
        centre, angle = prepare_return(self.control)
        if self.target is None:
            self.target = point(self.control.return_contact)
        return {'A': move_to(mainshoot, point(centre), self.control, angle, flags=Flags.allow_dss | Flags.dodge_ball),
                'B': kick_to(assistant, self.target, self, allow_kick=return_ready(self.control), level=P.NORMAL)}

    def transFunction(self):
        # 接应者完成回传后，主攻手切换为预判拦截和射门。
        return 'InterceptAndShoot' if self.released(assistant) else ''


def select_touch_target(control, contact):
    # 实际出脚后才固定目标；出脚前持续依据实测门将位置选择开放角度更大的门角。
    if control.shot_locked:
        return
    goal_x = Params.pitchLength / 2
    keeper_pos = xy(Enemy.pos(0)) if Enemy.valid(0) else None
    control.shot_target = choose_corner_shot(
        contact, goal_x, Params.goalWidth, keeper_pos, control.shot_target)


def prepare_return(control):
    # 回传触球点只初始化一次，后续用估计来球速度计算能把球导向门内的车头角度。
    if control.return_contact is None:
        control.return_contact = SHOT_CONTACT
    contact = control.return_contact
    select_touch_target(control, contact)
    pass_dir = direction(xy(Ball.pos()), contact)
    incoming = (A.RETURN_SPEED_ESTIMATE * math.cos(pass_dir), A.RETURN_SPEED_ESTIMATE * math.sin(pass_dir))
    angle = redirect_heading(contact, control.shot_target, incoming, SHOT_SPEED, INCOMING_RETAIN)
    return (contact[0] - MOUTH_OFFSET * math.cos(angle), contact[1] - MOUTH_OFFSET * math.sin(angle)), angle


def return_ready(control):
    centre, angle = prepare_return(control)
    # 回传出脚前仍需检查主射手的位置、朝向和通道，预转向不意味着提前传球。
    return (control.allowed(mainshoot) and ball_recoverable(control.return_contact)
            and motion_legal(mainshoot, centre)
            and distance(xy(Player.Pos(mainshoot)), centre) < A.RETURN_READY_DISTANCE
            and angle_error(Player.direction(mainshoot), angle) < A.RETURN_READY_ANGLE
            and lane_clear(point(control.return_contact)))


def touch_motion(state, centre, angle):
    """将检查过的车心坐标直接下发；接近球时先刹车和对准，出脚后不再追球。"""
    control = state.control
    def execute(n):
        if not control.allowed(n):
            halt(n)
            return
        robot, ball, velocity = xy(Player.Pos(n)), xy(Ball.pos()), xy(Ball.vel())
        kick_ready = can_kick(n)
        # 球进入击球窗口时，以当前球位和最新门将位置重新选角，避免沿用接球途中的目标。
        if kick_ready:
            select_touch_target(control, ball)
        desired = redirect_heading(ball, control.shot_target, velocity, SHOT_SPEED, INCOMING_RETAIN)
        feasible = redirect_possible(ball, control.shot_target, velocity, SHOT_SPEED, INCOMING_RETAIN)
        destination, facing = contact_destination(n, centre, angle), angle
        gap = distance(robot, ball)
        if kick_ready:
            # 已到击球口就保持车心；不能为瞄准再往前压球。无法补偿的快球先吸住再射。
            destination = robot
            facing = desired if feasible else Player.direction(n)
        if not motion_legal(n, destination):
            halt(n)
            return
        flags = Flags.allow_dss
        if gap > A.TOUCH_APPROACH_DISTANCE:
            flags |= Flags.dodge_ball  # 远处换位绕球，避免车身横穿来球路径。
        C.setDribbleCommand(n, A.DRIBBLE_COMMAND)
        C.TaskMediator.Instance().registerRole(n, 'fetchBall')
        # 明确使用安全拦截点和零末速度；仅传朝向的 GetBallV5 无法遵守这里的位置约束。
        C.makeItRushTo(n, point(destination), facing, flag=flags,
                       maxAcc=A.TOUCH_MAX_ACC, needDribble=True, vel=C.CVector(0, 0))
        kickStatus.setBothKick(n, 0, 0)
        # 使用当前可击打范围；不等待 held、停球或门将让出球路。
        h = Player.direction(n) + Player.rotVel(n) * A.COMMAND_DELAY
        out_x = SHOT_SPEED * math.cos(h) + INCOMING_RETAIN * velocity[0]
        out_y = SHOT_SPEED * math.sin(h) + INCOMING_RETAIN * velocity[1]
        goal_y = ball[1] + (Params.pitchLength / 2 - ball[0]) * out_y / out_x if out_x > 0 else float('inf')
        # 只有球在击球窗口内、预计触球朝向正确且合成出球射线命中门内，才允许触球射门。
        if kick_ready and feasible and angle_error(h, desired) < A.TOUCH_ANGLE and abs(goal_y) < Params.goalWidth / 2 - A.GOAL_RAY_MARGIN:
            power = min(control.cap, evalPower(Ball.pos(), point(control.shot_target), P.HIGH))
            if math.isfinite(power) and power > 0:
                kickStatus.setKick(n, power)
                control.last_power = power
                control.shot_locked = True
                if state.fired is None:
                    state.fired = xy(Ball.pos())
                    control.start_shot(state.fired)
    return Task((execute, lambda n: Ball.pos()), fixedNumber=mainshoot)


def touch_shot(state):
    control = state.control
    if not control.allowed(mainshoot) or state.released(mainshoot):
        return stop(mainshoot)
    # 已下发射门且球已离开击球口时只等待释放确认，不能把射出的球再次当作拦截目标。
    if state.fired is not None and not can_kick(mainshoot):
        return stop(mainshoot)
    ball, velocity = xy(Ball.pos()), xy(Ball.vel())
    robot = xy(Player.Pos(mainshoot))
    select_touch_target(control, ball)
    if can_kick(mainshoot):
        # 已可直接击球时跳过离散预测，当前帧即可瞄准出脚。
        return touch_motion(state, robot, Player.direction(mainshoot))

    future = ball_at(ball, velocity, A.PREDICT_STEP * A.PREDICT_STEPS)
    if not ball_recoverable(ball) and not ball_recoverable(future):
        # 球已进入不可追的区域时退回合法接应位；每帧重评，球滚出后自动恢复接球。
        centre, _ = prepare_return(control)
        return move_to(mainshoot, point(centre), control, Player.toBallDir(mainshoot),
                       flags=Flags.allow_dss | Flags.dodge_ball, max_acc=A.TOUCH_MAX_ACC)

    args = (ball, velocity, robot, xy(Player.vel(mainshoot)), Player.direction(mainshoot))
    target = control.shot_target
    plan = touch_intercept(*args, target, lambda p: motion_legal(mainshoot, p),
                           MOUTH_OFFSET, SHOT_SPEED, INCOMING_RETAIN, contact_legal=ball_recoverable)
    if plan is not None:
        select_touch_target(control, plan[0])
        # 仅在目标换边时重新计算，避免每帧无条件重复整段预测。
        if control.shot_target != target:
            plan = touch_intercept(*args, control.shot_target, lambda p: motion_legal(mainshoot, p),
                                   MOUTH_OFFSET, SHOT_SPEED, INCOMING_RETAIN, contact_legal=ball_recoverable)
    if plan is None:
        # 来不及转向/刹停或来球太快时正面收球，接近时不前压；收稳后仍可在此状态射门。
        return receive(mainshoot, control, press=False)
    _, centre, _, angle = plan
    return touch_motion(state, centre, angle)


class InterceptAndShoot(AttackState):
    def getTasks(self):
        if self.control.direct_rebound and self.fired is None and rebound_needs_pass():
            # 解围球继续远离球门时改走一脚回传，同一帧开始回收和主射手跑位。
            return ReceiveAndReturn.getTasks(self)
        return {'A': touch_shot(self), 'B': stop(assistant)}

    def released(self, number):
        # 拦截射门还要求球向前越过速度门槛，排除横向碰球或接触抖动造成的假释放。
        return super().released(number) and Ball.vel().x() > A.SHOT_RELEASE_VX

    def transFunction(self):
        if self.control.direct_rebound and self.fired is None and rebound_needs_pass():
            self.control.direct_rebound = False
            return 'ReceiveAndReturn'
        # 出脚/离脚仅进入观察，不能当作进球或本轮结束；被快速挡回时同样进入观察。
        if self.control.shot_departed or self.released(mainshoot):
            return 'FollowShot'
        return ''


def rebound_needs_pass():
    """按球到门中心的距离分流，兼顾解围球短时继续远离球门的趋势。"""
    ball = xy(Ball.pos())
    future = ball_at(ball, xy(Ball.vel()), A.REBOUND_LOOKAHEAD)
    goal = (Params.pitchLength / 2, 0)
    return max(distance(ball, goal), distance(future, goal)) > A.REBOUND_SHOT_DISTANCE


class FollowShot(AttackState):
    def getTasks(self):
        # 射门仍在飞行时不追入禁区；没有补射次数或等待时长上限。
        return {'A': stop(mainshoot), 'B': stop(assistant)}

    def transFunction(self):
        if self.control.ball_available and self.control.ball_in_field and self.control.rebound_ready:
            # 远球复用 ReceiveAndReturn -> PassBack -> InterceptAndShoot，只补一脚传球。
            return self.control.start_rebound()
        return ''


class Done(AttackState):
    def getTasks(self):
        return {'A': stop(mainshoot), 'B': stop(assistant)}


@declare_state_machine(GetFirstBall, PassToAssistant, ReceiveAndReturn, PassBack,
                       InterceptAndShoot, FollowShot, Done)
class two_attack(StateMachine):
    def __init__(self):
        super().__init__()
        self.control = Control()
        self.last_state = None

    def hookBeforePlanTasks(self):
        import Global
        # Play 切换时清空上一轮的控球计数、目标和出球标记，避免跨回合沿用旧状态。
        if Global.isPlaySwitched:
            self.control = Control()
            for state in self.states.values():
                state.reset_attempt()
            self.last_state = None
        self.control.update()
        for state in self.states.values():
            state.control = self.control
        # 框架稍后才恢复 start_state；这里同步选择它，避免重开时重置错状态。
        active = self.start_state if Global.isPlaySwitched else self.current_state
        name = active.state_name
        # 仅在状态变化时打印，避免每个控制周期重复输出相同状态。
        if name != self.last_state:
            active.reset_attempt()
            print('TWO_ATTACK:', name, flush=True)
            self.last_state = name
