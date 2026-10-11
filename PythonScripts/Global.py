import copy
import CppPackage
import configparser
import os
from pathlib import Path
from enum import Enum, auto
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from CppPackage import ParamType, CGeoPoint
    from RoleMatch_LuaStyle import Task

# ——————————从zss.ini中读取变量
"""
注意：对于QSettings和python的configparser.ConfigParser()，二者都是对Key, Section不区分大小写，
对于等号后面的空格也有很高的容忍度，对于bool类型的变量，True true等都能识别，1,0的识别则和python的
configparser.ConfigParser()行为可能不一致，写入的大小写行为也不一致。这边自定义类CaseSensitiveConfigParser
是为了读入的时候不区分大小写，写入的时候区分大小写

受限于pybind11绑定的问题，绑定之后ParamManagerZSS的父类会有静态方法初始化问题，导致会在当前的python
解释器的工作目录下读取ini文件。这会导致从python和C++启动时候的行为不一致问题，在更新添加python的启动方式
的时候，删去了通过C++的ParaManagerZSS读入的方式，改用Python自带的ini管理器读入。
"""
class CaseSensitiveConfigParser(configparser.ConfigParser):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 默认保持大小写敏感，这样写入时会遵循原始样式
        self.optionxform = str

    def get(self, section, option, *args, **kwargs):
        # 在查找前，先找到实际存在的那个 Key（无论大小写）
        actual_key = self._find_actual_key(section, option)
        return super().get(section, actual_key, *args, **kwargs)

    def _find_actual_key(self, section, option):
        """辅助方法：在指定的 section 中找到匹配的原始 Key"""
        if self.has_section(section):
            for existing_key in self.options(section):
                if existing_key.lower() == option.lower():
                    return existing_key
        return option # 如果没找到，返回原样以便触发默认的错误处理

# ParamManagerZSS = CppPackage.ParamManagerZSS.Instance()
# isYellow = ParamManagerZSS.getParam("ZAlert/IsYellow", ParamType.Bool, False)
# isRight = ParamManagerZSS.getParam("ZAlert/IsRight", ParamType.Bool, False)
# isSimulation = ParamManagerZSS.getParam("Alert/IsSimulation", ParamType.Bool, False)
# SAO_ACTION        = CGetSettings("Alert/SaoAction","Int")
# IS_YELLOW         = CGetSettings("ZAlert/IsYellow","Bool")
# IS_RIGHT          = CGetSettings("ZAlert/IsRight", "Bool")
# DEBUG_MATCH       = CGetSettings("Debug/RoleMatch","Bool")
# USE_11vs11_SOLVER = CGetSettings("Messi/USE_11vs11SOLVER","Bool")

# 从zss.ini中读取裁判盒相关参数
isYellow: bool
isRight: bool
isSimulation: bool
def read_config_file(config_file_path):
    configParser = CaseSensitiveConfigParser()
    # 如果配置文件存在则读取，否则创建新文件
    if os.path.exists(config_file_path):
        configParser.read(config_file_path, encoding='utf-8')
    global isYellow, isRight, isSimulation
    isYellow = configParser.getboolean("ZAlert", "IsYellow", fallback=False)
    isRight = configParser.getboolean("ZAlert", "IsRight", fallback=False)
    isSimulation = configParser.getboolean("Alert", "IsSimulation", fallback=False)
# ——————————end 从zss.ini中读取的变量


# ——————————下面的变量会在Config.py的顶层语句被InitAllModules.py中import的时候中被初始化
isTestMode: bool
isSmallField = True  # 是否为小场地比赛
isDebugMode = False
gameStrategies = {}
needDetailedRuntimeDebugInfo = True  # 是否需要详细的运行时debug信息
# ——————————end 在Config.py中被初始化的变量


# ——————————会在SelectPlay.py中更新
lastPlayName = ""
currentPlayName = ""
isPlaySwitched = False
hasFinishedRefPlay = True
"""
这个是用于额外的手动判断裁判盒的跳转逻辑
有的裁判盒切换不准确，比如FreeKick到NormalPlay，过早的进入了NormalPlay，则需要在Python层手动控制。基本逻辑是：
如果hasFinishedRefPlay=False，则说明需要等裁判盒的tranFunction返回"exit"之后才算运行完这个裁判盒脚本，才会
继续跳转。但是如果此时裁判盒发的是GameStop或者Halt，则强行停止
"""

# ——————————end 会在SelectPlay.py中更新


# ——————————力度计算参数（PowerCalculator 使用）
# 修改这些值即可全局调整力度行为，无需改 PowerCalculator.py
powerMax = 12700           # 正常输出上限（比赛规则）
powerCurveFile = str(Path("data") / "power_curve" / "active_curve.json")
powerCurveReloadIntervalSec = 0.2
# ——————————end 力度计算参数

# ——————————裁判盒相关脚本中使用
lastRefCycle = 0 # 用于裁判盒脚本中智能控制，可能会刷新状态重新执行脚本吧。目前大致处于弃用状态

# ——————————end 裁判盒相关脚本中使用

def ball():
    return CppPackage.VisionModule.Instance().ball()


debugEngine = CppPackage.DebugEngine.Instance()  # 使用CppPackage.DebugEngine()是一样的，pybind层写好了，等价于获取单例


class RoleNumberStruct:
    """
    规范roleNumber数据储存的结构体，不要与传统用法混淆
    """
    class MatchType(Enum):
        """
        role match的时候的role-number的匹配规则
        Auto: 进入传统的role match模式
        Fixed: 该角色与车号绑定
        本意是把原来lua层的gRoleNumber的-1既表示自动匹配又表示暂未分配车号的语义功能给拆开了
        """
        Auto = auto(),
        Fixed = auto(),

    def __init__(self, matchType, currentRoleNumber=-1):
        self.matchType = matchType
        self.currentRoleNumber = currentRoleNumber  # 如果为-1则表示当前角色未分配到车号

    def resetRoleNumber(self):
        match self.matchType:
            case RoleNumberStruct.MatchType.Auto:
                self.currentRoleNumber = -1
            case RoleNumberStruct.MatchType.Fixed:
                # 如果是固定的角色号，则不重置
                pass


