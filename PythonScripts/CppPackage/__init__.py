import os
import sys
import importlib
from pathlib import Path
# __init__.py 所在路径
_current_file_path = Path(__file__).resolve()

# 构造 dll 所在目录路径
_dll_path = _current_file_path.parent.parent.parent # 即ZBin/

if hasattr(os, "add_dll_directory"):
    _dll_directory_handle = os.add_dll_directory(str(_dll_path))
    
# 添加 DLL 路径（Python ≥ 3.8）
# if hasattr(os, "add_dll_directory"):
#     os.add_dll_directory(os.path.abspath(os.path.dirname(__file__)))
# os.add_dll_directory(r"D:\Documents\SRCrobocup\MilkForPython\ZBin")
from .CppPackage import *
# # 动态加载 pyd 模块，替换当前模块的符号
# _cpp = importlib.import_module("CppPackage")  # 注意：不是 .CppPackage，否则嵌套了！

# # 把 _cpp 的所有符号导入当前模块
# globals().update({k: getattr(_cpp, k) for k in dir(_cpp) if not k.startswith("_")})
# del _cpp
