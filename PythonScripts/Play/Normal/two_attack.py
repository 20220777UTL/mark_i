"""蓝 0 主攻、蓝 1 接应：传球、换位、回传、主动拦接后预测射门。

由 Client / Medusa 启动。所有距离 mm，速度 mm/s。POWER_CAP 尚需球速标定。
"""
import math
from Play.Normal import AttackParams as A
import CppPackage as C
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import Task, State, StateMachine, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Player, Enemy
from WorldModel import Params, Flags, kickStatus
from WorldModel.PowerCalculator import evalPower, P
from Play.Normal.AttackGeometry import (
    angle_error, direction, distance, intercept, clearance, kick_ball_pos,
    choose_corner_shot, redirect_heading, touch_intercept,
)

mainshoot, assistant = 0, 1
# 兼容现有调用；全部可调值在 AttackParams.py。
POWER_CAP, CARRY_LIMIT = A.POWER_CAP, A.CARRY_LIMIT
MOUTH_OFFSET, CAPTURE_FRAMES = A.MOUTH_OFFSET, A.CAPTURE_FRAMES
SHOT_SPEED, INCOMING_RETAIN = A.SHOT_SPEED, A.INCOMING_RETAIN
FRONT_X = Params.pitchLength / 2 - Params.penaltyDepth - A.FRONT_CLEARANCE
ASSISTANT_POS = CGeoPoint(FRONT_X, A.SIDE_OFFSET)
MAINSHOOT_POS = CGeoPoint(FRONT_X, -A.SIDE_OFFSET)
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
    # 分轴留刹车距离，横向跑位不会无故缩小纵向活动范围。
    vx, vy = xy(Player.vel(number))
    margin = Params.playerRadius + A.BOUNDARY_EXTRA
    return (Params.pitchLength / 2 - Params.penaltyDepth - margin - vx * vx / (2 * A.BRAKE_ACCEL),
            Params.pitchWidth / 2 - margin - vy * vy / (2 * A.BRAKE_ACCEL))


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


def keeper():
    # 无有效门将观测时返回 None，调用方据此跳过门将避让几何检测。
    return (xy(Enemy.pos(0)), xy(Enemy.vel(0))) if Enemy.valid(0) else (None, (0, 0))


def stop(number):
    def execute(n):
        C.setDribbleCommand(n, 0)
        kickStatus.setBothKick(n, 0, 0)
        C.makeItStop(n)
    return Task((execute, lambda n: Player.Pos(n)), fixedNumber=number)


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

    def update(self):
        for n in self.carry:
            # 连续满足吸球几何条件若干帧后才确认持球，抑制单帧视觉抖动。
            self.capture_frames[n] = min(CAPTURE_FRAMES, self.capture_frames[n] + 1) if has_ball(n) else 0
            forward, sideways = ball_local(n)
            if self.capture_frames[n] >= CAPTURE_FRAMES:
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
        x, y = xy(Player.Pos(n))
        bound, width = movement_bounds(n)
        # 任务继续前同时检查带球里程、含刹车距离的场地边界和禁区合法性。
        return (self.carry[n] < CARRY_LIMIT and abs(x) <= bound
                and abs(y) <= width and legal((x, y)))


def move_to(number, target, control, angle=None, velocity=None, fetching=False, flags=None):
    flags = Flags.allow_dss if flags is None else flags
    destination = xy(target)
    bound, width = movement_bounds(number)
    # 先裁剪目标以给机器人留出制动空间，再对裁剪后的点做边界/禁区校验。
    destination = (max(-bound, min(bound, destination[0])),
                   max(-width, min(width, destination[1])))
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
                       maxAcc=A.RUSH_MAX_ACC, needDribble=True,
                       vel=C.CVector(*(velocity or (0, 0))))
    return Task((execute, lambda n: target), fixedNumber=number)


def receive(number, control):
    """远处预测拦截，近处先对球再小幅收球；全程 RushTo。"""
    robot, ball = xy(Player.Pos(number)), xy(Ball.pos())
    if not control.allowed(number):
        return stop(number)
    # 已确认持球时保持原地和当前朝向，避免接球任务继续追逐球导致推球。
    if control.held[number]:
        return move_to(number, Player.Pos(number), control, Player.direction(number))
    # 进入和退出近球模式使用不同距离阈值，形成滞回，减少模式频繁切换。
    threshold = A.RECEIVE_NEAR_EXIT if control.receive_near[number] else A.RECEIVE_NEAR_ENTER
    control.receive_near[number] = (distance(robot, ball) <= threshold
                                    and Ball.velMod() <= A.RECEIVE_MOVING_SPEED)
    velocity = None
    if control.receive_near[number]:
        angle = direction(robot, ball)
        destination = robot
        # 只有车头已基本对准球时才前压；否则先原地转向，避免侧面碰球。
        if angle_error(Player.direction(number), angle) <= A.RECEIVE_ALIGN_ANGLE:
            # 正面来球仍在靠近时留在接触距离；静止/远离时才小幅前压。
            closing = (Ball.vel().x() * math.cos(angle) + Ball.vel().y() * math.sin(angle)
                       < -A.RECEIVE_INCOMING_SPEED)
            offset = MOUTH_OFFSET if closing else MOUTH_OFFSET - A.RECEIVE_PRESS
            if not closing:
                velocity = (A.RECEIVE_PRESS_SPEED * math.cos(angle),
                            A.RECEIVE_PRESS_SPEED * math.sin(angle))
            destination = (ball[0] - offset * math.cos(angle), ball[1] - offset * math.sin(angle))
    else:
        destination, angle = intercept(ball, xy(Ball.vel()), robot, xy(Player.vel(number)),
                                       legal, MOUTH_OFFSET, with_heading=True, robot_heading=Player.direction(number))
    return move_to(number, point(destination), control, angle, velocity, fetching=True,
                   flags=0 if control.receive_near[number] else Flags.allow_dss)


