param([Parameter(Mandatory)][string]$Working)

$ErrorActionPreference = 'Stop'
$workingPath = (Resolve-Path -LiteralPath $Working).Path
$app = Split-Path -Parent $workingPath
$python = Join-Path $app 'python\pythonw.exe'
$branded = Join-Path $app 'python\Aemeath.exe'
$start = Join-Path $app '.pyappify-shortcut.py'
$main = Join-Path $workingPath 'main.py'
foreach ($path in @($python, $start, $main)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "PyAppify file missing: $path. Open the original OK-WW once before creating this shortcut."
    }
}
if (Get-Process -Name Aemeath -ErrorAction SilentlyContinue | Where-Object Path -EQ $branded) {
    throw 'Close Aemeath before updating its shortcut.'
}
Copy-Item -LiteralPath $python -Destination $branded -Force
$desktop = [Environment]::GetFolderPath('Desktop')
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut((Join-Path $desktop 'Aemeath 助手.lnk'))
$shortcut.TargetPath = $branded
$shortcut.Arguments = '"' + $start + '"'
$shortcut.WorkingDirectory = $workingPath
$shortcut.IconLocation = (Join-Path $workingPath 'icons\icon.ico') + ',0'
$shortcut.Description = 'Aemeath 助手'
$shortcut.Save()
