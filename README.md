# mark_i — SRC 初赛 2.32 动态角色分配版

保存于 2026-10-18，对应运行标识 `COMBO 2.32 DYNAMIC-ROLES` / 日志 `combo_2.32_dynamic_roles`。

## 当前策略

- A：取球、第一传、跑射门点、接回传射门。
- B：接第一传、转向、等待 A 到位、回传。
- 使用官方 Munkres 从有效蓝方车辆自动分配角色，`{AB}` 在同一 Play 内保持身份；一轮重试不交换职责。
- 暂停后重新进入进攻 Play 时重新匹配并清空旧进攻状态。车辆不足时停止等待。
- 黄方练习守门员使用现成 `Goalie`。
- 保留 SimpleGoTo、既有传射流程、力度、恢复及禁区保护。
- 当前点位：接应 `(4200,-1500)`，射门 `(3200,1400)`，回传瞄点 `(3270,1330)`，单位毫米。

## 仓库布局及 Windows 启动

仓库根目录就是运行包的 **ZBin**，`PythonScripts` 与 `Client.exe` 同级。保留仓库原有 Windows 运行库及 macOS 脚本；本版本的实际验证平台为 Windows。

1. 使用 Python **3.12.10 x64**。在 `PythonScripts` 内按 `pyproject.toml`、`uv.lock` 建立依赖环境：安装 uv 后执行 `uv sync --frozen --python 3.12.10`。也可复制现有 Python312 解释器到仓库根目录的 `Python312`，然后在新位置重新创建 `.venv`，不要复用其他目录的虚拟环境。
2. 运行根目录 `use_combo_full.cmd`，再用 `start_client_windows.cmd` 启动 Client。启动脚本会在存在本地 Python312 时设置该进程的 PYTHONHOME。
3. 在 Client 接通仿真和视觉，启动裁判发送并按 **Halt**。需要摆初始练习场景时运行 `reset_scene.cmd`。
4. 启动黄方练习守门员和蓝方策略，按 **Stop Game → Force Start** 开始。
5. 修改 Python 后停止并重新启动策略。人工摆球使用 **Halt**；Stop Game 会执行退球站位，不是原地保持。不要关闭裁判发送代替 Halt。

`reset_scene.cmd` 是本地 0/1 号蓝车和 0 号黄车的练习摆位工具，不代表战术写死这些编号。换车号测试时在 Client 摆放实际车辆，再重开 Play。

比赛颜色和场地半场以现场为准；当前配置是蓝方进攻、黄方练习守门。未确认的“随机复位两个对象”裁判流程尚未新增适配。

## 已有验证

- 动态分配版检查：205 项通过，0 失败，0 错误；这是该版之前完成的离线测试，详见 `verification/v2.32/verification.json` 和 `test_results.txt`。
- 2026-10-18 的 0805 录像：Force Start 后连续 180 秒，10 次实际射门、8 进、2 偏出，转化率 80%；另一次最后接球未出射，随后自动恢复。不是官方裁判计分记录，也不是所有场景的成功率保证。
- 本次上传逐文件比对当前运行目录并保存 SHA256 清单，核心策略没有为上传改动。

本机 Python 环境、运行日志、录像、历史备份不入库。现有可执行文件与 DLL 留在仓库，换机器需要自行准备 Python 依赖。新位置的完整启动仍需在目标机器验证。
