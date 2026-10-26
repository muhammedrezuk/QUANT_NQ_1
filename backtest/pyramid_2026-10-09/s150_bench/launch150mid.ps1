# وسط الهرم لقسم 150: الذرّات على الخمس والربع ساعة من 2017-12 بكودها وعيار بيانها — 4 عمليّات معًا.
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\500dc279-a556-4c4c-881e-d017738aae39\scratchpad\s150_bench'
New-Item -ItemType Directory -Force -Path "$d\facts_mid" | Out-Null
$running = @()
foreach ($fr in '15m','5m') { foreach ($id in '151','152','153','154','156','165') {
  while (@($running | Where-Object { -not $_.HasExited }).Count -ge 4) { Start-Sleep -Seconds 5 }
  $name = "$id`_$fr"
  $p = Start-Process -FilePath $py -ArgumentList "$d\run150.py", '--atom', $id, '--frame', $fr, '--from', '2017-12-01', '--out', "$d\facts_mid\$name.jsonl" -RedirectStandardOutput "$d\facts_mid\$name.log" -RedirectStandardError "$d\facts_mid\$name.err" -NoNewWindow -PassThru -WorkingDirectory $d
  try { $p.PriorityClass = 'BelowNormal' } catch {}
  $running += $p
} }
$running | ForEach-Object { $_.WaitForExit() }
"done $(Get-Date -Format 'HH:mm:ss')"
Get-ChildItem "$d\facts_mid" -Filter '*.log' | ForEach-Object { "$($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 1) -join '') }
Get-ChildItem "$d\facts_mid" -Filter '*.err' | Where-Object { $_.Length -gt 0 } | ForEach-Object { "ERR $($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 2) -join ' | ') }
