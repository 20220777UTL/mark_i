from munkres import Munkres

import Vision
from RoleMatch_LuaStyle.Task import Task
from Vision import Player


def cost_matrix(tasks: list[Task], vehicles: list[int]):
    """行=任务，列=车辆；cost[i][j] = 车辆 j 执行任务 i 的代价"""
    matrix = []
    for t in tasks:
        row = []
        for v in vehicles:
            dist = Vision.Player.ourPlayer(v).Pos().dist(t.getMatchPos(v))
            row.append(dist)
            # row.append(int(round(dist)))  # 转为整数，防止后面的类型错误
        matrix.append(row)
    return matrix


def munkres_for_tasks(tasks: list[Task]) -> list[Task]:
    """对未分配(num < 0) 的任务做 Munkres 分配；已分配的任务直接跳过"""
    vehicles_all = Player.getAllValidNumbers()
    if not vehicles_all or not tasks:
        return tasks

    # 已经固定了车号的任务
    fixed_tasks = [t for t in tasks if t.num >= 0]
    # 需要分配的任务
    free_tasks = [t for t in tasks if t.num < 0]

    # 被固定任务占用掉的车辆（如果这些车仍是有效车）
    used_vehicles = {t.num for t in fixed_tasks if t.num in vehicles_all}
    vehicles_free = [v for v in vehicles_all if v not in used_vehicles]

    # 没有需要分配的任务或没有可用车辆
    if not free_tasks or not vehicles_free:
        return tasks

    # 生成代价矩阵并执行匹配（行=free_tasks, 列=vehicles_free）
    cost = cost_matrix(free_tasks, vehicles_free)
    m = Munkres()
    indexes = m.compute(cost)

    # 写回分配结果
    for task_idx, veh_idx in indexes:
        if task_idx < len(free_tasks) and veh_idx < len(vehicles_free):
            free_tasks[task_idx].munkres_set_num(vehicles_free[veh_idx])

    return tasks

def DoMunkresMatch(freeTasks: list[Task], freeVehicles):
    if not freeVehicles or not freeTasks:
        return freeTasks

    # 生成代价矩阵并执行匹配（行=freeTasks, 列=vehicles_free）
    cost = cost_matrix(freeTasks, freeVehicles)
    m = Munkres()
    indexes = m.compute(cost)

    return indexes


