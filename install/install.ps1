# autogovern installer for Windows (PowerShell).
# Usage: irm https://raw.githubusercontent.com/ashborn-systems/autogovern/main/install/install.ps1 | iex
$ErrorActionPreference = "Stop"

# Install uv if absent.
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    irm https://astral.sh/uv/install.ps1 | iex
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}

Write-Host "Installing autogovern..."
# Re-running the installer upgrades an existing installation.
if (uv tool list 2>$null | Select-String -Pattern '^autogovern ') {
    uv tool upgrade autogovern
} else {
    uv tool install autogovern
}

if (-not (Get-Command autogovern -ErrorAction SilentlyContinue)) {
    Write-Host ""
    Write-Host "autogovern is not on your PATH. Add this to your PowerShell profile:"
    Write-Host "  `$env:Path = `"$env:USERPROFILE\.local\bin;`$env:Path`""
    Write-Host ""
}

Write-Host ""
Write-Host "autogovern installed successfully."
Write-Host "Run 'autogovern init' to get started."
