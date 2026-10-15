"""Small, pure geometry helpers. No assumed friction or kick velocity."""
import math
from dataclasses import dataclass
from Play.Normal import AttackParams as A


def distance(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def direction(a, b):
    return math.atan2(b[1] - a[1], b[0] - a[0])


def angle_error(a, b):
    return abs(math.atan2(math.sin(a - b), math.cos(a - b)))


def behind(contact, heading, offset):
    return (contact[0] - offset * math.cos(heading),
            contact[1] - offset * math.sin(heading))


def intercept_contact(ball, velocity, mouth):
    """Nearest point on a short observed velocity segment; replan every frame."""
    speed2 = sum(v * v for v in velocity)
    t = 0 if speed2 < A.MOVING_SPEED ** 2 else max(0, min(A.PREDICT_HORIZON,
        sum((m - b) * v for m, b, v in zip(mouth, ball, velocity)) / speed2))
    return tuple(b + v * t for b, v in zip(ball, velocity))


def static_clearance(ball, target, obstacle, radius):
    dx, dy = target[0] - ball[0], target[1] - ball[1]
    length2 = dx * dx + dy * dy
    if length2 < 1:
        return -math.inf
    t = max(0, min(1, ((obstacle[0] - ball[0]) * dx + (obstacle[1] - ball[1]) * dy) / length2))
    return distance((ball[0] + t * dx, ball[1] + t * dy), obstacle) - radius - A.BALL_RADIUS


def choose_corner_shot(ball, goal_x, goal_width, keeper=None):
    edge = goal_width / 2 - A.SHOT_POST_MARGIN
    corners = ((goal_x, -edge), (goal_x, edge))
    if keeper is None or distance(ball, keeper) < 1:
        return min(corners, key=lambda p: distance(ball, p))
    return max(corners, key=lambda p: angle_error(direction(ball, p), direction(ball, keeper)))


def goal_ray(ball, heading, goal_x, goal_width):
    if math.cos(heading) <= 0 or ball[0] >= goal_x:
        return False
    y = ball[1] + (goal_x - ball[0]) * math.tan(heading)
    return abs(y) < goal_width / 2 - A.GOAL_RAY_MARGIN


def crossed_goal(previous, current, goal_x, goal_width):
    line = goal_x + A.BALL_RADIUS
    if previous is None or not previous[0] < line <= current[0]:
        return False
    t = (line - previous[0]) / (current[0] - previous[0])
    return abs(previous[1] + t * (current[1] - previous[1])) <= goal_width / 2 - A.BALL_RADIUS


@dataclass(frozen=True)
class ReturnPlan:
    contact: tuple
    centre: tuple
    landing: tuple
    goal: tuple
    heading: float
    is_chip: bool


def return_plan(source, contact, goal, mouth_offset, landing_lead=0):
    """L is before P along B -> P; R is behind P along P -> G."""
    length = distance(source, contact)
    if length <= landing_lead or length < 1 or landing_lead < 0:
        raise ValueError('Return pass has no positive flight distance')
    heading = direction(contact, goal)
    landing = tuple(p - landing_lead * (p - b) / length for p, b in zip(contact, source))
    return ReturnPlan(contact, behind(contact, heading, mouth_offset), landing,
                      goal, heading, landing_lead > 0)
