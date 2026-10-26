# يوم الخميس 2026-10-08 — ذرّات التِّكّ وحدها (أمر المالك: «شغّلها على تِكّ بس، يوم واحد»): الإحصاء 301–318 والنماذج 351–358،
# النوافذ من 20 حتّى 6000 تِكّة. طابورٌ على 10 عمليّات، كلّ ذرّة على 3 أجزاء، بأولويّة منخفضة؛ ثمّ الحكم على كلّ الأيّام المقيسة.
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\QUANT_NQ\backtest\s150_calibration_2026-10-09'
$base = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib_day'
$o = "$base\runs"; $logs = "$base\logs_ticks"
New-Item -ItemType Directory -Force -Path $o, $logs | Out-Null
$atoms = @('301','302','303','304','305','306','307','308','309','310','311','312','313','314','315','316','318',
           '351','352','353','354','355','356','358')
$parts = 3
$jobs = foreach ($a in $atoms) { foreach ($i in 0..($parts-1)) { ,@($a, "$i/$parts") } }
$running = @()
"start $(Get-Date -Format 'HH:mm:ss') jobs=$($jobs.Count)"
foreach ($j in $jobs) {
  while (@($running | Where-Object { -not $_.HasExited }).Count -ge 10) { Start-Sleep -Seconds 2 }
  $tag = "$($j[0])_$($j[1].Replace('/','of'))"
  $p = Start-Process -FilePath $py -ArgumentList @("$d\calib_day.py", '--tune', $j[0], '--part', $j[1], '--out', $o) `
       -RedirectStandardOutput "$logs\$tag.log" -RedirectStandardError "$logs\$tag.err" -NoNewWindow -PassThru
  try { $p.PriorityClass = 'BelowNormal' } catch {}
  $running += $p
}
$running | ForEach-Object { $_.WaitForExit() }
"runs done $(Get-Date -Format 'HH:mm:ss') files=$((Get-ChildItem $o -Filter '3*.json.gz').Count)"
Get-ChildItem $logs -Filter '*.err' | Where-Object { $_.Length -gt 0 } | ForEach-Object { "ERR $($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 2) -join ' | ') }
& $py "$d\eval_day.py" --in $o
"eval done $(Get-Date -Format 'HH:mm:ss')"
