# mark_i

A working copy of the SRC `ZBin` runtime and Python strategy project.

The Windows runtime files (`.exe` and `.dll`) are retained. Local Python environments, logs, debug symbols, and macOS-native build artifacts are excluded from version control. Recreate Python dependencies from `PythonScripts/pyproject.toml` and `PythonScripts/uv.lock` on the target environment.