//+------------------------------------------------------------------+
//| NQ_StocksSync.mq5 — أسعار أكبر شركات الناسداك كلّ دقيقة (قراءة فقط)
//|
//| أمر المالك ٢٠٢٦-١٠-٠٨ (ختم «NQ» — «المعرفة أوّلًا»): «بس بميتاتريدر في كلّ الأسهم موجودة».
//| لماذا: سي‑تريدر (المصدر الحيّ) بلا أسهم، فالنظام أعمى عن الشركات التي تحمل حركة المؤشّر —
//| إن هبط سهم أبل 5٪ لا يعرف حتّى يظهر في سعر الناسداك نفسه. وميتاتريدر عند الوسيط فيه عقودها.
//|
//| ⛔ إكسبرت قراءةٍ لا تداول: لا أوامر ولا تعديل حساب ولا مراكز. يضيف رموز الشركات إلى «مراقبة السوق»
//|    (SymbolSelect) ليقرأ أسعارها، ويكتب كلّ دقيقة في قاعدةٍ منفصلة Common\Files\nq_stocks.db
//|    تقرؤها ذرّة «معرفة الشركات» 122 للقراءة فقط. يُركَّب على شارتٍ منفصل (لا شارت إكسبرت التداول).
//+------------------------------------------------------------------+
#property copyright "QUANT_NQ"
#property version   "1.00"

// أكبر أوزان الناسداك، ثمّ مؤشّر الخوف ومؤشّر الدولار (أمر المالك: «في فيكس وفي دي إكس واي كمان على ميتاتريدر»).
// البدائل بـ| : أوّلها اسم المرجع في القاعدة، وأيّها وُجد عند الوسيط يُقرأ.
input string InpTickers      = "NVDA,MSFT,AAPL,AMZN,AVGO,META,GOOGL,GOOG,TSLA,COST,NFLX,AMD,PLTR,CSCO,TMUS,VIX|VIXX|UVXY,DXY|USDX|USDIDX|DX";
input int    InpEverySeconds = 60;   // كلّ كم ثانية تُكتب الأسعار

string g_tickers[];
string g_symbols[];   // اسم الرمز عند الوسيط لكلّ شركة ("" = لم يُعثر عليه)

string Esc(string s) { StringReplace(s, "'", "''"); return "'" + s + "'"; }
string Num(double v)  { if(v == 0.0 || !MathIsValidNumber(v)) return "NULL"; return DoubleToString(v, 6); }

// الرمز عند الوسيط: الاسم نفسه، أو الاسم ثمّ فاصل ولاحقة (مثل .NAS أو .NAS-24 أو _Z6) — والناسداك أوّلًا.
// ٢٠٢٦-١٠-٠٨: الخوف والدولار عند الوسيط **عقودٌ آجلة** (VIX_V6 · DXY_Z6) — فمن العقود يُختار **أقرب عقدٍ لم ينتهِ**
// (أقلّ تاريخ انتهاء بعد الآن)، لا أوّل ما يُوجد، حتّى لا يُمسك عقدٌ منتهٍ بعد التدوير. والأسهم بلا انتهاء.
string FindOne(string ticker)
{
   string best = "";
   long best_exp = 0;
   datetime now = TimeTradeServer();
   int total = SymbolsTotal(false);
   for(int i = 0; i < total; i++)
   {
      string name = SymbolName(i, false);
      string up = name; StringToUpper(up);
      if(up == ticker) return name;
      if(StringFind(up, ticker + ".") == 0 || StringFind(up, ticker + "_") == 0 || StringFind(up, ticker + "-") == 0)
      {
         if(StringFind(up, "NAS") >= 0) return name;
         long exp = SymbolInfoInteger(name, SYMBOL_EXPIRATION_TIME);
         if(exp > 0 && exp <= (long)now) continue;                       // عقدٌ منتهٍ
         if(best == "" || (exp > 0 && (best_exp == 0 || exp < best_exp))) { best = name; best_exp = exp; }
      }
   }
   return best;
}

// البدائل «أ|ب|ج»: أوّل ما يوجد منها عند الوسيط.
string FindBrokerSymbol(string aliases)
{
   string parts[];
   int n = StringSplit(aliases, '|', parts);
   for(int i = 0; i < n; i++)
   {
      StringTrimLeft(parts[i]); StringTrimRight(parts[i]); StringToUpper(parts[i]);
      string found = FindOne(parts[i]);
      if(found != "") return found;
   }
   return "";
}

int OnInit()
{
   int n = StringSplit(InpTickers, ',', g_tickers);
   ArrayResize(g_symbols, n);
   for(int i = 0; i < n; i++)
   {
      StringTrimLeft(g_tickers[i]); StringTrimRight(g_tickers[i]); StringToUpper(g_tickers[i]);
      string aliases = g_tickers[i];
      int bar = StringFind(aliases, "|");
      if(bar > 0) g_tickers[i] = StringSubstr(aliases, 0, bar);   // اسم المرجع في القاعدة = أوّل البدائل
      g_symbols[i] = FindBrokerSymbol(aliases);
      if(g_symbols[i] != "") SymbolSelect(g_symbols[i], true);
      Print(g_tickers[i], " ⟵ ", g_symbols[i] == "" ? "غير موجود عند الوسيط" : g_symbols[i]);
   }
   EventSetTimer(MathMax(10, InpEverySeconds));
   Sync();
   return INIT_SUCCEEDED;
}

