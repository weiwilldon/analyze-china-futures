param(
  [Parameter(Mandatory=$true)]
  [string]$Token
)

[Environment]::SetEnvironmentVariable("TUSHARE_TOKEN", $Token, "User")
$env:TUSHARE_TOKEN = $Token

Write-Host "TUSHARE_TOKEN has been saved to the current Windows user environment."
Write-Host "Open a new Codex session or terminal if the current process cannot see it."
