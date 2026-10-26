# سلسلة السيولة على الدقيقة والخمس والربع ساعة × عرض القمّة 1/2/3، من 2017-12 — 5 عمليّات معًا.
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\structure_bench'
New-Item -ItemType Directory -Force -Path "$d\liq" | Out-Null
$running = @()
foreach ($fr in '1m','5m','15m') { foreach ($lb in 1,2,3) {
  while (@($running | Where-Object { -not $_.HasExited }).Count -ge 5) { Start-Sleep -Seconds 3 }
  $p = Start-Process -FilePath $py -ArgumentList "$d\run_liq.py", '--frame', $fr, '--lookback', $lb, '--from', '2017-12-01', '--out', "$d\liq\$fr`_lb$lb.jsonl" -RedirectStandardOutput "$d\liq\$fr`_lb$lb.log" -RedirectStandardError "$d\liq\$fr`_lb$lb.err" -NoNewWindow -PassThru -WorkingDirectory $d
  try { $p.PriorityClass = 'BelowNormal' } catch {}
  $running += $p
} }
$running | ForEach-Object { $_.WaitForExit() }
"done $(Get-Date -Format 'HH:mm:ss')"
Get-ChildItem "$d\liq" -Filter '*.log' | ForEach-Object { "$($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 1) -join '') }
Get-ChildItem "$d\liq" -Filter '*.err' | Where-Object { $_.Length -gt 0 } | ForEach-Object { "ERR $($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 2) -join ' | ') }
