//+------------------------------------------------------------------+
//| NQ_CalendarSync.mq5 — مزامنة التقويم الاقتصاديّ كلّ ساعة (قراءة فقط)
//|
//| أمر المالك ٢٠٢٦-١٠-٠٨ (ختم «NQ» — «المعرفة أوّلًا»): «لازم يعرف شو صار بالماضي، وإيمتى
//| مواعيد المستقبل، شو جاي».
//| لماذا: سكربت NQ_CalendarHistory صدّر التقويم مرّةً (٢٠٢٦-١٠-٠٧ 16:52 غرينتش) ومعه ١٤ يومًا
//| قادمة فقط — فلا يعرف النظام اجتماع الفائدة القادم ولا ما بعد أسبوعين، وما يصدر بعد التصدير يبقى
//| بلا قيمة فعليّة. وجدول calendar في قاعدة الجسر يكتبه الإكسبرت الحيّ ليومٍ قبل ويومين بعد وحسب.
//|
//| ⛔ إكسبرت قراءةٍ لا تداول: لا أوامر ولا تعديل حساب ولا مراكز — يقرأ التقويم وحده كلّ ساعة،
//|    ويكتب في القاعدة المنفصلة نفسها (Common\Files\nq_calendar_history.db) بالمخطّط نفسه، فتقرؤها
//|    ذرّات المعرفة 117 · 118 · 119 للقراءة فقط. يُركَّب على أيّ شارت (لا يحتاج زرّ التداول الآليّ).
//|
//| الوقت: كالسكربت — time_server بوقت خادم الوسيط كما هو، وفرق الخادم لحظة المزامنة في export_meta.
//+------------------------------------------------------------------+
#property copyright "QUANT_NQ"
#property version   "1.00"

input int    InpDaysBack     = 30;                    // أيّامٌ ماضية تُحدَّث قيمها كلّ مرّة
input int    InpDaysAhead    = 180;                   // أيّامٌ قادمة (المواعيد المجدولة)
input int    InpEveryMinutes = 60;                    // كلّ كم دقيقة تُعاد المزامنة
input string InpCountries    = "US,EU,CN,JP,GB,DE";  // رموز الدول؛ فارغ = كلّ الدول
input bool   InpBackfill     = true;                  // إن كانت القاعدة فارغة: يملؤها من 2014 أوّل مرّة
input datetime InpBackfillFrom = D'2014.01.01 00:00'; // بداية الملء الأوّل

string Esc(string s) { StringReplace(s, "'", "''"); return "'" + s + "'"; }
string Val(long v)   { if(v == LONG_MIN) return "NULL"; return DoubleToString(v / 1000000.0, 6); }

int OnInit()
{
   EventSetTimer(MathMax(5, InpEveryMinutes) * 60);
   Sync();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); Comment(""); }
void OnTimer()                  { Sync(); }

