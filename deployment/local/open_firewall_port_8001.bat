@echo off
setlocal

netsh advfirewall firewall add rule name="Vendor Accounts Web App - Local Version (Port 8001)" dir=in action=allow protocol=TCP localport=8001

echo Firewall rule added for Vendor Accounts Web App - Local Version on port 8001.
pause
