# 这边类比之前lua层的StartZeus.lua和Zeus.lua，随Decision.cpp中的单例的初始化进行第一次的全局初始化
"""
C++层的执行顺序
Decision类初始化的时候：
    eval file: InitAllModules.py
    import SelectPlay.py
每一帧调用SelectPlay.py中的SelectPlay()
"""

import os
import sys
from pathlib import Path
# 当前脚本 所在路径
current_file_path = Path(__file__).resolve() # 即ZBin/PythonScripts/InitAllModules.py，含有后缀名！

# 构造 dll 所在目录路径
dll_path = current_file_path.parent.parent # 即ZBin/

if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(str(dll_path))
# import site
# site.addsitedir(str(current_file_path / ".venv" / "Lib" / "site-packages"))
sys.path.append(str(current_file_path.parent / ".venv" / "Lib" / "site-packages"))  # 将当前目录添加到搜索路径
print(sys.path)
# 将下面的全部解注释即可以强制debug，以定位到import Global中的错误
# ========================强制debug专用语句==========================
# import debugpy 
# print("==== BEFORE LISTEN ====")
# debugpy.listen(5678,in_process_debug_adapter=True) #一定要加in_process_debug_adapter=True才能让vs code监听成功处于待连接的状态，这边的端口号和launch.json中的一致
# print("==== AFTER LISTEN ====")
# debugpy.wait_for_client()
# print("Debugging!")
# debugpy.breakpoint() #会在此处停下
# ========================end 强制debug专用语句==========================
try:
    import CppPackage
    import Global
    Global.read_config_file("zss.ini")
    print(f"启动参数:")
    print(f"  isSimulation: {Global.isSimulation}")
    print(f"  isYellow: {Global.isYellow}")
    print(f"  isRight: {Global.isRight}")
    if Global.isDebugMode:
        import debugpy
        print("==== BEFORE LISTEN ====")
        debugpy.listen(5678,
                       in_process_debug_adapter=True)
        print("==== AFTER LISTEN ====")
        debugpy.wait_for_client()
        print("Debugging!")
        debugpy.breakpoint()  # 会在此处停下
    import Geometry
    import Vision
    import WorldModel
    import Utils
    import Config #如果上面的import中报错，则需要启用上面的强制debug来进一步定位错误
    import SelectPlay

except ImportError as e:
    print(f"Error while importing module: {e}")
    import traceback
    traceback.print_exc()
    raise

