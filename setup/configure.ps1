. "$PSScriptRoot/common.ps1"
$localDir = Join-Path $KitRoot 'local'
New-Item -ItemType Directory -Path $localDir -Force | Out-Null
$file = Join-Path $localDir 'secrets.env'
$values = [ordered]@{}
if (Test-Path -LiteralPath $file) {
    foreach ($line in [IO.File]::ReadAllLines($file)) {
        if ($line -match '^([A-Z_][A-Z0-9_]*)=(.*)$') { $values[$matches[1]]=$matches[2] }
    }
}
# Plain-language Vietnamese hints for non-technical users; only key names are shown. UTF-8 BOM keeps PowerShell 5.1 reading them correctly.
$keys = [ordered]@{
    'GENMAX_API_KEY'           = 'Genmax - giọng đọc tiếng Anh cho video fitness (genmax.io > API keys)'
    'GEMINI_API_KEY'           = 'Google Gemini - vẽ nhân vật, giọng dự phòng (aistudio.google.com > Get API key)'
    'ZERNIO_API_KEY'           = 'Zernio - đăng bài lên TikTok/YouTube/Facebook/LinkedIn (zernio.com > API keys)'
    'ZERNIO_API_KEY_SECONDARY' = 'Zernio profile thứ hai - chỉ cần khi dùng hai profile Zernio'
    'ELEVENLABS_API_KEY'       = 'ElevenLabs - chuyển lời nói thành chữ cho video tự quay (elevenlabs.io > API keys)'
}
Write-Host 'Dán từng key rồi nhấn Enter. Ký tự sẽ không hiện ra. Để trống và nhấn Enter nếu muốn giữ giá trị cũ hoặc bỏ qua.'
foreach ($name in $keys.Keys) {
    $status = if ($values[$name]) { 'đã lưu' } else { 'chưa có' }
    Write-Host ''
    Write-Host "$name [$status]"
    Write-Host "  $($keys[$name])"
    $secure = Read-Host -Prompt $name -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
        if ($plain.Length -gt 0) {
            if ($plain -match '[\r\n]') { throw 'Key must be one line.' }
            $values[$name] = $plain.Trim()
        }
    } finally {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        $plain = $null
        $secure.Dispose()
    }
}
$lines = foreach ($entry in $values.GetEnumerator()) { $entry.Key + '=' + $entry.Value }
[IO.File]::WriteAllLines($file,[string[]]$lines,(New-Object Text.UTF8Encoding($false)))
if (!(Test-Path -LiteralPath (Join-Path $localDir 'accounts.json'))) {
    Copy-Item -LiteralPath (Join-Path $KitRoot 'config/accounts.example.json') -Destination (Join-Path $localDir 'accounts.json')
}
Write-Host ''
foreach ($name in $keys.Keys) { Write-Host ("{0,-26} {1}" -f $name, $(if ($values[$name]) { 'đã lưu' } else { '-' })) }
Write-Host 'Đã lưu key trên máy này (không hiển thị). Không gửi file local/secrets.env cho người khác.'
