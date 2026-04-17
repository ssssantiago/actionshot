# PyInstaller spec file for ActionShot standalone executable
# Build with: pyinstaller actionshot.spec

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'pynput',
        'pynput.mouse',
        'pynput.keyboard',
        'pynput.mouse._win32',
        'pynput.keyboard._win32',
        'pyautogui',
        'PIL',
        'cv2',
        'pytesseract',
        'comtypes',
        'comtypes.gen',
        'pywinauto',
        'pystray',
        'anthropic',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ActionShot',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=None,
)
