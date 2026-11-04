# Builds Omnibloom-Setup.exe with Windows Python, inside this folder only (.venv-win, .build-win, dist).
# Runs the fake-console tests on Windows first, then checks the built exe against the fake console.
# Touches nothing outside this folder and never contacts the PS5.
$ErrorActionPreference = 'Continue'
Set-Location -LiteralPath $PSScriptRoot
$log = Join-Path $PSScriptRoot 'win-build.txt'
"started $(Get-Date -Format s)" | Set-Content -LiteralPath $log -Encoding utf8
function Say($t) { $t | Out-String -Width 200 | Add-Content -LiteralPath $log -Encoding utf8 }
function Run([string]$exe, [string[]]$a) { Say ("> " + $exe + " " + ($a -join ' ')); & $exe @a 2>&1 | ForEach-Object { "$_" } | Add-Content -LiteralPath $log -Encoding utf8; Say ("exit " + $LASTEXITCODE) }
Say (Get-Command py, python, python3 -ErrorAction SilentlyContinue | Select-Object Name, Source)
$venv = Join-Path $PSScriptRoot '.venv-win'
$vpy = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path $vpy)) {
  $base = $null
  if (Get-Command py -ErrorAction SilentlyContinue) { Run 'py' @('-3', '-m', 'venv', $venv) }
  else {
    $cand = Get-Command python -ErrorAction SilentlyContinue | Where-Object { $_.Source -notlike '*WindowsApps*' } | Select-Object -First 1
    if ($cand) { Run $cand.Source @('-m', 'venv', $venv) }
  }
}
if (-not (Test-Path $vpy)) { Say 'RESULT: no usable Windows Python (only the Microsoft Store shortcut, or none)'; exit 3 }
Run $vpy @('--version')
Run $vpy @('-m', 'pip', 'install', '--disable-pip-version-check', '-q', 'pyinstaller>=6.16', 'pyftpdlib>=2.0', 'pillow')
Say 'TESTS:'
Run $vpy @('-W', 'ignore', '-m', 'unittest', 'tests.test_end_to_end')
Say 'BUILD:'
Run $vpy @('-m', 'PyInstaller', '--noconfirm', '--log-level', 'WARN', '--distpath', 'dist', '--workpath', '.build-win', 'omnibloom-setup.spec')
if (Test-Path 'dist\Omnibloom-Setup.exe') {
  Say 'FROZEN:'
  Run $vpy @('-W', 'ignore', 'tools\frozen_check.py', 'dist\Omnibloom-Setup.exe')
  Say (Get-Item 'dist\Omnibloom-Setup.exe' | Select-Object Name, Length)
  Say ((Get-FileHash 'dist\Omnibloom-Setup.exe' -Algorithm SHA256).Hash)
  Say 'RESULT: built'
} else { Say 'RESULT: build failed' }
