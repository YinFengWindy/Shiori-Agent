# Authenticated, text-only local callback. Credentials are read from the saved file.
param(
    [Parameter(Mandatory = $true)][string]$Connection,
    [switch]$Handshake
)
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
try {
    $settings = Get-Content -LiteralPath $Connection -Raw -Encoding UTF8 | ConvertFrom-Json
    $callback = [Uri]$settings.callback_url
    if ($callback.Scheme -ne 'http' -or $callback.Host -ne '127.0.0.1' -or $callback.UserInfo -or $callback.Query -or $callback.Fragment) {
        throw 'Invalid local callback address'
    }
    if ($Handshake) {
        $payload = @{ protocol = $settings.protocol; challenge = $settings.challenge } | ConvertTo-Json -Compress
        $operation = 'handshake'
    } else {
        $payload = [Console]::In.ReadToEnd()
        $operation = 'messages'
    }
    $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
    if ($bytes.Length -gt 65536) { throw 'Message too large' }
    # HttpWebRequest avoids user proxy settings and never follows redirects.
    $request = [Net.HttpWebRequest]::Create($callback.AbsoluteUri + $operation)
    $request.Proxy = $null
    $request.AllowAutoRedirect = $false
    $request.Method = 'POST'
    $request.ContentType = 'application/json; charset=utf-8'
    $request.Headers['Authorization'] = 'Bearer ' + $settings.token
    $request.Timeout = 15000
    $request.ReadWriteTimeout = 15000
    $request.ContentLength = $bytes.Length
    $stream = $request.GetRequestStream()
    try { $stream.Write($bytes, 0, $bytes.Length) } finally { $stream.Dispose() }
    $response = $request.GetResponse()
    try {
        if ([int]$response.StatusCode -notin @(200, 202)) { throw 'Callback not accepted' }
        $reader = [IO.StreamReader]::new($response.GetResponseStream(), [Text.Encoding]::UTF8)
        try { [Console]::Out.WriteLine($reader.ReadToEnd()) } finally { $reader.Dispose() }
    } finally { $response.Dispose() }
} catch {
    # Exception details may contain URLs or credentials; only emit a safe outcome.
    [Console]::Error.WriteLine('Shiori callback failed or uncertain. Keep the same message_id; check the connection status.')
    exit 1
}
