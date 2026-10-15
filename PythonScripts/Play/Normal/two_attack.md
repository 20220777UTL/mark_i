# two_attack 操作与标定

0 号主攻、1 号接应。状态为 `FirstPass → PassBack → Shoot → FollowShot`；
场内回弹按远近回到 `PassBack` 或 `Shoot`，进球或整颗球出界进入 `Done`。
重新选择 Play 会清空这一轮的目标、出球记录和持球计时。

## 默认行为

- `Global.isSimulation` 来自当前启动配置。仿真不调用红外；真机持球要求红外持续确认，
  视觉只做粗略矛盾检查，不再要求球落在旧的 65–90 mm / ±10 mm 窗口内。
- 持球确认使用真实时间（默认 40 ms），且需要新的有效视觉帧。机器人或球丢失、
  非有限数值、红外接口异常时停止移动和出球；真机红外仍开启时保留吸球。
- 普通平传、射门和挑传都经过 `evalPower`。策略没有自己的力度映射，
  全局与曲线的力度上限继续有效；力度值不等于球速。
- 所有移动共用场地、禁区、制动及带球里程约束。门将选择仍按实测 0 号门将位置。
- 不使用固定出球速度、来球保留系数或摩擦模型预测“必然射中”。只有已经对准、
  处于球口、落地且横向速度很小的来球才尝试一脚射；其他来球先收稳再射。
  这些控制容差仍须用真机验收，不能当作已证明的硬件能力。

**仓库没有有效的真机挑传标定，因此当前默认回传是平传。**
独立的 chip 曲线已经存在，但其落点含义和环境未获验证，代码不会自动把它当成准确标定。

## 挑传配置

编辑运行目录的 `data/two_attack_calibration.json`，重选 Play 后生效。
`simulation` 与 `real` 必须分别填写，不能复制仿真结果冒充真机实测。

| 字段 | 含义 |
| --- | --- |
| `mouth_offsets_mm` | 每台车车心至球口处球心的实测距离；真机缺省使用 `playerFrontToCenter + BALL_RADIUS`，只是初值。仿真的 82 mm 来自已有仿真记录。 |
| `chip.calibrated` | 该环境的挑传曲线、落地提前量和适用距离已验证后才设为 true。 |
| `chip.sender` | 当前回传者必须为 1；其他机器人不能复用这个标定。 |
| `chip.distance_reference` | 必须为 `first_landing`，曲线的距离指第一次落地，不能是最终停球距离。 |
| `chip.observation_verified` | 已验证该运行环境的三维位置和落地反馈可以连续区分腾空与落地。 |
| `chip.min_distance_mm` / `max_distance_mm` | 出球位置到第一落点的已验证距离范围。 |
| `chip.landing_lead_mm` | 第一落点到预计接射触点的距离，方向沿来球方向；只适用于上述距离范围。 |
| `chip.curve_fingerprint` | 对实际 chip 曲线、曲线限制和 `Global.powerMax` 的指纹；其中任意一项改变，需要重新核验。 |

以 `P` 为触球点、`G` 为门内射门目标、`B` 为接应者当前出球位置：

```text
主射手车心 R = P - mouth_offset * unit(G - P)
第一落点   L = P - landing_lead * unit(P - B)
```

挑传力度调用 `evalPower(B, L, P.NORMAL, is_chip=True)`，下发 `setChipKick`。
回传前根据实际 B 更新 L；发出命令时锁定 L、P、R、G。本次球路中不会为了跟随门将
不断旋转主射手、同时改变球口触点。落点偏差通过落地后的实测球路处理。

曲线未标定、落点反馈不可用、超出标定范围或落点非法时回退平传，并打印 `return_mode` 原因。
没有有效观测时不能通过单纯延时断言球已落地。已知腾空球只保持接应位置；
必须先看到腾空，再看到持续有效低高度，或由真机主射手球口红外确认接触，才恢复接球/接射。
反馈一直缺失且红外也没有接触时保持等待，恢复观测或重选 Play 后再继续。
如果出球命令丢失，等待超过重试间隔且新观测确认球仍在接应者球口时，取消该次挑传并重新确认持球；
不能仅因等待超时就把空中球当成已落地。

