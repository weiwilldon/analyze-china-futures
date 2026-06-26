$ErrorActionPreference = "Stop"

Write-Host "TqSdk account setup" -ForegroundColor Cyan
Write-Host "This will save TQSDK_USER and TQSDK_PASSWORD as user environment variables."
Write-Host "The password input is hidden and will not be printed." -ForegroundColor Yellow
Write-Host ""

$user = Read-Host "Enter TqSdk username"
if ([string]::IsNullOrWhiteSpace($user)) {
    throw "TqSdk username cannot be empty."
}

$securePassword = Read-Host "Enter TqSdk password" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

if ([string]::IsNullOrWhiteSpace($password)) {
    throw "TqSdk password cannot be empty."
}

[Environment]::SetEnvironmentVariable("TQSDK_USER", $user, "User")
[Environment]::SetEnvironmentVariable("TQSDK_PASSWORD", $password, "User")

Write-Host ""
Write-Host "Saved TqSdk environment variables for the current Windows user." -ForegroundColor Green
Write-Host "Close and reopen Codex, or start a new terminal/session, so new processes can read them."
Write-Host "Press Enter to close this window."
Read-Host | Out-Null
