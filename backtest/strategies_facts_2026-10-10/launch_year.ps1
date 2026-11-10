# سنة المشي إلى الأمام (أمر المالك ١٠-١٠ «عيد قياس بطريقة مختلفة وأطول» + «NQ») — قياسٌ فقط، لا يمسّ الحيّ.
# أيّام العمل 2025-10-13 ⟵ 2026-10-08 (التِّكّات من 2025-10-09)، يومٌ لكلّ عمليّة، 10 معًا بأولويّة منخفضة؛ ثمّ الحكم.
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\QUANT_NQ\backtest\strategies_facts_2026-10-10'
$base = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib_day'
$env:CALIB_SCRATCH = $base
$log = "$d\year_run.log"
$logs = "$base\logs_year"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
function Say($m) { "$(Get-Date -Format 'MM-dd HH:mm:ss') $m" | Out-File -FilePath $log -Append -Encoding utf8 }
$days = @()
$t = [datetime]'2025-10-13'
while ($t -le [datetime]'2026-10-08') { if ($t.DayOfWeek -ne 'Saturday' -and $t.DayOfWeek -ne 'Sunday') { $days += $t.ToString('yyyy-MM-dd') }; $t = $t.AddDays(1) }
Say "بدء — أيّام $($days.Count)"
$running = @()
$n = 0
foreach ($day in $days) {
  while (@($running | Where-Object { -not $_.HasExited }).Count -ge 10) { Start-Sleep -Seconds 5 }
  $env:CALIB_DAY = $day
  $p = Start-Process -FilePath $py -ArgumentList @("$d\year_day.py") -RedirectStandardOutput "$logs\$day.log" `
       -RedirectStandardError "$logs\$day.err" -NoNewWindow -PassThru
  try { $p.PriorityClass = 'BelowNormal' } catch {}
  $running += $p
  $n += 1
  if ($n % 20 -eq 0) { Say "أُطلق $n من $($days.Count)" }
}
$running | ForEach-Object { $_.WaitForExit() }
Say "الأيّام انتهت — أخطاء: $((Get-ChildItem $logs -Filter '*.err' | Where-Object { $_.Length -gt 0 }).Count)"
& $py "$d\walkforward.py" *>> "$logs\walkforward.log"
Say "انتهى — walkforward_summary_USTEC.md"
