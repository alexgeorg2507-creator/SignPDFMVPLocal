# sync_vendor.ps1 — синхронизация канона signfinder-core/api в vendored-копии
# Запускать ПЕРЕД docker compose build, если менялся канон.
# Источник истины: C:\work\signfinder-core и C:\work\signfinder-api

$ErrorActionPreference = "Stop"

$CANON_CORE = "C:\work\signfinder-core"
$CANON_API  = "C:\work\signfinder-api"
$VENDOR_CORE = "C:\work\SignPDFMVPLocal\signfinder-core"
$VENDOR_API  = "C:\work\SignPDFMVPLocal\signfinder-api"

Write-Host "Синхронизация signfinder-core..." -ForegroundColor Cyan

# Удалить старую vendored-копию core (кроме .git если есть)
if (Test-Path $VENDOR_CORE) {
    Get-ChildItem $VENDOR_CORE -Exclude ".git" | Remove-Item -Recurse -Force
}

# Скопировать канон → vendored, исключая мусор
robocopy $CANON_CORE $VENDOR_CORE /MIR /XD ".git" "venv" "__pycache__" ".pytest_cache" "*.egg-info" /XF "*.pyc" /NFL /NDL /NJH /NJS /NC /NS
# robocopy exit codes 0-7 = success
if ($LASTEXITCODE -ge 8) { throw "robocopy core failed: $LASTEXITCODE" }

Write-Host "Синхронизация signfinder-api..." -ForegroundColor Cyan

if (Test-Path $VENDOR_API) {
    Get-ChildItem $VENDOR_API -Exclude ".git" | Remove-Item -Recurse -Force
}
robocopy "$CANON_API\app" "$VENDOR_API\app" /MIR /XD "__pycache__" /XF "*.pyc" /NFL /NDL /NJH /NJS /NC /NS
if ($LASTEXITCODE -ge 8) { throw "robocopy api failed: $LASTEXITCODE" }

Write-Host "Готово. Vendored-копии синхронизированы с каноном." -ForegroundColor Green
Write-Host "Теперь: docker compose build api" -ForegroundColor Yellow

# Проверка версии
$ver = Select-String -Path "$VENDOR_CORE\signfinder\__init__.py" -Pattern '__version__'
Write-Host "Vendored core: $ver" -ForegroundColor Gray
