# يوم الخميس 2026-10-08 — ذرّات الشموع أوّلًا (أمر المالك: «الشموع أوّلًا، وزّع على الأنوية»).
# 151–165 · 201 (ومعها سجلّ البنية 202–208 والسيولة 251–254) · 255. طابورٌ على 10 عمليّات (12 نواة، تبقى اثنتان للجهاز)،
# كلّ ذرّة مقسومة على أجزاء، بأولويّة منخفضة؛ ثمّ الحكم.
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\QUANT_NQ\backtest\s150_calibration_2026-10-09'
$base = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib_day'
$o = "$base\runs"; $logs = "$base\logs"
New-Item -ItemType Directory -Force -Path $o, $logs | Out-Null
$atoms = @('151','152','153','154','155','156','157','158','159','160','161','162','163','164','165','201','255')
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
"runs done $(Get-Date -Format 'HH:mm:ss') files=$((Get-ChildItem $o -Filter '*.json.gz').Count)"
Get-ChildItem $logs -Filter '*.err' | Where-Object { $_.Length -gt 0 } | ForEach-Object { "ERR $($_.BaseName): " + ((Get-Content $_.FullName -Encoding utf8 -Tail 2) -join ' | ') }
& $py "$d\eval_day.py" --in $o
"eval done $(Get-Date -Format 'HH:mm:ss')"
