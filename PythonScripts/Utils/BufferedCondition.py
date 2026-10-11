from typing import overload, Optional, Union
import CppPackage
import Global

class BufferedTimer:
    """
    封装基于 vision.getCycle() 的缓冲计数器。
    tick 返回 True 表示条件满足（连续满足 buffer_frame 帧或达到 max_count 超时）。
    """
    def __init__(self):
        self.last_cycle: int = -1
        self.consec_count: int = 0
        self.total_count: int = 0

    def tick(self, condition: bool, buffer_frame: int, max_count: int, current_cycle: int) -> bool:
        # 仅在检测到新的 cycle 时计数一次（避免单 cycle 内重复调用被多次计数）
        if current_cycle != self.last_cycle: # 来了新的视觉帧，排除视觉或者程序暂停期间
            self.last_cycle = current_cycle
            if condition:
                self.consec_count += 1
            else:
                self.consec_count = 0
            self.total_count += 1
        # 条件成立：连续达到 buffer_frame，或达到了 max_count（超时）
        result = (self.consec_count >= buffer_frame) or (self.total_count >= max_count)
        if result:
            self.reset() # 条件满足了，此时重置计时器
        return result
    
    def reset(self):
        self.last_cycle = -1
        self.consec_count = 0
        self.total_count = 0

# 模块级注册表（强引用），便于通过 id 使用 timer；如需自动回收可换成 weakref.WeakValueDictionary
_timers: dict[str, BufferedTimer] = {}

def get_or_create_timer(timer_id: str) -> BufferedTimer:
    if timer_id not in _timers:
        _timers[timer_id] = BufferedTimer()
    return _timers[timer_id]

def del_timer(timer_id: str) -> None:
    _timers.pop(timer_id, None)

def reset_all_timers() -> None:
    """
    重置注册表中所有 BufferedTimer（逐个调用 reset）。
    建议在赛局切换或需要统一清空所有缓冲状态时调用。
    """
    for t in list(_timers.values()):
        try:
            t.reset()
        except Exception:
            # 防御性：忽略单个 timer 重置错误，继续重置其他 timer
            pass

def buffered_condition(condition: bool, buffer: Union[int, str], max_count: int = 99999,
                       timer: Optional[Union[str, BufferedTimer]] = None) -> bool:
    """
    Args:
        condition: 当前条件（布尔）
        buffer: 缓冲帧数或预设字符串 'fast'/'normal'/'slow'
        max_count: 最大检测帧数（超时阈值）
        timer: BufferedTimer 实例或 timer_id 字符串；若为 None 使用模块默认计时器 "_default"
    Returns:
        bool: 条件是否被判定为满足
    """
    # 解析 buffer
    if isinstance(buffer, str):
        match buffer:
            case "normal":
                buffer_frame = 6
            case "slow":
                buffer_frame = 10
            case "fast":
                buffer_frame = 1
            case _:
                raise ValueError(f"Unknown buffer size: {buffer}")
    elif isinstance(buffer, int):
        buffer_frame = buffer
    else:
        raise TypeError(f"buffer must be int or str, got {type(buffer)}")

    # 选择计时器
    if timer is None:
        timer_obj = get_or_create_timer("_default")
    elif isinstance(timer, str):
        timer_obj = get_or_create_timer(timer)
    elif isinstance(timer, BufferedTimer):
        timer_obj = timer
    else:
        raise TypeError("timer must be None, str (timer_id) or BufferedTimer instance")

    # 获取视觉周期
    try:
        from Vision import vision
        current_cycle = vision.getCycle()
    except Exception:
        # 容错：若 vision 不可用，视为每次都启动新周期（可根据需求调整）
        current_cycle = -1

    return timer_obj.tick(condition, buffer_frame, max_count, current_cycle)