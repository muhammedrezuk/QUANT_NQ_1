# 151 — الشبكة الأولى (33) والموسّعة (32: أضيق وأوسع، طلب المالك) على الأطر الخمسة؛ الحكم من bench_signal بلا توأم.
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\QUANT_NQ\backtest\s150_calibration_2026-10-09'
$o = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib151\out2'
$logs = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib151\logs2'
New-Item -ItemType Directory -Force -Path $o, $logs | Out-Null
$running = @()
foreach ($wide in '', '1') {
  foreach ($fr in '5m','15m','1h','4h','1d') {
    $env:CALIB_WIDE = $wide
    $p = Start-Process -FilePath $py -ArgumentList @("$d\calib151.py", '--frame', $fr, '--out', $o) `
         -RedirectStandardOutput "$logs\${fr}_w$wide.log" -RedirectStandardError "$logs\${fr}_w$wide.err" -NoNewWindow -PassThru
    try { $p.PriorityClass = 'BelowNormal' } catch {}
    $running += $p
  }
}
$running | ForEach-Object { $_.WaitForExit() }
"runs done $(Get-Date -Format 'HH:mm:ss')"
Get-ChildItem $logs -Filter '*.err' | Where-Object { $_.Length -gt 0 } | ForEach-Object { "ERR $($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 3) -join ' | ') }
(Get-ChildItem $o -Filter '*.npz').Count
