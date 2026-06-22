$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Dist = Join-Path $Root "dist"
$InstallerDir = Join-Path $Root "installer"
$BuildRoot = Join-Path $env:TEMP "SchematicMaterialConverterInstallerBuild"
$PackageDir = Join-Path $BuildRoot "package"
$Exe = Get-ChildItem -LiteralPath $Dist -Filter "*.exe" |
    Where-Object { $_.Name -notmatch "Setup" } |
    Sort-Object LastWriteTime |
    Select-Object -Last 1
$FinalInstaller = Join-Path $Dist "SchematicMaterialConverter_Setup.exe"
$Stub = Join-Path $InstallerDir "installer_stub.py"
$VideoAsset = Join-Path $InstallerDir "installer_video.mp4"
$MenuAudioAsset = Join-Path $InstallerDir "installer_menu_bgm.mp3"
$ManagerBgAsset = Join-Path $InstallerDir "installer_manager_bg.png"
$InstallBgAsset = Join-Path $InstallerDir "installer_install_bg.png"

if ($null -eq $Exe -or -not (Test-Path -LiteralPath $Exe.FullName)) {
    throw "Missing app exe in $Dist. Build it first."
}
foreach ($Asset in @($VideoAsset, $MenuAudioAsset, $ManagerBgAsset, $InstallBgAsset)) {
    if (-not (Test-Path -LiteralPath $Asset)) {
        throw "Missing installer asset: $Asset"
    }
}

if (Test-Path -LiteralPath $BuildRoot) {
    $resolvedBuildRoot = (Resolve-Path -LiteralPath $BuildRoot).Path
    if (-not $resolvedBuildRoot.StartsWith($env:TEMP, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to remove unexpected build root: $resolvedBuildRoot"
    }
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null

Copy-Item -LiteralPath $Exe.FullName -Destination (Join-Path $PackageDir "payload.exe") -Force

Remove-Item -LiteralPath $FinalInstaller -Force -ErrorAction SilentlyContinue

python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name SchematicMaterialConverter_Setup `
    --distpath $Dist `
    --workpath (Join-Path $BuildRoot "pyinstaller-build") `
    --specpath $BuildRoot `
    --exclude-module numpy `
    --exclude-module psutil `
    --exclude-module charset_normalizer `
    --add-data "$PackageDir\payload.exe;." `
    --add-data "$VideoAsset;." `
    --add-data "$MenuAudioAsset;." `
    --add-data "$ManagerBgAsset;." `
    --add-data "$InstallBgAsset;." `
    $Stub
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}
if (-not (Test-Path -LiteralPath $FinalInstaller)) {
    throw "Installer was not created: $FinalInstaller"
}

$CopyHelper = Join-Path $BuildRoot "copy_setup.py"
Set-Content -LiteralPath $CopyHelper -Encoding ASCII -Value @"
import pathlib
import shutil
import sys

src = pathlib.Path(sys.argv[1])
dst = src.parent / "\u8a2d\u8a08\u56f3\u7d20\u6750\u5909\u63db\u30c4\u30fc\u30eb_Setup.exe"
shutil.copy2(src, dst)
src.unlink()
print(dst)
"@

python $CopyHelper $FinalInstaller
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create Japanese-named installer."
}

Write-Host "Installer created in dist folder."
