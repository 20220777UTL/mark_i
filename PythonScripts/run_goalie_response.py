"""Run the isolated GoalieOnly response experiment without editing Config.py."""
import builtins
import sys
from pathlib import Path


_original_import = builtins.__import__
_strategy_injected = False


def _install_test_strategy(name, globals=None, locals=None, fromlist=(), level=0):
    global _strategy_injected
    imported = _original_import(name, globals, locals, fromlist, level)
    if name == "SelectPlay" and not _strategy_injected:
        # InitAllModules has loaded Config and the vision/world-model modules by
        # this point. Inject before the first strategy frame without editing it.
        import Config
        from Play.Test.TestGoalieResponse import TestGoalieResponse

        Config.testStrategy = Config.GameStrategy(TestGoalieResponse())
        _strategy_injected = True
        print("[GoalieResponse] Injected temporary strategy; Config.py is untouched.", flush=True)
    return imported


def main():
    ini_path = Path.cwd() / "zss.ini"
    original_ini = ini_path.read_bytes() if ini_path.is_file() else None
    builtins.__import__ = _install_test_strategy
    try:
        import main as strategy_main
        strategy_main.main()
    finally:
        builtins.__import__ = _original_import
        # Also restore on Python-level interruption or exceptions. The PS
        # launcher performs the same byte-for-byte restore after normal exit.
        if original_ini is not None:
            ini_path.write_bytes(original_ini)


if __name__ == "__main__":
    main()
