import argparse
import configparser
import os
from pathlib import Path
import CppPackage as C
import Global
from Global import CaseSensitiveConfigParser
import os
def _update_config_file(args):
    """更新配置文件中的参数"""

    # 获取当前工作目录的父目录下的zss.ini
    # config_file = Path.cwd().parent / "zss.ini"
    config_file = "zss.ini"

    # 创建配置解析器
    config = CaseSensitiveConfigParser()

    # 如果配置文件存在则读取，否则创建新文件
    if os.path.exists(config_file):
        config.read(config_file, encoding='utf-8')
    
    # 确保必要的section存在
    if 'ZAlert' not in config:
        config['ZAlert'] = {}
    if 'Alert' not in config:
        config['Alert'] = {}
    
    # 更新配置项

    # is-simulation参数
    if args.simulation:
        config['Alert']['IsSimulation'] = str(args.simulation).lower()

    # team参数: blue->false, yellow->true
    if args.team:
        is_yellow = str(args.team.lower() == 'yellow').lower()
        config['ZAlert']['IsYellow'] = is_yellow
    
    # positive-side参数: right->true, left->false
    if args.positive_side:
        is_right = str(args.positive_side.lower() == 'right').lower()
        config['ZAlert']['IsRight'] = is_right

    # 写入配置文件，便于后续C++层调用的时候共享这个状态
    with open(config_file, 'w', encoding='utf-8') as f:
        config.write(f)
    # Global.read_config_file(config_file) # 改成InitAllModules统一读取
    # print(f"启动参数:")
    # print(f"  isSimulation: {Global.isSimulation}")
    # print(f"  isYellow: {Global.isYellow}")
    # print(f"  isRight: {Global.isRight}")


def _parse_args():
    parser = argparse.ArgumentParser(description="从Python层自由启动C++")
    # is-simulation参数，布尔类型
    parser.add_argument("--simulation", "--sim",
                        action="store_true",
                        help="是否为仿真模式，默认为false")

    # team参数，只能是blue或yellow
    parser.add_argument("--team", "-t", 
                       choices=["blue", "yellow"],
                       required=False,
                       help="队伍颜色，可选值: blue, yellow")
    
    # positive-side参数，只能是right或left
    parser.add_argument("--positive-side", "-s", "--side",
                       choices=["right", "left"],
                       required=False,
                       help="坐标为正数的场地方向，可选值: right, left")
    
    parser.add_argument("--test-mode", "--test",
                        action="store_true",
                        help="是否为测试模式，默认为false")
    
    parser.add_argument("--test-function", "--test-func",
                        action="store_true",
                        help="是否为测试模式，默认为false")
    
    return parser.parse_args()

def test():
    from Vision import vision
    print(vision.getCycle())

def main():
    args = _parse_args()
    
    # 打印参数信息
    print(f"=========正在从Python启动C++！=========")

    # 更新配置文件
    _update_config_file(args)

    # 在这里可以调用C++模块进行初始化

    print(f"========================================")
    print(f"当前 Python 进程 PID: {os.getpid()}")
    print(f"========================================")
    systemRunner = C.SystemRunner.Instance()
    print("[INFO] 正在进行C++模块初始化，请确保视觉信息已连接，否则将在这一步阻塞；请确保从ZBin目录下启动")
    systemRunner.init() # 如果没有连接视觉信息，则会在这边卡住，等待视觉信息
    print("[INFO] 初始化完成，开始运行C++模块")
    try:
        import InitAllModules
        import SelectPlay
        while True:
            systemRunner.preDecision()
            # 注意：频繁 import 模块通常不是好习惯，建议放在循环外
            if args.test_mode:
                Global.isTestMode = True
            if args.test_function:
                test()
            else:
                SelectPlay.SelectPlay()
            systemRunner.postDecision()
    except KeyboardInterrupt: # 使用ctrl+C退出
        print("\n[INFO] 检测到键盘中断信号，正在退出...")
    # except Exception as e:
    #     print(f"[ERROR] 运行时错误: {e}")
    finally:
        # 这里可以做一些清理工作，比如停止 C++ 引擎
        print("[INFO] 程序已停止")

if __name__ == '__main__':
    main()
    """
    必须从ZBin目录启动！
    启动方式：先激活虚拟环境，然后在ZBin目录下运行python PythonScripts/ main.py 然后添加一些参数以启动
    示例：
        python PythonScripts/main.py --sim --team blue --side left
        python PythonScripts/main.py -t blue -s left
    """