void Sync()
{
   int db = DatabaseOpen("nq_calendar_history.db",
                         DATABASE_OPEN_READWRITE | DATABASE_OPEN_CREATE | DATABASE_OPEN_COMMON);
   if(db == INVALID_HANDLE) { Print("✘ تعذّر فتح القاعدة: ", GetLastError()); return; }

   DatabaseExecute(db, "CREATE TABLE IF NOT EXISTS calendar_history ("
      "value_id INTEGER PRIMARY KEY, event_id INTEGER, event_code TEXT, event_name TEXT, "
      "country_code TEXT, currency TEXT, importance INTEGER, type INTEGER, sector INTEGER, "
      "frequency INTEGER, time_mode INTEGER, unit INTEGER, multiplier INTEGER, digits INTEGER, "
      "time_server INTEGER, period INTEGER, revision INTEGER, "
      "actual REAL, forecast REAL, prev REAL, revised_prev REAL, impact_type INTEGER, "
      "source_url TEXT, exported_at INTEGER)");
   DatabaseExecute(db, "CREATE TABLE IF NOT EXISTS export_meta (key TEXT PRIMARY KEY, value TEXT)");

   // القاعدة فارغة ⟸ ملءٌ أوّل من 2014؛ وإلّا نافذة المزامنة وحدها (ماضٍ قريب + مستقبل).
   datetime from_at = TimeTradeServer() - InpDaysBack * 86400;
   int req = DatabasePrepare(db, "SELECT COUNT(*) FROM calendar_history");
   long existing = 0;
   if(req != INVALID_HANDLE) { if(DatabaseRead(req)) DatabaseColumnLong(req, 0, existing); DatabaseFinalize(req); }
   if(InpBackfill && existing == 0) from_at = InpBackfillFrom;

   long off = (long)TimeTradeServer() - (long)TimeGMT();
   off = (long)MathRound(off / 900.0) * 900;
   long synced = (long)TimeGMT();
   datetime end_at = TimeTradeServer() + InpDaysAhead * 86400;

   string codes[];
   int nc = StringSplit(InpCountries, ',', codes);
   if(nc <= 0) { ArrayResize(codes, 1); codes[0] = ""; nc = 1; }

   long total = 0, failed = 0;
   for(int c = 0; c < nc && !IsStopped(); c++)
   {
      string code = codes[c];
      StringTrimLeft(code); StringTrimRight(code);
      datetime a = from_at;
      while(a < end_at && !IsStopped())
      {
         MqlDateTime d; TimeToStruct(a, d);
         d.day = 1; d.hour = 0; d.min = 0; d.sec = 0;
         d.mon += 1; if(d.mon > 12) { d.mon = 1; d.year += 1; }
         datetime b = StructToTime(d);
         if(b > end_at) b = end_at;

         MqlCalendarValue v[];
         ResetLastError();
         int n = (code == "") ? CalendarValueHistory(v, a, b) : CalendarValueHistory(v, a, b, code);
         if(n < 0) { failed++; Print("✘ ", code, " ", TimeToString(a, TIME_DATE), " خطأ ", GetLastError()); }
         if(n > 0)
         {
            DatabaseTransactionBegin(db);
            for(int i = 0; i < n; i++)
            {
               MqlCalendarEvent ev;
               if(!CalendarEventById(v[i].event_id, ev)) continue;
               MqlCalendarCountry ct;
               string ccode = "", ccur = "";
               if(CalendarCountryById(ev.country_id, ct)) { ccode = ct.code; ccur = ct.currency; }
               string q = "REPLACE INTO calendar_history VALUES("
                  + (string)(long)v[i].id + "," + (string)(long)ev.id + "," + Esc(ev.event_code) + "," + Esc(ev.name) + ","
                  + Esc(ccode) + "," + Esc(ccur) + "," + (string)(int)ev.importance + "," + (string)(int)ev.type + ","
                  + (string)(int)ev.sector + "," + (string)(int)ev.frequency + "," + (string)(int)ev.time_mode + ","
                  + (string)(int)ev.unit + "," + (string)(int)ev.multiplier + "," + (string)ev.digits + ","
                  + (string)(long)v[i].time + "," + (string)(long)v[i].period + "," + (string)v[i].revision + ","
                  + Val(v[i].actual_value) + "," + Val(v[i].forecast_value) + "," + Val(v[i].prev_value) + ","
                  + Val(v[i].revised_prev_value) + "," + (string)(int)v[i].impact_type + ","
                  + Esc(ev.source_url) + "," + (string)synced + ")";
               if(DatabaseExecute(db, q)) total++;
            }
            DatabaseTransactionCommit(db);
         }
         a = b;
      }
   }
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('server_offset_s_at_export','" + (string)off + "')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('exported_at_utc','" + (string)synced + "')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('server','" + AccountInfoString(ACCOUNT_SERVER) + "')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('countries','" + InpCountries + "')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('horizon_days_ahead','" + (string)InpDaysAhead + "')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('sync_mode','hourly_ea')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('last_sync_rows','" + (string)total + "')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('failed_chunks','" + (string)failed + "')");
   DatabaseClose(db);
   Comment("مزامنة التقويم: ", TimeToString(TimeGMT(), TIME_DATE | TIME_MINUTES), " غرينتش · ", total,
           " قيمة · حتّى ", InpDaysAhead, " يومًا قادمة · أجزاء فاشلة ", failed);
   Print("✓ مزامنة التقويم: ", total, " قيمة · أجزاء فاشلة ", failed);
}