## 接口事实与限制

| 接口 | 本策略中的用途 |
| --- | --- |
| `Player.isInfraredOn` / `infraredOn` | 同一红外信号的两个名字。真机持球依据；本地历史仿真可调用但曾连续 1740 帧为假。 |
| `infraredCount` / `infraredOffCount` | 可选诊断；持续时间由本策略按新帧和时钟计算，不假定原生计数的帧率。 |
| `kickBall` / `isBallKicked` | 封装注释表示命令状态，不能证明实际踢出；不参与释放判断。 |
| `kickBallVision`、`BallStatus.IsBallKickedOut`、`getBallPossession` | 只记录诊断，不将未经核实的底层语义作为核心条件。 |
| `BestChipPredictPos` / `ChipBallState` / `ChipRestFlyTime` / `RealPos` | 每帧读取的可选反馈；预测点只记录，不驱动车追逐空中二维投影。 |

当前仓库只有编译库和接口声明，没有这些原生算法或无线反馈的实现源码。
无法仅凭 Python 接口存在确认其在某台真机上有效，也没有独立的红外通信时间戳可判断旧信号。
`RealPos` 按 mm 读取，XY 必须与当前有效球观测一致；全零 XYZ、非有限值和明显陈旧位置无效。
单独的 `ChipBallState=False`、剩余时间 0 或默认落点 (0,0) 均不算落地证明。
真实 XY 配合高度 0 可以表示地面；原点全零仍按未知处理。

## 记录与核验

在启动策略的进程中设置 `SRC_TWO_ATTACK_TELEMETRY` 为可写 JSONL 文件路径。
记录会附带环境、帧号、持球、红外诊断、球位置速度、原生挑球反馈及挑传事件。
未设置时只打印状态、回退原因、有效出球和结果事件。

从 `mark_i` 目录运行以下只读工具：

```powershell
python PythonScripts/tools/two_attack_diagnostics.py fingerprint data/power_curve/active_curve.json --power-max 12700
python PythonScripts/tools/two_attack_diagnostics.py report LOG/two_attack.jsonl
```

`--power-max` 必须使用运行时真实的 `Global.powerMax`，不是另设一个力度。
指纹工具只打印结果，不会激活挑传或修改曲线。

标定步骤：

1. 分别在仿真、真机用现有挑球测试技能采集 1 号车的力度与第一落点；确认原生高度和落地状态
   确实变化。此步骤不能由当前未标定的自动回传代替，也不要仅为绕过检查而把配置置为 true。
2. 用实际测试数据编辑已有 chip Normal 曲线；测量落地后到适合接射速度时的前进距离。
   为能共享同一提前量的距离区间填写范围与 `landing_lead_mm`，超出范围保持回退。
3. 填写该环境的观测验证、曲线指纹和实测参数，再启用 `calibrated`，重选 Play。
4. 观察多次自动回传的落点误差、飞行时间、落地后前进距离和触球速度。诊断工具保留中断/
   不完整试次；第一次低高度采样是观测近似，不能用丢帧或弹跳后的采样冒充准确第一落点。
5. 真机单独检查红外遮挡与抖动、不同起点/距离、回传偏差、收稳降级、补射和出界。
   离线测试和仿真成功不等于真机验收。

## 自动检查

从 `PythonScripts` 运行 `python -m unittest discover -s tests -q`。
测试包括真实状态机调度顺序、两种回传的完整流程、红外与失效观测、挑传落点与命令、
飞行中反馈缺失、回弹/出界，以及改变减速、采样延迟、起点与噪声的离线轨迹回放。
离线回放检验命令约束，不测量 grSim 或真实机器人的进球率。
