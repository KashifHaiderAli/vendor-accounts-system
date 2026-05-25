@echo off
setlocal

netsh advfirewall firewall add rule name="Vendor Accounts Web App - Main Version (Port 8000)" dir=in action=allow protocol=TCP localport=8000

echo Firewall rule added for Vendor Accounts Web App - Main Version on port 8000.
pause
