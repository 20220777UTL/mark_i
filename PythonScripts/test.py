import sys
import os
from pathlib import Path


extend_dir = Path.cwd() / "PythonScripts"
sys.path.extend([str(extend_dir)])

import CppPackage as C

systemRunner = C.SystemRunner.Instance()
systemRunner.init() # 如果没有连接视觉信息，则会在这边卡住，等待视觉信息

import InitAllModules
import Vision
from Vision import vision
while True:
    systemRunner.preDecision()
    print(vision.getCycle())
    systemRunner.postDecision()


"""
todo: 修改ZSS::ParaManager::的配置文件读取目录，使得能够从Python层启动的Python.exe能够进行调试开发！
思考getCycle的含义！
"""