defaultRoleNumberStructTable: "dict[str, RoleNumberStruct]" = {
    "A": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),
    "B": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),
    "C": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),
    "D": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),
    "E": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),
    "F": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),
    "G": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),  # G是守门员，在Config.py中设置
    "H": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),
    "I": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),
    "J": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),
    "K": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),  # 第11辆车

    # 下面的虚拟车号可用于调试，需在Config.py中设置车号等才能手动启用这些role，或者在getTasks()中指定，用于特殊的角色代号或者与旧版本lua兼容
    "L": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),  # 第12辆车
    "M": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),  # 第13辆车
    "N": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),  # 第14辆车
    "P": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),  # 第15辆车
    "Q": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),  # 第16辆车
    "R": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),  # 第17辆车
    "S": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),  # 第18辆车
    "T": RoleNumberStruct(RoleNumberStruct.MatchType.Auto),  # 第19辆车
}

goalieNumber = 0 # 在Config.py中调整

roleNumberStructTable = copy.deepcopy(defaultRoleNumberStructTable)  # 复制一份，避免修改默认值
lastRoleNumberStructTable = copy.deepcopy(roleNumberStructTable)  # 一定是copy!!!

def getRoleNumber(roleName: str) -> int:
    """
    获取角色号
    :param roleName: 角色名称
    :return: 角色号，如果未分配则返回-1
    """
    if roleName not in roleNumberStructTable.keys():
        print(f"Invalid role name: {roleName}")
        return -1
    return roleNumberStructTable[roleName].currentRoleNumber

def roleNumber(roleName: str) -> int:
    """
    获取角色号的别名，这是为了和lua老的兼容
    :param roleName: 角色名称
    :return: 角色号，如果未分配则返回-1
    """
    return getRoleNumber(roleName)

def getLastRoleNumber(roleName: str) -> int:
    """
    获取上一次分配的角色号
    :param roleName: 角色名称
    :return: 上一次分配的角色号，如果未分配则返回-1
    """
    if roleName not in lastRoleNumberStructTable.keys():
        print(f"Invalid role name: {roleName} when getting lastRoleNumber")
        return -1
    return lastRoleNumberStructTable[roleName].currentRoleNumber

def lastRoleNumber(roleName: str) -> int:
    """
    获取上一次分配的角色号的别名，这是为了和lua老的兼容
    :param roleName: 角色名称
    :return: 上一次分配的角色号，如果未分配则返回-1
    """
    return getLastRoleNumber(roleName)

"""
roleNumbers和lastRoleNumbers仅仅用于记录当前的分配情况，必须放在Global中，便于跨不同状态调用、查询

但是在Config.py中对roleNumbers中指定的fixedNumber在进行匹配的时候也会被考虑到。优先级：getTasks()中指定的fixedNumber如果和roleNumbers中指定的冲突，则会覆盖后者。剩下的fixedNumber取并集

还有一个记录中心是Task类本身，其记录了roleName，num，并去中心化的自行执行。
"""


def resetRoleNumbersTableBetweenPlays():
    """
    用于不同的Play之间重置角色号表。
    :return:
    """
    global roleNumberStructTable, lastRoleNumberStructTable
    roleNumberStructTable = copy.deepcopy(defaultRoleNumberStructTable)
    lastRoleNumberStructTable = copy.deepcopy(defaultRoleNumberStructTable)

def resetRoleNumbersTableBeforeRoleMatch():
    """
    用于在RoleMatch之前重置角色号表。
    :return:
    """
    global roleNumberStructTable
    roleNumberStructTable = copy.deepcopy(defaultRoleNumberStructTable)



class TempRoleNumber:
    defaultTempRoleNumber = {
        "A": -1,
        "B": -1,
        "C": -1,
        "D": -1,
        "E": -1,
        "F": -1,
        "H": -1,
        "I": -1,
        "J": -1,
        "K": -1,
        "L": -1,
        
        "M": -1,
        "N": -1,
        "P": -1,
        "Q": -1,
        "R": -1,
        "S": -1,
        "T": -1,
        
        "G": -1,
    }
    def __init__(self):
        self.table = TempRoleNumber.defaultTempRoleNumber.copy() # 复制一份，避免修改默认值

    def __getitem__(self, key):
        # 这里可以自定义读取行为
        return self.table[key]

    def __setitem__(self, key, value):
        # 这里可以自定义写入行为
        self.table[key] = value

    def getRoleNameByNumber(self, roleNumber: int):
        """
        根据临时编号查找对应的角色名。
        如果存在多个相同编号，则返回首个匹配项。
        """
        for roleName, value in self.table.items():
            if value == roleNumber:
                return roleName
        return None

    def resetTempRoleNumber(self):
        self.table = TempRoleNumber.defaultTempRoleNumber.copy()  # 复制一份，避免修改默认值

    def adjustTempRoleNumber(self, tasks: "dict[str, Task]"):
        """
        调整编号，用于人工指定部分任务的编号分配！
        :param tasks:
        :return:
        """
        for roleName, task in tasks.items():
            task.setFixedNumber(self.table[roleName])
            
    

# 每个任务(role)的 role-matchPos集合对，是在munkres运行之后获取的matchPos
# 在State.py的run中被维护
rolePositions:"dict[str, CGeoPoint]" = {}
def getRolePos(role: str):
    return rolePositions[role]
