from abc import abstractmethod, ABC
from typing import Callable, final
import CppPackage as C
import Global
import Global as G
import Vision
from Algorithm.munkre import DoMunkresMatch
from RoleMatch_LuaStyle.Task import Task
from Vision import Player


class State(ABC):
    def __init__(self, state_name = None):
        if state_name:
            self.state_name = state_name
        else:
            self.state_name = self.__class__.__name__
        self.tasks: "dict[str, Task]" = dict()  # 是以dict方式而不是list方式展示的tasks集合，前面的"A","B"等表示该任务执行机器人的角色（或者理解为任务的代号）
        # self.tasks_after_munkres: "list[Task]" = [] # 是一个list！！！
        self.achedMatchPos: "dict[str, C.CGeoPoint]" = {}  # 缓存matchPos，避免boostrap的自指矛盾
        self.defaultMatchPos = Vision.ball().Pos()

    def playerPos(self, player_name: str) -> C.CGeoPoint:
        """
        延迟获取球员位置：在munkres算法分配之后获取的，但是初始化还是做不到
        用于同一块任务列表之间的相互引用
        """
        return Vision.Player.ourPlayer(self.tasks[player_name].num).Pos()

    def playerNum(self, player_name: str) -> int:
        """
        延迟获取球员车号：在munkres算法分配之后获取的，但是初始化还是做不到
        用于同一块任务列表之间的相互引用
        """
        return self.tasks[player_name].num

    @abstractmethod
    def getTasks(self) -> "dict[str, Task]":
        """
        好处：可以延迟设置任务列表（实际上用不上）以及可以显示指定子类覆写、从子类的__init__方法中抽离
        """
        pass

    @abstractmethod
    def getMatchString(self) -> str:
        """
        设置匹配规则字符串：用于定义角色分配规则
        :return:匹配规则字符串。如果没有指定匹配规则，则默认实时分配所有角色
        """
        return ""

    @abstractmethod
    def transFunction(self) -> str:
        """
        状态转换函数：根据当前状态决定下一个状态
        :return:下一个状态的名称，如果为空字符串或者None或者无效str则不进行状态切换，
        最后一种情况会在Global.needDetailedRuntimeDebugInfo下打印详细信息
        """
        return ""

    @staticmethod
    @final
    def DecodeMatchStr(matchRule):
        """
        单纯将str转为分配规则列表，不进行额外的判断等

        输入输出示例：
        In[11]: DecodeMatchStr("[AB]{CD}(E)")
        Out[11]:
        [{'mode': 'RealTime', 'roles': ['A', 'B']},
         {'mode': 'Never', 'roles': ['C', 'D']},
         {'mode': 'Once', 'roles': ['E']}]
        :param matchRule:
        :return:
        """
        strTable = []
        teamCnt = 0
        if callable(matchRule):
            return matchRule
        elif isinstance(matchRule, str):
            s = matchRule
        else:
            print("RoleMatch:not a valid matchRule type!!")
            return []
        while s:
            character = s[0]
            if character == '[':
                endChar, mode = ']', "RealTime"
            elif character == '(':
                endChar, mode = ')', "Once"
            elif character == '{':
                endChar, mode = '}', "Never"
            else:
                break
            endPos = s.find(endChar)
            teamTable = [c for c in s[1:endPos]]
            teamTable.append(("mode", mode)) # 这边pycharm会提示类型不匹配，但实际上是可以的，就是teamTable是一个混合类型的list
            strTable.append(teamTable)
            s = s[endPos + 1:]
            if not s:
                break
        # 转换为dict结构
        result = []
        for team in strTable:
            mode = None
            if isinstance(team[-1], tuple) and team[-1][0] == "mode":
                mode = team[-1][1]
                team = team[:-1]
            result.append({"mode": mode, "roles": team})
        return result

    def updateRole(self, isStateSwitched):
        """
        更新角色信息：即更新Global.roleNumbers和self.tasks中的num字段
        :param isStateSwitched: 是否切换了状态
        """
        Global.resetRoleNumbersTableBeforeRoleMatch()
        ourExistVehicles = Player.getAllValidNumbers()
        # 先处理人为指定的固定车号分配的任务
        # 优先级：getTasks()中指定的fixedNumber如果和 Global.RoleNumberStruct 中指定的冲突，则会覆盖后者。剩下的，也就是Global中指定的和fixedNumber和setTasks里面指定的fixedNumber取并集
        fixedMatch_roles = []
        for roleName, structData_roleNumber in Global.roleNumberStructTable.items():
            if structData_roleNumber.matchType == Global.RoleNumberStruct.MatchType.Fixed:
                task_fixedMatch = self.tasks.get(roleName, None)
                if task_fixedMatch is not None:
                    fixedMatch_roles.append(roleName)
                    if task_fixedMatch.fixedNumber >= 0:
                        # 如果任务中也指定了固定车号，冲突了，以Task的fixedNumber为准
                        structData_roleNumber.currentRoleNumber = task_fixedMatch.fixedNumber
                    else:
                        # task_fixedMatch.fixedNumber = structData_roleNumber.currentRoleNumber
                        # task_fixedMatch.num = structData_roleNumber.currentRoleNumber #fix:这边也要更新！
                        task_fixedMatch.setFixedNumber(structData_roleNumber.currentRoleNumber)
                    # remove ourExistVehicles 操作统一在下一行for循环中进行

        for roleName, task in self.tasks.items():
            if task.fixedNumber >= 0:
                fixedMatch_roles.append(roleName)
                Global.roleNumberStructTable[roleName] = Global.RoleNumberStruct(Global.RoleNumberStruct.MatchType.Fixed, task.fixedNumber)
                if task.fixedNumber in ourExistVehicles:
                    ourExistVehicles.remove(task.fixedNumber)

        
        matchString = self.getMatchString()
        if not matchString or matchString== "":
            matchTactic = [{"mode": "RealTime", "roles": list(self.tasks.keys())}]  # 如果没有指定匹配规则，则默认实时分配所有角色
        else:
            matchTactic = self.DecodeMatchStr(self.getMatchString())

        """
        先做一层滤除，防止：
        1.错误写上的role导致的bug
        2.过滤掉不在任务列表中的角色，或者已经被指定fixedNumber的角色
        """
        realMatchTactic = []
        for matchGroup in matchTactic:
            realMatchGroup = matchGroup.copy()
            realMatchGroup["roles"] = [role for role in matchGroup.get("roles") if
                                       (role in self.tasks.keys()) and (self.tasks[role].fixedNumber < 0)] # 再进行一层滤除，排除已经分配的车号的task
            if realMatchGroup['roles'] == []:
                continue # 由于上面的滤除导致最后roles是空，则不添加到realMatchTactic中
            realMatchTactic.append(realMatchGroup)
            # todo:怎么样保持任务不变？只进行updateTasks更新部分task？
            # matchGroup["roles"] = [role for role in matchGroup.get("roles") if
            #                        (role in self.tasks.keys()) and (self.tasks[role].fixedNumber < 0)]
        matchTactic = realMatchTactic
        
        matchRolesList = []  # 处理[]和{}等匹配规则之后的匹配list，里面包含很多list，每个list是一组roles

        # 遍历所有分配规则，按模式决定是否需要重新分配
        for matchGroup in matchTactic:
            mode = matchGroup.get("mode")
            roles = matchGroup.get("roles")  # 类似["A","B"]这样的list，其实是一组同级别匹配的角色
            # 实时分配、战术切换、状态切换（且模式为Once）时，加入待分配列表
            if mode == "RealTime" or (mode == "Never" and Global.isPlaySwitched) or (isStateSwitched and mode == "Once"):
                matchRolesList.append(roles)
            else:
                # 否则沿用上一次分配结果，并将已分配编号从可用列表移除
                for roleName in roles:
                    # if (self.tasks[roleName].num < 0):
                    #     matchRolesList.append([roleName]) # 这边虽然没有分配车号了，但是仍然加入到matchRolesList中，保持任务的完整性，避免后续逻辑出错
                    #     continue
                    Global.roleNumberStructTable[roleName] = Global.lastRoleNumberStructTable.get(roleName, Global.RoleNumberStruct(Global.RoleNumberStruct.MatchType.Auto, -1))
                    if (Global.roleNumberStructTable[roleName].currentRoleNumber < 0): 
                        matchRolesList.append([roleName]) # 这边虽然没有分配车号了，但是仍然加入到matchRolesList中，保持任务的完整性，避免后续逻辑出错
                        continue
                    assignedVehicle:"int" = Global.getRoleNumber(roleName)
                    if assignedVehicle in ourExistVehicles:
                        ourExistVehicles.remove(assignedVehicle)  # 从可用车辆列表中安全不抛异常地移除已分配的车辆号

        # 对所有需要重新分配的角色组，进行分配
        # note: 这边就是涉及到角色组如何处理的算法了

        canMatchNum = len(ourExistVehicles)  # 统计当前可用机器人数量
        for matchRoles in matchRolesList: # todo:重命名这个matchGroup
            matchRoles_real = []  # 储存真实的应该需要分配的角色，即机器人要足够
            for roleName in matchRoles:
                # 只有可用机器人数量足够时才分配
                if canMatchNum >= 1:
                    matchRoles_real.append(roleName)
                    canMatchNum -= 1
                else:
                    # 没有可分配机器人时，角色编号设为-1
                    Global.roleNumberStructTable[roleName].currentRoleNumber = -1

            # 从self.tasks中提取rolesInSameMatchGroup对应的Task对象，传给munkres_for_tasks
            tasks_to_assign = [self.tasks[roleName] for roleName in matchRoles_real]
            indexes = DoMunkresMatch(tasks_to_assign, ourExistVehicles)  # 运行纯 Munkres 算法分配任务
            # 由indexes写回分配结果
            tasks_Length = len(tasks_to_assign)
            vehicles_Length = len(ourExistVehicles)  # 防止算法返回虚拟车辆进行分配，必须要小于len的index才是算法中有效的结果！
            assignedVehicles = [] # 先暂存下来，然后延迟删除
            for task_index, veh_index in indexes:
                if task_index < tasks_Length and veh_index < vehicles_Length:
                    vehicle_id = ourExistVehicles[veh_index] # 不要和veh_index混用！
                    # 写入task中
                    tasks_to_assign[task_index].munkres_set_num(vehicle_id)
                    assignedVehicles.append(vehicle_id)
                    # 更新Global.roleNumbers表
                    Global.roleNumberStructTable[tasks_to_assign[task_index].roleName].currentRoleNumber = vehicle_id
            
            # 更新ourExistVehicles，canMatchNum只是更新的一方面
            ourExistVehicles = [v for v in ourExistVehicles if v not in assignedVehicles]
        
        # 再根据Global.roleNumbers更新self.tasks中的num字段，bug fix. 因为外界的改动可能使得task.num被改动！
        for roleName, task in self.tasks.items():
            task.num = Global.getRoleNumber(roleName)
        Global.lastRoleNumberStructTable = Global.roleNumberStructTable.copy()

    def run(self, isStateSwitched) -> str:
        """
        ————————run函数的运行先后过程————————
        获取任务（getTasks）、
        （处理matchPos的缓存问题）、
        运行 Munkres 算法分配任务、
        延迟获取任务、
        执行任务、
        延迟获取更新lastMatchPos变量、
        输出调试信息、
        运行transFunction得到将要返回的下一个状态、
        重置munkres算法分配的车号

        注：不支持getTasks自动复用之前状态残留的任务，理由是我认为所有人必须显式指定在做什么，或者显式复用，而不是隐式复用，会导致语义不清和逻辑混乱

        :return: 下一个状态，如果为空则不进行状态切换
        """

        self.tasks = self.getTasks()

        for role, task in self.tasks.items():
            task.roleName = role  # 便于后面更新Global.roleNumbers的操作，这边储存了角色名信息
            if task.needDelayComputingMatchPos:
                task.achedMatchPos = self.achedMatchPos.setdefault(role, self.defaultMatchPos)

        # ————运行munkres算法分配任务（只用到了self.tasks中的matchPos）
        # self.tasks中的num在这函数中被赋值
        self.updateRole(isStateSwitched)

        # ————延迟获取任务
        for _, task in self.tasks.items():
            if task.needDelayComputingMatchPos:  # 这边进行延迟解包
                try:
                    task.skill_cpp, task.matchPos = task.delayedSkill(task.getNum())
                except TypeError:
                    task.skill_cpp, task.matchPos = task.delayedSkill()

        Global.rolePositions = {}
        for role, task in reversed(list(self.tasks.items())):
            # ————执行任务
            if task.getNum() >= 0:
                task.run(task.getNum())  # 加上分配好的num作为第一个参数
                # task.resetNumber()
            else:
                if Global.needDetailedRuntimeDebugInfo:
                    print(
                    f"[State {self.state_name}] Task {task.name}(role: {role}) is not assigned to any vehicle.")

            # ————延迟计算matchPos，通过lastMatchPos缓存上一次的matchPos
            if task.needDelayComputingMatchPos:
                achedMatchPos = task.matchPos(task.getNum())  # 延迟计算这个matchPos的lambda表达式
                # 将achedMatchPos更新到self.achedMatchPos中，便于下一次生命周期内使用（但是Task的生命周期比State短，不能保存住achedMatchPos）
                self.achedMatchPos.setdefault(role, achedMatchPos)
                task.achedMatchPos = achedMatchPos  # 防止transFunction中还要使用，避免逻辑错误

            Global.rolePositions[role] = task.achedMatchPos

        # ————输出调试信息:状态的名称、角色名称
        G.debugEngine.gui_debug_msg(C.CGeoPoint(1000, 3000), "[" + self.state_name + "]", debug_color=0)
        debugPointOffset = C.CVector(50,50)
        for role, task in self.tasks.items():
            if task.getNum() >= 0:
                G.debugEngine.gui_debug_msg(self.playerPos(role) + debugPointOffset, role, debug_color=1)  # 在机器人上面显示角色名称

        # ————运行transFunction得到将要返回的下一个状态
        nextState = self.transFunction()

        # ————重置munkres算法分配的车号，防止下次调用时仍然使用上次munkres算法分配的车号
        # 已弃用，因为每次tasks都是重新创建的，已经更新了
        # for _, task in self.tasks.items():
        #     task.resetNumber()

        return nextState


def declare_state(transFunction: "Callable[[],str]", matchString, tasks):
    """装饰器：用于简洁定义状态类"""

    def decorator(cls):
        class WrappedState(State):
            def getMatchString(self) -> str:
                if callable(matchString):
                    return matchString()
                return matchString

            def getTasks(self) -> "dict[str, Task]":
                if callable(tasks):
                    return tasks()
                return tasks

            def transFunction(self) -> str:
                return transFunction()

            def __init__(self):
                super().__init__(cls.__name__)

        WrappedState.__name__ = cls.__name__
        return WrappedState

    return decorator
