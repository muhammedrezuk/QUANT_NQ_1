# يطلق سلسلة البنية على كلّ (إطار × عرض قمّة) بالتوازي على أنوية الجهاز — 5 عمليّات معًا، بأولويّة منخفضة.
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\structure_bench'
New-Item -ItemType Directory -Force -Path "$d\events" | Out-Null
$jobs = @()
foreach ($fr in '5m','15m','1h','4h','1d') { foreach ($lb in 1,2,3,5) { $jobs += ,@($fr, $lb) } }
$running = @()
foreach ($j in $jobs) {
  while (@($running | Where-Object { -not $_.HasExited }).Count -ge 5) { Start-Sleep -Seconds 5 }
  $fr = $j[0]; $lb = $j[1]
  $out = "$d\events\$fr`_lb$lb.jsonl"
  $p = Start-Process -FilePath $py -ArgumentList "$d\run_chain.py", '--frame', $fr, '--lookback', $lb, '--out', $out -RedirectStandardOutput "$d\events\$fr`_lb$lb.log" -RedirectStandardError "$d\events\$fr`_lb$lb.err" -NoNewWindow -PassThru -WorkingDirectory $d
  try { $p.PriorityClass = 'BelowNormal' } catch {}
  $running += $p
}
$running | ForEach-Object { $_.WaitForExit() }
"done $(Get-Date -Format 'HH:mm:ss')"
Get-ChildItem "$d\events" -Filter '*.log' | ForEach-Object { "$($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 1) -join '') }
Get-ChildItem "$d\events" -Filter '*.err' | Where-Object { $_.Length -gt 0 } | ForEach-Object { "ERR $($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 3) -join ' | ') }
