# update.ps1 - Cap nhat code moi nhat va chay lai app, chi can 1 lenh duy nhat:
#
#   .\update.ps1
#
# Script nay tu dong: git pull -> kich hoat venv -> cai lai thu vien (neu doi)
# -> tat tien trinh Python cu -> chay lai app.py

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "[1/5] Dang tai code moi nhat..." -ForegroundColor Cyan
git pull

Write-Host "[2/5] Kich hoat moi truong ao..." -ForegroundColor Cyan
& "$PSScriptRoot\venv\Scripts\Activate.ps1"

Write-Host "[3/5] Cai dat thu vien (neu co thay doi)..." -ForegroundColor Cyan
pip install -q -r requirements.txt

Write-Host "[4/5] Dung cac tien trinh Python cu (neu co)..." -ForegroundColor Cyan
Get-Process python* -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 1

Write-Host "[5/5] Khoi dong app - mo trinh duyet vao http://localhost:5000" -ForegroundColor Green
python app.py
