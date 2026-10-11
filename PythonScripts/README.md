# Falcon Python strategy

The Python strategy layer is launched from `ZBin` and uses the pybind11 module generated at `ZBin/PythonScripts/CppPackage/CppPackage.pyd`.

## 校内赛策略入口

从 `ZBin` 目录启动 `PythonScripts/main.py`。本包中的策略文件是空占位：可以导入、响应裁判指令并逐帧运行，但不会给机器人下发任务。

- `Play/Normal/ExampleNormal.py`：常规比赛策略，在 `getTasks()` 中填写任务。
- `Play/RefPlay/ExampleRef.py`：裁判指令策略。需要不同指令执行不同内容时，复制为独立文件，并在 `Config.py` 中为对应 key 注册策略实例。
- `Play/Test/ExampleTest.py`：`--test` 模式的策略。
- `Config.py`：蓝黄队和裁判指令到策略实例的对应关系。保留现有 key；可按需为蓝黄队提供不同实例。

每个示例的 `getTasks()` 当前返回空字典；填写任务时使用 `RoleMatch_LuaStyle.Task.Task` 和 `RoleMatch_LuaStyle.Skills` 中的接口。`getMatchString()` 留空表示使用默认实时匹配，`transFunction()` 留空表示保持当前状态。运行例子：

```powershell
cd ZBin
PythonScripts/.venv/Scripts/python.exe PythonScripts/main.py --sim --team blue --side left
```

启动时 `SystemRunner.init()` 会等待视觉信息连接；裁判盒/视觉环境就绪后进入逐帧循环。当前占位策略不会主动控制机器人。

## Environment

```powershell
cd ZBin/PythonScripts
uv sync --locked
```

The project currently targets Python 3.12.10. Keep `pyproject.toml` and `uv.lock` in sync when dependencies change.

## Build integration

The root CMake build generates `CppPackage.pyd` and its `.pyi` stub, then places them in `ZBin/PythonScripts/CppPackage`. Run Python entry points with `ZBin` as the working directory so `zss.ini`, native DLLs, and strategy data resolve consistently.

## Power-curve editor

```powershell
cd ZBin
PythonScripts/.venv/Scripts/python.exe PythonScripts/tools/power_curve_editor.py
```

The editor and runtime share `ZBin/data/power_curve/active_curve.json` through `PowerCurveBackend.py`.
