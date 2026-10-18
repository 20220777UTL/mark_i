"""选手编写：常规比赛中的进攻、防守和角色切换。默认不下发任务。"""
import Global
from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill, SimpleGoTo, Goalie, RushTo
from RoleMatch_LuaStyle import Task, State, declare_state_machine, StateMachine


class NormalState(State):
    def getTasks(self):
        # 在这里返回角色到 Task 的映射。
        return {    # # "A": Task(SimpleGoTo(C.CGeoPoint(1000, -500), 0, 0)),
                    # # "B": Task(SimpleGoTo(C.CGeoPoint(1000, 500), 0, 0)),
                    # #"C": Task(SimpleGoTo(CGeoPoint(1000, 1000), 0, 0), fixedNumber=2),
                    # "C": Task(Skill.RushTo(Ball.pos())),
                    # "D": Task(lambda: SimpleGoTo(self.playerPos("E") + CVector(200,200), 0, 0), fixedNumber=1),
                    # "E": Task(SimpleGoTo(CGeoPoint(1000, 1500), 0, 0)),
                    # "G": Task(SimpleGoTo(CGeoPoint(-3518,-3012), 0, 0)), # 应该会因为Config.py中的固定车号配置而被覆盖
                    # "H": Task(SimpleGoTo(Player.Pos("E") + CVector(-200,-200), 0, 0), fixedNumber=3), # 测试传统方法的效果
                    "A": Task(Skill.NormalShoot(12700, False), fixedNumber=1),
                    "G": Task(Skill.Goalie()),}

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(NormalState)
class ExampleNormalPlay(StateMachine):
    pass