def lane_clear(target):
    pos, velocity = keeper()
    # 门将无效时不阻挡通道；有效时要求所有候选球速下的最小净空仍为正。
    return pos is None or min(clearance(xy(Ball.pos()), xy(target), pos, velocity, A.LANE_DELAY, s,
                                       Params.playerRadius) for s in A.LANE_SPEEDS) > 0


def kick_to(number, target, state, level=P.HIGH, shooting=False):
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
        ready = state.control.held[n] and can_kick(n) and angle_error(predicted, desired) < A.KICK_ANGLE
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
                if state.fired is None:
                    state.fired = xy(Ball.pos())
    return Task((execute, lambda n: Ball.pos()), fixedNumber=number)


class AttackState(State):
    def __init__(self):
        super().__init__()
        self.fired = None
        self.target = None
        self.incoming_seen = False

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''

    def released(self, number):
        # 既要球相对出球点移动足够远，也要与机器人拉开距离，才算完成释放。
        return (self.fired is not None and distance(self.fired, xy(Ball.pos())) > A.RELEASE_TRAVEL
                and Player.Pos(number).dist(Ball.pos()) > A.RELEASE_DISTANCE)


class GetFirstBall(AttackState):
    def getTasks(self):
        return {'A': receive(mainshoot, self.control), 'B': move_to(assistant, ASSISTANT_POS, self.control)}

    def transFunction(self):
        # 主攻手确认控球、接应者到位且传球通道畅通后才启动传球状态。
        if self.control.held[mainshoot] and Player.Pos(assistant).dist(ASSISTANT_POS) < RECEIVE_RADIUS and lane_clear(point(mouth(assistant))):
            return 'PassToAssistant'
        return ''


class PassToAssistant(AttackState):
    def getTasks(self):
        if self.target is None:
            self.target = point(mouth(assistant))
        return {'A': kick_to(mainshoot, self.target, self),
                'B': move_to(assistant, Player.Pos(assistant), self.control)}

    def transFunction(self):
        # 球确实离开主攻手并拉开距离后，才认为传球完成并开始接应回传。
        return 'ReceiveAndReturn' if self.released(mainshoot) else ''


class ReceiveAndReturn(AttackState):
    def getTasks(self):
        centre, angle = prepare_return(self.control)
        return {'A': move_to(mainshoot, point(centre), self.control, angle), 'B': receive(assistant, self.control)}

    def transFunction(self):
        centre, angle = prepare_return(self.control)
        # 接应车控稳后，主攻手还需到达预备点、对准回传方向且回传通道畅通。
        if (self.control.held[assistant] and distance(xy(Player.Pos(mainshoot)), centre) < A.RETURN_READY_DISTANCE
                and angle_error(Player.direction(mainshoot), angle) < A.RETURN_READY_ANGLE
                and lane_clear(point(self.control.return_contact))):
            return 'PassBack'
        return ''


class PassBack(AttackState):
    def getTasks(self):
        centre, angle = prepare_return(self.control)
        if self.target is None:
            self.target = point(self.control.return_contact)
        return {'A': move_to(mainshoot, point(centre), self.control, angle),
                'B': kick_to(assistant, self.target, self)}

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
        control.return_contact = (MAINSHOOT_POS.x() + MOUTH_OFFSET, MAINSHOOT_POS.y())
    contact = control.return_contact
    select_touch_target(control, contact)
    pass_dir = direction(xy(Ball.pos()), contact)
    incoming = (A.RETURN_SPEED_ESTIMATE * math.cos(pass_dir), A.RETURN_SPEED_ESTIMATE * math.sin(pass_dir))
    angle = redirect_heading(contact, control.shot_target, incoming, SHOT_SPEED, INCOMING_RETAIN)
    return (contact[0] - MOUTH_OFFSET * math.cos(angle), contact[1] - MOUTH_OFFSET * math.sin(angle)), angle


