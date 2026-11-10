//+------------------------------------------------------------------+
//| NQ_CalendarHistory.mq5 — تصدير تاريخ التقويم الاقتصاديّ (قراءة فقط)
//|
//| أمر المالك ٢٠٢٦-١٠-٠٧: «شغّل جلب nq» · «عبّي قاعدة بيانات أخبار» · «عملها».
//| لماذا: جدول calendar في قاعدة الجسر يكتبه الإكسبرت لنافذة يومٍ قبل ويومين بعد فقط،
//| فما عندنا يبدأ ٢٠٢٦-٠٩-٠١. وتقويم ميتاتريدر نفسه يحفظ التاريخ بالقيمة الفعليّة
//| والمتوقَّعة والسابقة — وهي «المتوقَّع» الذي تحتاجه طبقة الأخبار (ورقة النقاش ٤-د).
//|
//| ⛔ سكربتٌ لا إكسبرت: يعمل مرّةً ويخرج. لا أوامر تداول ولا تعديل حساب ولا مراكز —
//|    يقرأ التقويم وحده، ويكتب في قاعدةٍ منفصلة في المجلّد المشترك:
//|    Common\Files\nq_calendar_history.db  (لا يقرؤها النظام الحيّ).
//|
//| الوقت: قيم التقويم بوقت خادم الوسيط. يُحفظ كما هو (time_server)، ويُحفظ فرق الخادم
//| لحظة التصدير في export_meta. لا يُحوَّل التاريخ القديم إلى غرينتش هنا: فرق الخادم
//| يتغيّر مع التوقيت الصيفيّ، وقاعدته عند الوسيط تُقاس لاحقًا من أخبارٍ معروفة الساعة.
//+------------------------------------------------------------------+
#property copyright "QUANT_NQ"
#property version   "1.00"
#property script_show_inputs

input datetime InpFrom      = D'2014.01.01 00:00';      // من (بداية تاريخ الناسداك عندنا)
input int      InpDaysAhead = 14;                        // أيّامٌ قادمة تُضاف
input string   InpCountries = "US,EU,CN,JP,GB,DE";      // رموز الدول؛ فارغ = كلّ الدول

string Esc(string s) { StringReplace(s, "'", "''"); return "'" + s + "'"; }
string Val(long v)   { if(v == LONG_MIN) return "NULL"; return DoubleToString(v / 1000000.0, 6); }

void OnStart()
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

   // فرق الخادم عن غرينتش الآن، مقرّبًا لربع ساعة (وقت الخادم قد يتأخّر ثوانيَ عن آخر تِكّة).
   long off = (long)TimeTradeServer() - (long)TimeGMT();
   off = (long)MathRound(off / 900.0) * 900;
   long exported = (long)TimeGMT();
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('server_offset_s_at_export','" + (string)off + "')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('exported_at_utc','" + (string)exported + "')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('server','" + AccountInfoString(ACCOUNT_SERVER) + "')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('countries','" + InpCountries + "')");

   string codes[];
   int nc = StringSplit(InpCountries, ',', codes);
   if(nc <= 0) { ArrayResize(codes, 1); codes[0] = ""; nc = 1; }

   datetime end_at = TimeTradeServer() + InpDaysAhead * 86400;
   long total = 0, failed = 0;
   for(int c = 0; c < nc && !IsStopped(); c++)
   {
      string code = codes[c];
      StringTrimLeft(code); StringTrimRight(code);
      datetime a = InpFrom;
      long per_country = 0;
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
                  + Esc(ev.source_url) + "," + (string)exported + ")";
               if(DatabaseExecute(db, q)) per_country++;
            }
            DatabaseTransactionCommit(db);
         }
         a = b;
         Comment("تصدير التقويم: ", code, " حتّى ", TimeToString(a, TIME_DATE), " · المحفوظ ", total + per_country);
      }
      total += per_country;
      Print("✓ ", code == "" ? "كلّ الدول" : code, ": ", per_country, " قيمة");
   }
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('rows_written','" + (string)total + "')");
   DatabaseExecute(db, "REPLACE INTO export_meta VALUES('failed_chunks','" + (string)failed + "')");
   DatabaseClose(db);
   Comment("");
   Print("✓ انتهى تصدير التقويم: ", total, " قيمة · أجزاء فاشلة ", failed, " · Common\\Files\\nq_calendar_history.db");
}
