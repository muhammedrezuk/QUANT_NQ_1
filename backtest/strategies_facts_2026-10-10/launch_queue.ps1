# الطابور الدائم (أمر المالك ١٠-١١: «الكمبيوتر شغّال 7/24 … كلّ قياس 12 ساعة من الليل للصبح ومن الصبح لليل، واجمع عليه» + «NQ»).
# قياسٌ فقط، لا يمسّ الحيّ. ينتظر قياس السنة الجاري، ثمّ شبكة النوافذ لكلّ يوم (10 أنوية، أولويّة منخفضة)،
# ويكتب تقريرًا عند 09:00 و21:00 كلّ يوم على ما انتهى («آخر تقرير.md» + reports\). ومهامّ تُضاف لاحقًا: queue.txt
# (سطرٌ لكلّ مهمّة: اسم_السكربت|اليوم) — يقرؤه بعد انتهاء الشبكة.
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\QUANT_NQ\backtest\strategies_facts_2026-10-10'
$base = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib_day'
$env:CALIB_SCRATCH = $base
$log = "$d\queue_run.log"
$logs = "$base\logs_queue"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
function Say($m) { "$(Get-Date -Format 'MM-dd HH:mm:ss') $m" | Out-File -FilePath $log -Append -Encoding utf8 }
$script:lastReport = ''
function MaybeReport {
  $now = Get-Date
  $slot = if ($now.Hour -ge 21) { $now.ToString('yyyy-MM-dd') + '-21' } elseif ($now.Hour -ge 9) { $now.ToString('yyyy-MM-dd') + '-09' } else { '' }
  if ($slot -and $slot -ne $script:lastReport) {
    $script:lastReport = $slot
    Say "تقرير $slot يبدأ"
    & $py "$d\walkforward_grid.py" *>> "$logs\report_$slot.log"
    Say "تقرير $slot انتهى — آخر تقرير.md"
  }
}
# التقرير لا يُكتب لفترةٍ بدأ الطابور داخلها (يُنتظر موعده القادم).
$h = (Get-Date).Hour
$script:lastReport = if ($h -ge 21) { (Get-Date).ToString('yyyy-MM-dd') + '-21' } elseif ($h -ge 9) { (Get-Date).ToString('yyyy-MM-dd') + '-09' } else { '' }
Say "الطابور بدأ"
while (@(Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match 'year_day.py|launch_year' }).Count -gt 0) {
  Start-Sleep -Seconds 60; MaybeReport
}
Say "قياس السنة انتهى — الشبكة تبدأ"
$days = @()
$t = [datetime]'2025-10-13'
while ($t -le [datetime]'2026-10-08') { if ($t.DayOfWeek -ne 'Saturday' -and $t.DayOfWeek -ne 'Sunday') { $days += $t.ToString('yyyy-MM-dd') }; $t = $t.AddDays(1) }
# الأحدث أوّلًا: أشهر الحكم القريبة تكتمل قبل البعيدة.
[array]::Reverse($days)
$running = @()
foreach ($day in $days) {
  while (@($running | Where-Object { -not $_.HasExited }).Count -ge 10) { Start-Sleep -Seconds 10; MaybeReport }
  $env:CALIB_DAY = $day
  $p = Start-Process -FilePath $py -ArgumentList @("$d\grid_day.py") -RedirectStandardOutput "$logs\grid_$day.log" `
       -RedirectStandardError "$logs\grid_$day.err" -NoNewWindow -PassThru
  try { $p.PriorityClass = 'BelowNormal' } catch {}
  $running += $p
}
while (@($running | Where-Object { -not $_.HasExited }).Count -gt 0) { Start-Sleep -Seconds 30; MaybeReport }
Say "الشبكة انتهت"
& $py "$d\walkforward_grid.py" *>> "$logs\report_final_grid.log"
Say "تقرير الشبكة النهائيّ — آخر تقرير.md"
# مهامّ تُضاف لاحقًا.
while ($true) {
  $q = "$d\queue.txt"
  if (Test-Path $q) {
    $done = "$d\queue_done.txt"
    $seen = if (Test-Path $done) { Get-Content $done -Encoding utf8 } else { @() }
    foreach ($line in (Get-Content $q -Encoding utf8)) {
      if (-not $line.Trim() -or $seen -contains $line) { continue }
      $parts = $line.Split('|')
      while (@($running | Where-Object { -not $_.HasExited }).Count -ge 10) { Start-Sleep -Seconds 10; MaybeReport }
      $env:CALIB_DAY = $parts[1]
      $p = Start-Process -FilePath $py -ArgumentList @("$d\$($parts[0])") -RedirectStandardOutput "$logs\q_$($parts[1]).log" `
           -RedirectStandardError "$logs\q_$($parts[1]).err" -NoNewWindow -PassThru
      try { $p.PriorityClass = 'BelowNormal' } catch {}
      $running += $p
      $line | Out-File -FilePath $done -Append -Encoding utf8
    }
  }
  Start-Sleep -Seconds 60; MaybeReport
}
