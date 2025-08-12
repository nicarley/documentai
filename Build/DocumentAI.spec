# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import copy_metadata

datas = [('C:\\Users\\admin7\\OneDrive - Americana Building Products\\Projects\\documentai/resources', 'resources/'), ('C:\\Users\\admin7\\OneDrive - Americana Building Products\\Projects\\documentai/ai_chatbot_app', 'ai_chatbot_app/'), ('C:\\Users\\admin7\\OneDrive - Americana Building Products\\Projects\\documentai/faiss_index', 'faiss_index/'), ('C:\\Users\\admin7\\OneDrive - Americana Building Products\\Projects\\documentai/AIDocs', 'AIDocs/')]
hiddenimports = []
datas += collect_data_files('pydantic')
datas += copy_metadata('pydantic')
datas += copy_metadata('langchain')
datas += copy_metadata('langchain-core')
datas += copy_metadata('langchain-ollama')
hiddenimports += collect_submodules('pydantic')
hiddenimports += collect_submodules('pydantic.deprecated')
hiddenimports += collect_submodules('langchain_core')
hiddenimports += collect_submodules('langchain_ollama')


a = Analysis(
    ['C:\\Users\\admin7\\OneDrive - Americana Building Products\\Projects\\documentai\\documentai.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DocumentAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\admin7\\OneDrive - Americana Building Products\\Projects\\documentai\\resources\\documentai.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DocumentAI',
)
