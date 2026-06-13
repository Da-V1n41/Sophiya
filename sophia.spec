# sophia.spec — PyInstaller spec для Sophia voice assistant
# Збірка: pyinstaller sophia.spec

import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Шляхи
project_dir = os.path.abspath('.')
ctk_dir = r'C:\Users\Andriy\AppData\Local\Programs\Python\Python312\Lib\site-packages\customtkinter'

datas = [
    # CustomTkinter — теми та шрифти (обов'язково)
    (ctk_dir, 'customtkinter'),

    # Vosk модель офлайн розпізнавання
    (os.path.join(project_dir, 'vosk-model-uk'), 'vosk-model-uk'),

    # Дані проєкту
    (os.path.join(project_dir, 'dataset.json'),  '.'),
    (os.path.join(project_dir, 'aliases.json'),  '.'),
    (os.path.join(project_dir, 'words.py'),      '.'),
    (os.path.join(project_dir, 'icon.ico'),      '.'),

    # Chrome розширення (для browser_bridge)
    (os.path.join(project_dir, 'chrome_extension'), 'chrome_extension'),
]

# Додаткові приховані імпорти (PyInstaller може пропустити)
hiddenimports = [
    # sklearn
    'sklearn.utils._typedefs',
    'sklearn.utils._heap',
    'sklearn.utils._sorting',
    'sklearn.utils._vector_sentinel',
    'sklearn.neighbors._dist_metrics',
    'sklearn.tree._utils',
    'sklearn.utils._cython_blas',
    'sklearn.utils.sparsefuncs_fast',
    # comtypes (використовується voice.py для Windows COM)
    'comtypes',
    'comtypes.client',
    'comtypes.server',
    # pystray системний трей
    'pystray._win32',
    # PIL
    'PIL._tkinter_finder',
    # sounddevice
    'sounddevice',
    # інше
    'websockets',
    'websockets.legacy',
    'websockets.legacy.server',
    'websockets.legacy.client',
    'plyer.platforms.win.notification',
]

a = Analysis(
    ['main.py'],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Виключаємо непотрібні важкі модулі
        'matplotlib',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'setuptools',
        'docutils',
        'sphinx',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Sophia',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,          # без чорного вікна консолі
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(project_dir, 'icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Sophia',          # → dist/Sophia/
)
