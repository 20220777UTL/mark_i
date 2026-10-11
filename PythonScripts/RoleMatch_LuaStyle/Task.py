# 规范 skill_cpp 调用，不再暴露车号
# 为分配任务做准备
from typing import Optional, final, Callable, Union, Any

import Vision
from Geometry import *


class Task:
    """
    任务类，需要外界传入func（也就是各种skill），个性化指定fixedNumber，matchPos（对应原lua的匹配位置）等。
    需要注意Task的生命周期！每次是重新创建的Task对象！这也就是会重新计算参数！但是State类的生命周期是更长的。后人写代码的时候需要注意这些
    """
    def __init__(self, skill:Union[
                             "tuple[Callable[[int],None], Callable[[int],CGeoPoint]], "
                             "Callable[[],Callable[[Any],tuple[Callable[[int],None], Callable[[int],CGeoPoint]]]], "
                             "Callable[[int],Callable[[Any],tuple[Callable[[int],None], Callable[[int],CGeoPoint]]]]"
                             ]
                 , *, fixedNumber: "int"=-1, description: str="") -> None:
        """
        skill如果涉及playerPos("B")这种需要延迟计算的，需要使用lambda:或者lambda runner:表达式包装一层。我们会正确处理这种情况。skill_cpp()的计算一定是逻辑正确的，但是为了解决先匹配的矛盾，所以一定是使用上一帧残留的matchPos先匹配（self.achedMatchPos最先赋值为Vision.ball().Pos()）
        :param skill: 可以是lambda，可以是lambda runner:，也可以是原始的skill。前面两种都是会被延迟计算的，runner是等matchPos进行match分配之后真实的车号。
        :param fixedNumber:
        :param description: 仅仅用于自我提示，方便debug
        """

        self.achedMatchPos = Vision.ball().Pos()  # 上一次缓存的匹配位置，在State类中进行管理和设置（生命周期的问题）
        self.needDelayComputingMatchPos = False
        """
        matchPos: 设置匹配位置，默认使用全局球的位置
        当匹配位置 = 或 十分接近 某球员位置时，相当于直接匹配该球员，例如原版 lua 的 advance
        """
            
        if (hasattr(skill, '__name__') and getattr(skill, '__name__')) == '<lambda>' or callable(skill):
            self.needDelayComputingMatchPos = True
            self.delayedSkill = skill # 会在State中进行解包处理
        else:
            self.skill_cpp, self.matchPos = skill

        self.fixedNumber:int = fixedNumber
        self.num = fixedNumber

        self.name = skill.__name__ if hasattr(skill, '__name__') else str(skill) #仅仅用于报错信息
        self.roleName: Optional[str] = None # 在State.py中设置，暂存而已

        self.description = description

    def run(self, num: int):
        #在run被调用之前，已经由TaskGroups的类调用munkres_set_num分配好了num，并且对delayedSkill进行了解包
        self.skill_cpp(num)
    
    def getNum(self):
        if self.fixedNumber >= 0:
            return self.fixedNumber
        return self.num

    def setFixedNumber(self, fixedNumber: int):
        self.num = self.fixedNumber = fixedNumber

    @final
    def munkres_set_num(self, num: int):
        """
        暴露给munkres用的，仅仅能munkres使用
        设置车号，通常在任务分配时调用
        子类请不要覆写该方法
        """
        if num < 0:
            raise ValueError("num must be a non-negative integer")
        self.num = num

    @final
    def getMatchPos(self, executor: int)-> "CGeoPoint":
        """
        暴露给munkres用的，一般仅仅能munkres使用！当然在State.py和transFunction中可以使用
        其实更多的是通过task.achedMatchPos来获取matchPos
        :return:
        """
        if self.needDelayComputingMatchPos: #说明是希望延迟计算的
            return self.achedMatchPos # 在munkres分配车号之后进行延迟计算
        else:
            return self.matchPos(executor)