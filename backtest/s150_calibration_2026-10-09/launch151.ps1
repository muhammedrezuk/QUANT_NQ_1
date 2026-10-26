# معايرة 151 وحدها: الأطر الخمسة معًا بأولويّة منخفضة، ثمّ حكم الاكتشاف والتحقّق (الخزنة لا تُفتح هنا).
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\QUANT_NQ\backtest\s150_calibration_2026-10-09'
$o = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib151\out'
$logs = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib151\logs'
New-Item -ItemType Directory -Force -Path $o, $logs | Out-Null
$running = @()
foreach ($fr in '5m','15m','1h','4h','1d') {
  $p = Start-Process -FilePath $py -ArgumentList @("$d\calib151.py", '--frame', $fr, '--out', $o) `
       -RedirectStandardOutput "$logs\$fr.log" -RedirectStandardError "$logs\$fr.err" -NoNewWindow -PassThru
  try { $p.PriorityClass = 'BelowNormal' } catch {}
  $running += $p
}
$running | ForEach-Object { $_.WaitForExit() }
"runs done $(Get-Date -Format 'HH:mm:ss')"
Get-ChildItem $logs -Filter '*.err' | Where-Object { $_.Length -gt 0 } | ForEach-Object { "ERR $($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 3) -join ' | ') }
(Get-ChildItem $o -Filter '*.npz').Count
& $py "$d\eval151.py" select --in $o
"eval done $(Get-Date -Format 'HH:mm:ss')"
