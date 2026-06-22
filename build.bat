@echo off
chcp 65001 >nul
rem === 設計図素材変換ツール  exe ビルドスクリプト ===
rem 必要: Python 3.10+ がインストール済みであること

cd /d "%~dp0"

echo [1/3] 依存ライブラリをインストールします...
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo 依存関係のインストールに失敗しました。
    pause
    exit /b 1
)

echo [2/3] PyInstaller で exe を作成します...
rem PyInstaller には ASCII 名を渡し、後で日本語名にリネームする（文字化け回避）
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name SchematicMaterialConverter ^
    --collect-all tkinterdnd2 ^
    --collect-all pyglet ^
    --exclude-module psutil ^
    --exclude-module charset_normalizer ^
    --add-data "data;data" ^
    app.py
if errorlevel 1 (
    echo ビルドに失敗しました。
    pause
    exit /b 1
)

echo [3/3] exe を「設計図素材変換ツール.exe」にリネームします...
copy /Y "dist\SchematicMaterialConverter.exe" "dist\設計図素材変換ツール.exe" >nul

echo.
echo === 完了 ===
echo 出力: %~dp0dist\設計図素材変換ツール.exe
echo このexeに .litematic をドラッグ&ドロップするか、ダブルクリックで起動できます。
pause