void OnDeinit(const int reason) { EventKillTimer(); Comment(""); }
void OnTimer()
{
   // كلّ ساعة يُعاد اختيار العقود الآجلة (تدوير الخوف والدولار) — الأسهم لا تتغيّر.
   static int ticks = 0;
   if(++ticks * MathMax(10, InpEverySeconds) >= 3600)
   {
      ticks = 0;
      string aliases[];
      int n = StringSplit(InpTickers, ',', aliases);
      for(int i = 0; i < n && i < ArraySize(g_symbols); i++)
      {
         StringTrimLeft(aliases[i]); StringTrimRight(aliases[i]); StringToUpper(aliases[i]);
         string found = FindBrokerSymbol(aliases[i]);
         if(found != "" && found != g_symbols[i]) { g_symbols[i] = found; SymbolSelect(found, true); Print(g_tickers[i], " ⟵ ", found); }
      }
   }
   Sync();
}

void Sync()
{
   int db = DatabaseOpen("nq_stocks.db", DATABASE_OPEN_READWRITE | DATABASE_OPEN_CREATE | DATABASE_OPEN_COMMON);
   if(db == INVALID_HANDLE) { Print("✘ تعذّر فتح القاعدة: ", GetLastError()); return; }
   DatabaseExecute(db, "CREATE TABLE IF NOT EXISTS stock_quotes ("
      "ticker TEXT PRIMARY KEY, broker_symbol TEXT, bid REAL, ask REAL, last REAL, tick_time_utc INTEGER, "
      "day_open REAL, day_high REAL, day_low REAL, prev_close REAL, day_bar_server INTEGER, written_at_utc INTEGER)");
   DatabaseExecute(db, "CREATE TABLE IF NOT EXISTS stocks_meta (key TEXT PRIMARY KEY, value TEXT)");

   long off = (long)TimeTradeServer() - (long)TimeGMT();
   off = (long)MathRound(off / 900.0) * 900;
   long now_utc = (long)TimeGMT();
   int found = 0, written = 0;
   DatabaseTransactionBegin(db);
   for(int i = 0; i < ArraySize(g_tickers); i++)
   {
      string sym = g_symbols[i];
      if(sym == "")
      {
         DatabaseExecute(db, "REPLACE INTO stock_quotes(ticker, broker_symbol, written_at_utc) VALUES("
                         + Esc(g_tickers[i]) + ",''," + (string)now_utc + ")");
         continue;
      }
      found++;
      MqlTick t;
      if(!SymbolInfoTick(sym, t)) continue;
      MqlRates d[];
      ArraySetAsSeries(d, true);
      int nd = CopyRates(sym, PERIOD_D1, 0, 2, d);
      double day_open = nd >= 1 ? d[0].open : 0.0, day_high = nd >= 1 ? d[0].high : 0.0;
      double day_low = nd >= 1 ? d[0].low : 0.0, prev_close = nd >= 2 ? d[1].close : 0.0;
      long day_bar = nd >= 1 ? (long)d[0].time : 0;
      long tick_utc = (long)t.time - off;   // وقت التِّكّة بوقت الخادم ⟸ غرينتش
      string q = "REPLACE INTO stock_quotes VALUES(" + Esc(g_tickers[i]) + "," + Esc(sym) + ","
         + Num(t.bid) + "," + Num(t.ask) + "," + Num(t.last) + "," + (string)tick_utc + ","
         + Num(day_open) + "," + Num(day_high) + "," + Num(day_low) + "," + Num(prev_close) + ","
         + (string)day_bar + "," + (string)now_utc + ")";
      if(DatabaseExecute(db, q)) written++;
   }
   DatabaseTransactionCommit(db);
   DatabaseExecute(db, "REPLACE INTO stocks_meta VALUES('written_at_utc','" + (string)now_utc + "')");
   DatabaseExecute(db, "REPLACE INTO stocks_meta VALUES('server_offset_s','" + (string)off + "')");
   DatabaseExecute(db, "REPLACE INTO stocks_meta VALUES('tickers_found','" + (string)found + "')");
   DatabaseExecute(db, "REPLACE INTO stocks_meta VALUES('tickers_written','" + (string)written + "')");
   DatabaseExecute(db, "REPLACE INTO stocks_meta VALUES('server','" + AccountInfoString(ACCOUNT_SERVER) + "')");
   DatabaseClose(db);
   Comment("أسعار الشركات: ", written, " من ", ArraySize(g_tickers), " · ", TimeToString(TimeGMT(), TIME_MINUTES), " غرينتش");
}
