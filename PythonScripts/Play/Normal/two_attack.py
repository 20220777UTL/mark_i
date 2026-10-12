import math
import os

import CppPackage
from RoleMatch_LuaStyle import Task, State, StateMachine, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Geometry import CGeoPoint
from Vision import Ball, Player
from WorldModel import Params, kickStatus
from WorldModel.PowerCalculator import evalPower, P

mainshoot = 1
assistant = 2

class Start(State):
    def __init__(self):
        super().__init__()
        self._vision_status = None
        # both 保持原策略；另外三种模式用于隔离原生技能，不改变场景。
        self.diagnostic_mode = os.environ.get("SRC_TWO_ATTACK_DIAG", "both")
        if self.diagnostic_mode not in ("both", "passer", "receiver", "stop"):
            raise ValueError("SRC_TWO_ATTACK_DIAG must be both, passer, receiver or stop")
        self._trace_frames = 0
        self._trace_active = False

    @staticmethod
    def _direction(origin, target):
        return math.atan2(target.y() - origin.y(), target.x() - origin.x())

    @staticmethod
    def _angle_error(actual, desired):
        return abs(math.atan2(math.sin(actual - desired), math.cos(actual - desired)))

    def _move_skill(self, number, target, angle, dribble=False):
        # 显式传入合法朝向，且不经过 RushTo 的 fetchBall 角色注册。
        # 大角度偏差时先原地转正，避免取球时边转边撞球。
        destination = target
        if self._angle_error(Player.direction(number), angle) > math.radians(8):
            destination = Player.Pos(number)
        move, match_position = Skill.SimpleGoTo(destination, angle=angle)

        def execute(executor):
            CppPackage.setDribbleCommand(executor, 3 if dribble else 0)
            return move(executor)

        return execute, match_position

    def _pass_skill(self, target, power):
        # 使用基础移动和明确的出球条件，绕过 GoAndTurnKick 的原生组合规划。
        robot, ball = Player.Pos(mainshoot), Ball.pos()
        distance = math.hypot(ball.x() - robot.x(), ball.y() - robot.y())
        ball_direction = self._direction(robot, ball)
        shot_direction = self._direction(ball, target)
        has_ball = (distance < 160 and Player.isInfraredOn(mainshoot)
                    and self._angle_error(Player.direction(mainshoot), ball_direction) < .3)
        if has_ball:
            destination, angle = robot, shot_direction
        else:
            # 让吸球口接近球，不把车身中心移动到球上。
            offset = Params.playerFrontToCenter + 20
            destination = CGeoPoint(ball.x() - offset * math.cos(ball_direction),
                                    ball.y() - offset * math.sin(ball_direction))
            angle = ball_direction
        move, match_position = self._move_skill(
            mainshoot, destination, angle, dribble=distance < 400)
        receiver = Player.Pos(assistant)
        receiver_ready = (
            math.hypot(receiver.x() - target.x(), receiver.y() - target.y()) < 100
            and self._angle_error(Player.direction(assistant),
                                  self._direction(receiver, ball)) < math.radians(8))
        can_kick = (has_ball and receiver_ready and math.isfinite(power) and power > 0
                    and self._angle_error(Player.direction(mainshoot), shot_direction)
                    < math.radians(5))

        def execute(executor):
            result = move(executor)
            if can_kick:
                kickStatus.setKick(executor, power)
            return result

        return execute, match_position

    def _trace_skill(self, name, skill):
        execute, match_position = skill
        trace = self._trace_frames <= 3

        def traced_execute(number):
            if trace:
                print(f"[two_attack] ENTER {name} robot={number}", flush=True)
            result = execute(number)
            if trace:
                print(f"[two_attack] RETURN {name} robot={number}", flush=True)
            return result

        return traced_execute, match_position

    @staticmethod
    def _valid_position(point):
        return (math.isfinite(point.x()) and math.isfinite(point.y())
                and abs(point.x()) <= Params.pitchLength / 2 + 1000
                and abs(point.y()) <= Params.pitchWidth / 2 + 1000)

    def _vision_problem(self):
        # 固定车号不会因为视觉丢失而自动取消任务，必须在调用技能前检查。
        if not Ball.valid():
            return "ball is not visible"
        if not self._valid_position(Ball.pos()):
            return "ball position is invalid"
        for number in (mainshoot, assistant):
            if not Player.isValid(number):
                return f"our robot {number} is not visible; check team color and robot ID"
            if not self._valid_position(Player.Pos(number)):
                return f"our robot {number} position is invalid"
            angle = Player.direction(number)
            if not math.isfinite(angle) or abs(angle) > math.tau:
                return f"our robot {number} direction is invalid: {angle}"
        return None

    def getTasks(self):
        self._trace_active = False
        problem = self._vision_problem()
        status = problem or (f"vision ready; backend=SimpleGoTo + explicit kick; "
                             f"diagnostic mode={self.diagnostic_mode}")
        if status != self._vision_status:
            print(f"[two_attack] {status}", flush=True)
            self._vision_status = status
        if problem:
            kickStatus.clearAll()
            for number in (mainshoot, assistant):
                CppPackage.setDribbleCommand(number, 0)
            return {
                "A": Task(Skill.Stop(), fixedNumber=mainshoot),
                "B": Task(Skill.Stop(), fixedNumber=assistant),
            }

        target = CGeoPoint(
            Params.pitchLength / 2 - Params.penaltyDepth - 300,
            800,
        )

        self._trace_frames += 1
        trace = self._trace_frames <= 3
        self._trace_active = trace
        if trace:
            print(f"[two_attack] BUILD frame={self._trace_frames} "
                  f"ball=({Ball.pos().x()}, {Ball.pos().y()}) "
                  f"A.dir={Player.direction(mainshoot)} B.dir={Player.direction(assistant)}",
                  flush=True)

        # 隔离测试时也显式停止另一辆车，避免遗留吸球或踢球指令。
        kickStatus.clearAll()
        for number in (mainshoot, assistant):
            CppPackage.setDribbleCommand(number, 0)
        tasks = {}
        if self.diagnostic_mode in ("both", "passer"):
            power = evalPower(Ball.pos(), target, P.NORMAL)
            if trace:
                print(f"[two_attack] A BasicPass target=({target.x()}, {target.y()}) "
                      f"power={power}", flush=True)
            skill_a = self._pass_skill(target, power)
            tasks["A"] = Task(self._trace_skill("A.BasicPass", skill_a),
                              fixedNumber=mainshoot)
        else:
            tasks["A"] = Task(self._trace_skill("A.Stop", Skill.Stop()), fixedNumber=mainshoot)

        if self.diagnostic_mode in ("both", "receiver"):
            angle = self._direction(Player.Pos(assistant), Ball.pos())
            if trace:
                print(f"[two_attack] B SimpleGoTo target=({target.x()}, {target.y()}) "
                      f"angle={angle}", flush=True)
            skill_b = self._move_skill(assistant, target, angle, dribble=True)
            tasks["B"] = Task(self._trace_skill("B.SimpleGoTo", skill_b), fixedNumber=assistant)
        else:
            tasks["B"] = Task(self._trace_skill("B.Stop", Skill.Stop()), fixedNumber=assistant)
        if trace:
            print("[two_attack] BUILD complete; assigning and submitting tasks", flush=True)
        return tasks

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(Start)
class two_attack(StateMachine):
    def hookAfterPlanTasks(self):
        state = self.current_state
        if state._trace_active:
            print("[two_attack] Python planTasks complete; next is C++ postDecision", flush=True)
