# قمّة الهرم لقسم 150: كلّ (ذرّة × إطار × عيار من البحث) بكود الذرّة نفسه على 12 سنة — 5 عمليّات معًا بأولويّة منخفضة.
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\s150_bench'
New-Item -ItemType Directory -Force -Path "$d\facts" | Out-Null
$jobs = @()
foreach ($fr in '1h','4h','1d') {
  $jobs += ,@('151', $fr, 'base', @())
  $jobs += ,@('151', $fr, 'f20s50', @('--set','ema_fast=20','--set','ema_slow=50'))
  $jobs += ,@('151', $fr, 'f50s200', @('--set','ema_fast=50','--set','ema_slow=200','--set','min_candles=200'))
  $jobs += ,@('152', $fr, 'roc5', @())
  $jobs += ,@('152', $fr, 'roc10', @('--set','roc_period=10'))
  $jobs += ,@('152', $fr, 'roc20', @('--set','roc_period=20','--set','min_candles=24'))
  $jobs += ,@('161', $fr, 'base', @('--peers'))
  $jobs += ,@('165', $fr, 'base', @())
  $jobs += ,@('153', $fr, 'base', @())
}
$jobs += ,@('157', '1d', 'base', @())
$jobs += ,@('157', '1h', 'base', @())
$jobs += ,@('159', '1h', 'base', @())
$jobs += ,@('158', '1h', 'base', @())
$running = @()
foreach ($j in $jobs) {
  while (@($running | Where-Object { -not $_.HasExited }).Count -ge 5) { Start-Sleep -Seconds 3 }
  $name = "$($j[0])_$($j[1])_$($j[2])"
  $args = @("$d\run150.py", '--atom', $j[0], '--frame', $j[1], '--out', "$d\facts\$name.jsonl") + $j[3]
  $p = Start-Process -FilePath $py -ArgumentList $args -RedirectStandardOutput "$d\facts\$name.log" -RedirectStandardError "$d\facts\$name.err" -NoNewWindow -PassThru -WorkingDirectory $d
  try { $p.PriorityClass = 'BelowNormal' } catch {}
  $running += $p
}
$running | ForEach-Object { $_.WaitForExit() }
"done $(Get-Date -Format 'HH:mm:ss')"
Get-ChildItem "$d\facts" -Filter '*.err' | Where-Object { $_.Length -gt 0 } | ForEach-Object { "ERR $($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 2) -join ' | ') }
