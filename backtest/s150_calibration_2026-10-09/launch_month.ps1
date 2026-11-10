# الشهر 2026-09-08 ⟵ 2026-10-08 (أمر المالك ١٠-١٠: «10 أنوية، شهر كامل، على ناسداك لندن ونيويورك، وسّع وضيّق NQ»).
# قياسٌ فقط — لا يكتب في الذرّات. يعمل على الجهاز وحده (يُطلق من المستكشف)، وسجلّه في month_run.log بجانبه.
$py = 'C:\Users\NQ\AppData\Local\Programs\Python\Python312\python.exe'
$d = 'C:\Users\NQ\QUANT_NQ\backtest\s150_calibration_2026-10-09'
$base = 'C:\Users\NQ\AppData\Local\Temp\claude\C--\ae528487-dc7c-45b7-af2c-39fed31dd93f\scratchpad\calib_day'
$env:CALIB_SCRATCH = $base
$log = "$d\month_run.log"
function Say($m) { "$(Get-Date -Format 'MM-dd HH:mm:ss') $m" | Out-File -FilePath $log -Append -Encoding utf8 }
$days = @()
$t = [datetime]'2026-09-08'
while ($t -le [datetime]'2026-10-08') { if ($t.DayOfWeek -ne 'Saturday' -and $t.DayOfWeek -ne 'Sunday') { $days += $t.ToString('yyyy-MM-dd') }; $t = $t.AddDays(1) }
$tick = @('301','302','303','304','305','306','307','308','309','310','311','312','313','314','315','316','318','351','352','353','354','355','356','358')
$cand = @('151','152','153','154','155','156','157','158','159','160','161','162','163','164','165','201','255')
Say "بدء — أيّام $($days.Count)"

function RunQueue($jobs, $max) {
  $running = @()
  foreach ($j in $jobs) {
    while (@($running | Where-Object { -not $_.HasExited }).Count -ge $max) { Start-Sleep -Seconds 3 }
    $env:CALIB_DAY = $j.day
    $p = Start-Process -FilePath $py -ArgumentList $j.args -RedirectStandardOutput $j.out -RedirectStandardError $j.err -NoNewWindow -PassThru
    try { $p.PriorityClass = 'BelowNormal' } catch {}
    $running += $p
  }
  $running | ForEach-Object { $_.WaitForExit() }
}

# ١) بيانات كلّ يوم (شموع اليوم وتِكّاته) مرّةً قبل الذرّات.
New-Item -ItemType Directory -Force -Path "$base\logs_month" | Out-Null
$prep = foreach ($day in $days) { [pscustomobject]@{ day = $day; args = @("$d\calib_day.py", '--prep');
  out = "$base\logs_month\prep_$day.log"; err = "$base\logs_month\prep_$day.err" } }
RunQueue $prep 10
Say "البيانات جاهزة"

# ٢) الذرّات: يومًا يومًا، ذرّات التِّكّ الثقيلة أوّلًا في كلّ يوم.
foreach ($day in $days) {
  $o = "$base\runs_$day"
  New-Item -ItemType Directory -Force -Path $o | Out-Null
  $jobs = foreach ($a in ($tick + $cand)) { foreach ($i in 0..1) { [pscustomobject]@{ day = $day;
    args = @("$d\calib_day.py", '--tune', $a, '--part', "$i/2", '--out', $o);
    out = "$base\logs_month\${day}_${a}_$i.log"; err = "$base\logs_month\${day}_${a}_$i.err" } } }
  RunQueue $jobs 10
  $env:CALIB_DAY = $day
  & $py "$d\eval_day.py" --in $o *>> "$base\logs_month\eval_$day.log"
  Say "يوم $day تمّ — ملفّات $((Get-ChildItem $o -Filter '*.json.gz').Count)"
  & $py "$d\agg_month.py" *>> "$base\logs_month\agg.log"
}
Say "انتهى الشهر — month_summary.md"