def touch_shot(state):
    control = state.control
    # 不满足控球/边界约束或射门已释放时不再继续拦截，避免多次下发击球。
    if not control.allowed(mainshoot) or state.released(mainshoot):
        return stop(mainshoot)
    if Ball.velMod() > A.INCOMING_SPEED_MIN:
        state.incoming_seen = True
    # 尚未观察到明显来球且球仍较远时，先去预备触球位；否则开始预测拦截。
    if not state.incoming_seen and Player.Pos(mainshoot).dist(Ball.pos()) > A.TOUCH_WAIT_DISTANCE:
        centre, angle = prepare_return(control)
        return move_to(mainshoot, point(centre), control, angle)
    target = control.shot_target or (Params.pitchLength / 2, 0)
    args = (xy(Ball.pos()), xy(Ball.vel()), xy(Player.Pos(mainshoot)),
            xy(Player.vel(mainshoot)), Player.direction(mainshoot))
    plan = touch_intercept(*args, target, legal, MOUTH_OFFSET, SHOT_SPEED, INCOMING_RETAIN)
    # 无合法触球方案时停车，避免使用过期或越界的拦截点。
    if plan is None:
        return stop(mainshoot)
    contact = plan[0]
    select_touch_target(control, contact)
    plan = touch_intercept(*args, control.shot_target, legal, MOUTH_OFFSET, SHOT_SPEED, INCOMING_RETAIN)
    # 更新射门目标后重新求解触球点；目标变化可能改变补偿角和可达性。
    if plan is None:
        return stop(mainshoot)
    _, centre, _, angle = plan
    bound, width = movement_bounds(mainshoot)
    centre = (max(-bound, min(bound, centre[0])), max(-width, min(width, centre[1])))
    # 再次核对裁剪后的预测车心；若拦截方案越界则停车，不执行该方案。
    if not legal(centre):
        return stop(mainshoot)

    def execute(n):
        kick_ready = can_kick(n)
        # 球进入击球窗口时，以当前球位和最新门将位置重新选角，避免沿用接球途中的目标。
        if kick_ready:
            select_touch_target(control, xy(Ball.pos()))
        desired = redirect_heading(xy(Ball.pos()), control.shot_target, xy(Ball.vel()), SHOT_SPEED, INCOMING_RETAIN)
        # 远处沿预测拦截朝向接球；准备出球时立即朝向重新选出的门角。
        v5_skill, _ = Skill.GetBallV5(desired if kick_ready else angle, ifIntercept=True)
        # GetBallV5 不会自行开启吸球；持续吸球以稳定拦接来球。
        C.setDribbleCommand(n, A.DRIBBLE_COMMAND)
        v5_skill(n)
        kickStatus.setBothKick(n, 0, 0)
        # 使用当前可击打范围；不等待 held、停球或门将让出球路。
        h = Player.direction(n) + Player.rotVel(n) * A.COMMAND_DELAY
        vx = SHOT_SPEED * math.cos(h) + INCOMING_RETAIN * Ball.vel().x()
        vy = SHOT_SPEED * math.sin(h) + INCOMING_RETAIN * Ball.vel().y()
        goal_y = Ball.posY() + (Params.pitchLength / 2 - Ball.posX()) * vy / vx if vx > 0 else float('inf')
        # 只有球在击球窗口内、预计触球朝向正确且合成出球射线命中门内，才允许触球射门。
        if kick_ready and angle_error(h, desired) < A.TOUCH_ANGLE and abs(goal_y) < Params.goalWidth / 2 - A.GOAL_RAY_MARGIN:
            power = min(control.cap, evalPower(Ball.pos(), point(control.shot_target), P.HIGH))
            if math.isfinite(power) and power > 0:
                kickStatus.setKick(n, power)
                control.last_power = power
                control.shot_locked = True
                if state.fired is None:
                    state.fired = xy(Ball.pos())
    return Task((execute, lambda n: Ball.pos()), fixedNumber=mainshoot)


class InterceptAndShoot(AttackState):
    def getTasks(self):
        return {'A': touch_shot(self), 'B': stop(assistant)}

    def released(self, number):
        # 拦截射门还要求球向前越过速度门槛，排除横向碰球或接触抖动造成的假释放。
        return super().released(number) and Ball.vel().x() > A.SHOT_RELEASE_VX

    def transFunction(self):
        # 只有确认球已向前射出并与机器人分离，才结束本次进攻流程。
        if self.released(mainshoot):
            return 'Done'
        return ''


class Done(AttackState):
    def getTasks(self):
        return {'A': stop(mainshoot), 'B': stop(assistant)}


@declare_state_machine(GetFirstBall, PassToAssistant, ReceiveAndReturn, PassBack,
                       InterceptAndShoot, Done)
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
                state.fired = state.target = None
                state.incoming_seen = False
        self.control.update()
        for state in self.states.values():
            state.control = self.control
        name = self.current_state.state_name
        # 仅在状态变化时打印，避免每个控制周期重复输出相同状态。
        if name != self.last_state:
            print('TWO_ATTACK:', name, flush=True)
            self.last_state = name
