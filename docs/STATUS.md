# STATUS

Oxirgi yangilanish: 2026-10-03
Joriy bosqich: 7 — kod tugadi; birgalikdagi jonli sinov kutilmoqda
Holat: to'xtagan (Docker va Gemini kaliti bilan foydalanuvchi bilan birga ishga tushiriladi)

## Bosqichlar
- [x] 1 — Repo skeleti, CI, EDGAR fetcher, xom saqlash, xesh, ma'lumot modeli (teg: v0.1.0)
- [~] 2 — Extractor, sxema, span provenance, validator — `main`da (PR #4), haqiqiy model bilan sinalmagan
- [~] 3 — Versiyalash, superseding, idempotentlik, review — `main`da (PR #5), haqiqiy model bilan sinalmagan
- [x] 4 — Chunking, embedding, indekslar — `main`da (PR #6), haqiqiy hujjatlarda sinalgan
- [~] 5 — Ilovalar (PR #7), gibrid qidiruv, rerank, javob, sitata tekshiruvi, SSE, kesh (PR #8) — faqat
  soxta model bilan sinalgan
- [~] 6 — Eval harness va oltin to'plam (PR #9) — natija yo'q, jonli ishga tushirilmagan
- [~] 7 — Viewer, bench, README, case study (PR #10) — bench va viewer jonli ishga tushirilmagan

Teglar: v0.2.0 … v0.7.0 jonli sinovdan keyin, natijalar README'ga yozilgach qo'yiladi.

## Jonli sinov tartibi (foydalanuvchi bilan birga)
1. `.env`: `EDGAR_USER_AGENT`, `GEMINI_API_KEY` (va `.claude/settings.json` dagi JSON izohlarini tuzatish).
2. `docker compose up -d --build` → `curl localhost:8000/health`.
3. Demo baza: `python -m anchor.ingest --cik 320193 --limit 5`, `anchor.extract`, `anchor.index`;
   viewer `http://localhost:8000`; `8-K/A` → asl `8-K` faktlari bosilganini tekshirish.
4. Eval: `python -m anchor.evals prepare` (36 hujjat, ~36 LLM chaqiruvi, 6 s pauza),
   `python -m anchor.evals run` (72 savol, ~8 daqiqa pauza bilan).
5. `python -m anchor.bench` (50 000 sintetik vektor, bir necha daqiqa).
6. Natijalarni README "Evaluation" va "Measurements" bo'limlariga, case study'ga, shu faylga yozish;
   CHANGELOG `[Unreleased]` → versiyalar, teglar; Notion'ga progress.

## Xavflar (jonli sinovda birinchi tekshiriladi)
- Gemini `responseJsonSchema` maydonini yoki `gemini-2.5-flash` nomini qabul qilmasligi mumkin —
  `src/anchor/llm.py`, `LLM_MODEL`.
- Bepul tarif chegarasi (daqiqaga/kuniga so'rov) — `--pause` bilan boshqariladi.
- Amazon hujjatlarida `Item` sarlavhalari qator boshida emas — bo'limga sezgir chunker ularni
  "preamble" deb oladi; eval korpusiga kiritilmagan.

## Qabul qilingan qarorlar (TZ dan chetlashishlar)
- `chunk`, `query_log`, `eval_result` keyingi bosqichlarda → docs/decisions/001-defer-ask-tables.md
- Model offset emas, iqtibos qaytaradi → docs/decisions/002-quotes-instead-of-offsets.md
- Lokal CPU embedding, 384 o'lcham (TZ: 1536) → docs/decisions/003-local-cpu-embeddings.md
- Idempotentlik kaliti: hujjat + model nomi + prompt + sxema + matn versiyasi; `force` yo'q.
- Javob oqimi: NDJSON, har da'vo qator tugashi bilan tekshiriladi (TTFT = birinchi tasdiqlangan da'vo).
- Sitata tekshiruvi: iqtibos manbada bo'lishi va da'vodagi har raqam iqtibosda bo'lishi shart.
- Eval korpusi ilovalarsiz (javobsiz savollar ilovalardagi raqamlarni so'raydi); alohida `_eval` baza.
- Indeks tadqiqoti sintetik vektorlarda (haqiqiy korpus juda kichik) — README'da ochiq yozilgan.
- LLM provayderi Gemini (bepul), Celery ishlatilmadi: barcha ishlar idempotent CLI buyruqlari, navbat
  hajmi o'lchanmaguncha qo'shimcha infratuzilma kiritilmaydi (TZ 8-bo'lim).

## O'lchov natijalari
| Metrika | Qiymat | Sana |
|---|---|---|
| Testlar | lokal (bazasiz) ~120 + CI'da hammasi yashil | 2026-10-03 |
| Oltin to'plam | 36 hujjat, 147 maydon, 62 + 10 savol; barcha iqtiboslar matnda topildi | 2026-10-03 |
| Embedding tezligi, bge-small, CPU | 21–25 bo'lak/s (maqsad > 200 — bajarilmadi) | 2026-10-02 |
| Qayta yuklash / qayta indekslash | 0 ish | 2026-10-02 |
| `8-K/A` → asl `8-K` bog'lash | 1/1 to'g'ri | 2026-10-02 |

## Ochiq muammolar
- Maydonlararo tekshiruv (jamlanma = qismlar yig'indisi, TZ 4.4) yo'q.
- `8-K/A` ilovalari asl hujjat ilovalarini bosmaydi (faqat asosiy hujjatlar).
- Docker Desktop xostda RAM kam bo'lganda o'chib qolgan.
