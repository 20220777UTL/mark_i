from functools import wraps
from typing import Optional

import Global
from RoleMatch_LuaStyle import State
from Utils import DebugColor
from WorldModel import worldModel, kickStatus
from Geometry import *
from Global import debugEngine
class StateMachine:
    """任务组类：只负责状态机的调度"""

    def __init__(self):
        self.name = self.__class__.__name__
        self.states:"dict[str, State]" = {}
        self.start_state:"Optional[State]" = None
        self.current_state:"Optional[State]" = None
        self.isStateSwitched = True # 第一次应该是True！！！
        self.context = {} # 上下文变量，预计是一个字典

    def planTasks(self):
        """这是调用的首入口"""
        self.hookBeforePlanTasks()
        debugEngine.gui_debug_msg(CGeoPoint(-812,3274), f"Current Play: {self.name}", debug_color=DebugColor.Yellow)  # 在界面上显示当前裁判消息
        if Global.isPlaySwitched: # 如果Play发生了切换，比如从裁判盒到NormalPlay
            self.isStateSwitched = True
            self.current_state = self.start_state

        if not self.current_state:
            print(f"[StateMachine {self.name}] No current state set.")
            raise Exception("No current state set in StateMachine.")

        if self.isStateSwitched:
            worldModel.SPlayFSMSwitchClearAll(True)
        kickStatus.clearAll()

        Global.debugEngine.gui_debug_msg(CGeoPoint(2204,-3449), f"Current State: {self.current_state.state_name}", debug_color=DebugColor.Yellow)
        next_state_name = self.current_state.run(self.isStateSwitched)
        

        if not next_state_name or next_state_name=="":
            # 此时默认不进行状态机切换
            self.isStateSwitched = False #调整回False
        elif next_state_name.lower()=="exit":
            # 只有一种情况，就是RefPlay人为手动控制exit退出
            self.isStateSwitched = False
            Global.hasFinishedRefPlay = True
        elif next_state_name in self.states:
            self.isStateSwitched = next_state_name != self.current_state.state_name
            self.current_state = self.states[next_state_name]
        else:
            # 此时是无效切换，名字对不上
            self.isStateSwitched = False
            if Global.needDetailedRuntimeDebugInfo:
                print(
                f"[StateMachine {self.name}] No valid transition from {self.current_state.state_name}")
        
        self.hookAfterPlanTasks()
    
    def hookBeforePlanTasks(self):
        pass
    def hookAfterPlanTasks(self):
        pass


def declare_state_machine(*state_classes):
    """
    group(聚合) states(状态)，即聚合这些状态
    写的第一个类会成为start_state，也就是最开始的current_state
    装饰器：将状态类列表注入 StateMachine 子类
    """
    def wrapper(cls):
        original_init = getattr(cls, '__init__', lambda self: None)

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            # `cls` is the class being decorated; `cls.__class__` is `type`.
            # Use `cls.__name__` to get the class name instead of getting 'type'.
            self.name = cls.__name__
            self.states = {}

            # 实例化
            self.state_instances = [state_cls() for state_cls in state_classes]
            if self.state_instances:
                self.start_state = self.state_instances[0] # 最开始的状态为第一个
                self.current_state = self.start_state
            else:
                print(f"[StateMachine {self.name}] No states defined.")
                return

            # 将状态实例添加到 states 字典中
            for state in self.state_instances:
                self.states[state.state_name] = state

        cls.__init__ = new_init
        return cls
    return wrapper
