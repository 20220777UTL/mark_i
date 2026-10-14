"""双车配合的纯几何计算。位置 mm，速度 mm/s，角度 rad。"""
import math
from Play.Normal import AttackParams as A


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def direction(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def kick_ball_pos(ball, target, prep_length):
    """Return kick direction and the robot center behind a stationary ball."""
    angle = direction(ball, target)
    return angle, (ball[0] - prep_length * math.cos(angle),
                   ball[1] - prep_length * math.sin(angle))


def angle_error(a, b):
    return abs(math.atan2(math.sin(a - b), math.cos(a - b)))


def ball_at(ball, velocity, t, decel=A.BALL_DECEL):
    speed = math.hypot(*velocity)
    # 低于静止阈值时不再外推，避免零速除法和噪声造成的位置漂移。
    if speed < A.STATIONARY_SPEED:
        return ball
    # 球停下后保持最终位置；不让匀减速模型继续预测反向运动。
    t = min(t, speed / decel)
    travel = speed * t - decel * t * t / 2
    return (ball[0] + velocity[0] / speed * travel,
            ball[1] + velocity[1] / speed * travel)


def intercept(ball, velocity, robot, robot_velocity, legal, mouth=A.MOUTH_OFFSET, *, with_heading=False, robot_heading=None):
    """选最早赶得上的合法接球点；预测范围 1 s，不追到禁区里。"""
    best, cost = (robot, direction(robot, ball)), float('inf')
    for step in range(1, A.PREDICT_STEPS + 1):
        t = step * A.PREDICT_STEP
        future = ball_at(ball, velocity, t)
        facing = (math.atan2(-velocity[1], -velocity[0])
                  if math.hypot(*velocity) > A.RECEIVE_MOVING_SPEED else direction(robot, future))
        centre = (future[0] - mouth * math.cos(facing),
                  future[1] - mouth * math.sin(facing))
        # 接球中心非法时跳过该时刻，不能把机器人规划进边界或禁区。
        if not legal(centre):
            continue
        heading = direction(robot, centre)
        speed0 = max(-A.MODEL_SPEED, min(A.MODEL_SPEED, robot_velocity[0] * math.cos(heading)
                              + robot_velocity[1] * math.sin(heading)))
        travel = max(0, distance(robot, centre) - A.INTERCEPT_TOLERANCE)
        accelerate_for = min(t, (A.MODEL_SPEED - speed0) / A.MODEL_ACCEL)
        reachable = (speed0 * accelerate_for + 0.5 * A.MODEL_ACCEL * accelerate_for ** 2
                     + A.MODEL_SPEED * (t - accelerate_for))
        turn_time = 0 if robot_heading is None else angle_error(robot_heading, facing) / A.TURN_RATE_ESTIMATE
        # 找到最早同时满足平移可达和转向可达的点；若都不可达，保留欠缺最小的候选。
        if travel <= reachable and turn_time <= t:
            return (centre, facing) if with_heading else centre
        if travel - reachable < cost:
            best, cost = (centre, facing), travel - reachable
    return best if with_heading else best[0]


def clearance(ball, target, keeper, keeper_velocity, delay, speed, radius=A.DEFAULT_ROBOT_RADIUS):
    """在同一时间轴比较球路和门将；每段用相对运动求最近距离。

    匀速门将预测加随时间增长的误差半径，不把外推位置当成事实。
    """
    length = distance(ball, target)
    # 起点与目标重合时没有可评估的射线路径，按完全不安全处理。
    if length < 1:
        return -float('inf')
    duration = length / speed
    vx, vy = (target[0] - ball[0]) / duration, (target[1] - ball[1]) / duration
    rx = ball[0] - keeper[0] - keeper_velocity[0] * delay
    ry = ball[1] - keeper[1] - keeper_velocity[1] * delay
    ux, uy = vx - keeper_velocity[0], vy - keeper_velocity[1]
    relative_speed2 = ux * ux + uy * uy
    # 将最近接时间限制在球实际经过的射线时段内；相对静止时最近点就是起点。
    closest = 0 if relative_speed2 < 1 else max(0, min(duration, -(rx * ux + ry * uy) / relative_speed2))
    uncertainty = A.KEEPER_BASE_MARGIN + A.KEEPER_UNCERTAINTY * (delay + closest) ** 2
    return math.hypot(rx + ux * closest, ry + uy * closest) - radius - A.BALL_RADIUS - uncertainty


def shot_score(ball, target, heading, keeper, velocity, radius=A.DEFAULT_ROBOT_RADIUS, delay=None):
    # 转向时间并入评分；没有门将观测时使用保守的固定净空估计。
    delay = A.LANE_DELAY + angle_error(heading, direction(ball, target)) / A.TURN_RATE_ESTIMATE if delay is None else delay
    # 未标定的球速区间：同时评估快/慢球，避免只靠某个乐观速度。
    gap = min(clearance(ball, target, keeper, velocity, delay, speed, radius)
              for speed in A.LANE_SPEEDS) if keeper is not None else A.NO_KEEPER_GAP
    return gap - A.SHOT_DELAY_PENALTY * delay, gap


def choose_shot(ball, heading, goal_x, goal_width, keeper=None,
                velocity=(0, 0), previous=None, radius=A.DEFAULT_ROBOT_RADIUS, delay=None):
    edge = goal_width / 2 - A.SHOT_POST_MARGIN  # 球半径、门柱误差和瞄准余量。
    candidates = [(goal_x, -edge + 2 * edge * i / (A.SHOT_TARGET_COUNT - 1)) for i in range(A.SHOT_TARGET_COUNT)]
    # 在门内离散取样，按最差球速下的净空与转向耗时共同选目标。
    best = max(candidates, key=lambda p: shot_score(ball, p, heading, keeper, velocity, radius, delay)[0])
    if previous is not None:
        old_score, old_gap = shot_score(ball, previous, heading, keeper, velocity, radius, delay)
        new_score, _ = shot_score(ball, best, heading, keeper, velocity, radius, delay)
        # 旧目标仍有正净空且分数接近时沿用，避免目标在相邻采样点间来回跳。
        if old_gap > 0 and old_score >= new_score - A.SHOT_SWITCH_MARGIN:
            best = previous
    return best


def ellipse_keeper(ball, goal_x,
                   half_x=A.GOALIE_ELLIPSE_HALF_X,
                   half_y=A.GOALIE_ELLIPSE_HALF_Y):
    """Estimate the static keeper center on the goal-centered ellipse."""
    dx, dy = ball[0] - goal_x, ball[1]
    normalized_radius = math.hypot(dx / half_x, dy / half_y)
    # 球恰在椭圆中心时方向未定义，退回门线中心作为门将估计位置。
    if normalized_radius <= 1e-9:
        return (goal_x, 0.0)
    scale = 1.0 / normalized_radius
    return (goal_x + scale * dx, scale * dy)


def static_clearance(ball, target, keeper, radius=A.DEFAULT_ROBOT_RADIUS):
    """Minimum geometric clearance between a shot segment and a static keeper."""
    dx, dy = target[0] - ball[0], target[1] - ball[1]
    length_squared = dx * dx + dy * dy
    # 退化线段无法定义投影位置，视为没有净空。
    if length_squared < 1:
        return -float('inf')
    # 投影参数裁剪到 [0, 1]，因此比较的是整条有限射线段，而非无限直线。
    fraction = max(0.0, min(1.0,
                            ((keeper[0] - ball[0]) * dx + (keeper[1] - ball[1]) * dy)
                            / length_squared))
    closest = (ball[0] + fraction * dx, ball[1] + fraction * dy)
    return distance(closest, keeper) - radius - A.BALL_RADIUS


def choose_static_shot(ball, goal_x, goal_width, keeper, previous=None,
                       radius=A.DEFAULT_ROBOT_RADIUS):
    """Aim through the widest static gap while retaining the post margin."""
    edge = goal_width / 2 - A.SHOT_POST_MARGIN
    candidates = [(goal_x, -edge + 2 * edge * i / (A.SHOT_TARGET_COUNT - 1))
                  for i in range(A.SHOT_TARGET_COUNT)]
    # 逐个计算射线到静态门将的净空，再选净空最大的门内目标。
    clearance_by_target = {target: static_clearance(ball, target, keeper, radius)
                           for target in candidates}
    best = max(candidates, key=clearance_by_target.__getitem__)
    if previous is not None:
        old_clearance = static_clearance(ball, previous, keeper, radius)
        # 原目标仍无碰撞风险且与最优净空相差不大时，优先保持瞄准稳定。
        if (old_clearance > 0
                and old_clearance >= clearance_by_target[best] - A.SHOT_SWITCH_MARGIN):
            best = previous
    return best


def choose_corner_shot(ball, goal_x, goal_width, keeper=None, previous=None):
    """以球为顶点，瞄准与实测门将方向夹角更大的门角，保留门柱余量。"""
    edge = goal_width / 2 - A.SHOT_POST_MARGIN
    corners = ((goal_x, -edge), (goal_x, edge))
    # 没有有效门将位置或门将与球重合时，沿用已选门角；首次选择距离球较近的一角。
    if keeper is None or distance(ball, keeper) < 1:
        return previous if previous in corners else min(corners, key=lambda p: distance(ball, p))
    keeper_angle = direction(ball, keeper)
    openings = [angle_error(direction(ball, corner), keeper_angle) for corner in corners]
    # 两侧夹角相等时保持原目标；有明确差异时选择角度更大的一侧。
    if abs(openings[0] - openings[1]) < 1e-9 and previous in corners:
        return previous
    return corners[0] if openings[0] >= openings[1] else corners[1]


def redirect_heading(ball, target, incoming, shot_speed, retain):
    """补偿来球的横向速度；shot_speed / retain 是待标定的物理估计。"""
    aim = direction(ball, target)
    lateral = -incoming[0] * math.sin(aim) + incoming[1] * math.cos(aim)
    # 只补偿可实现范围内的横向来球速度，避免反正弦输入越界或产生过度修正。
    correction = max(-A.REDIRECT_SINE_LIMIT, min(A.REDIRECT_SINE_LIMIT, -retain * lateral / shot_speed))
    return aim + math.asin(correction)


def touch_intercept(ball, velocity, robot, robot_velocity, heading, target,
                    legal, mouth, shot_speed, retain):
    """以射门朝向拦球，返回球的触点、车心、到球时间和朝向。"""
    best, cost = None, float('inf')
    for step in range(A.PREDICT_STEPS + 1):
        t = step * A.PREDICT_STEP
        contact = ball_at(ball, velocity, t)
        speed = math.hypot(*velocity)
        # 球速太低时不计算减速比例，避免除零；此时按静止球处理。
        factor = max(0, 1 - A.BALL_DECEL * t / speed) if speed > A.STATIONARY_SPEED else 0
        incoming = (velocity[0] * factor, velocity[1] * factor)
        facing = redirect_heading(contact, target, incoming, shot_speed, retain)
        centre = (contact[0] - mouth * math.cos(facing), contact[1] - mouth * math.sin(facing))
        # 拦截中心必须合法；不合法的未来触球点直接排除。
        if not legal(centre):
            continue
        move_dir = direction(robot, centre)
        speed0 = max(-A.MODEL_SPEED, min(A.MODEL_SPEED, robot_velocity[0] * math.cos(move_dir)
                              + robot_velocity[1] * math.sin(move_dir)))
        accelerating = min(t, (A.MODEL_SPEED - speed0) / A.MODEL_ACCEL)
        reachable = speed0 * accelerating + 0.5 * A.MODEL_ACCEL * accelerating ** 2 + A.MODEL_SPEED * (t - accelerating)
        deficit = max(distance(robot, centre) - A.TOUCH_TOLERANCE - reachable,
                      (angle_error(heading, facing) / A.TURN_RATE_ESTIMATE - t - A.COMMAND_DELAY) * A.TOUCH_TIME_COST)
        candidate = contact, centre, t, facing
        # 按时间顺序返回首个平移和转向都来得及的触球点，否则保留欠缺最小的方案。
        if deficit <= 0:
            return candidate
        if deficit < cost:
            best, cost = candidate, deficit
    return best
