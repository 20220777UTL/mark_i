"""Prepare the next Client Medusa launch for the other simulated team.

This Client binary starts both direction buttons with the same bare Medusa.exe
command. Medusa reads the shared zss.ini only when it starts. After blue has
loaded its own settings, stage yellow/right for the next click; after yellow
has loaded, restore blue/left. Keep every other byte of the user's INI file.
"""
import os
import re
from pathlib import Path


def stage_next_team(config_path, current_yellow):
    path = Path(config_path)
    original = path.read_bytes()
    section = re.search(rb'(?ms)^\[ZAlert\][ \t]*\r?\n(.*?)(?=^\[|\Z)', original)
    if section is None:
        raise ValueError('zss.ini has no [ZAlert] section')
    block = section.group(1)
    next_value = b'false' if current_yellow else b'true'
    for key in (b'IsYellow', b'IsRight'):
        pattern = rb'(?m)^' + key + rb'=(?:true|false)(?=\r?$)'
        block, count = re.subn(pattern, key + b'=' + next_value, block, count=1)
        if count != 1:
            raise ValueError(f'zss.ini lacks a boolean {key.decode()} entry')
    updated = original[:section.start(1)] + block + original[section.end(1):]
    if updated == original:
        return
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    try:
        temporary.write_bytes(updated)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
