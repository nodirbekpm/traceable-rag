# STATUS

Oxirgi yangilanish: 2026-10-02
Joriy bosqich: 2 — Extractor, Pydantic sxema, span provenance, validator
Holat: boshlanmagan (1-bosqich tugallandi)

## Tugallangan bosqichlar
- [x] 1 — Repo skeleti, CI, EDGAR fetcher, xom saqlash, xesh, ma'lumot modeli, migratsiyalar (teg: v0.1.0)

## Joriy bosqichda qilinganlar
- (hali yo'q)

## Keyingi aniq qadam
- Plan mode'da 2-bosqich rejasi: xom HTML → matn (span'lar aynan qaysi matnga nisbatan hisoblanishini
  hal qilish — xom baytlarmi yoki tozalangan matnmi), `8-K` uchun Pydantic sxema, LLM chaqiruvi,
  qiymatni manbada topuvchi validator.
- LLM provayderi va modeli tanlanadi (pulli — foydalanuvchidan API kalit kerak bo'ladi).

## Qabul qilingan qarorlar (TZ dan chetlashishlar)
- `chunk`, `query_log`, `eval_result` jadvallari 4–6-bosqichlarga qoldirildi; `source_document` ga
  `external_id`, `publisher_id` qo'shildi → docs/decisions/001-defer-ask-tables.md
- Bog'liqliklar `uv` bilan boshqariladi (TZ da ko'rsatilmagan)
- `supersedes_id` ustuni bor, lekin `8-K/A` ni asl hujjatga bog'lash mantig'i 3-bosqichda

## O'lchov natijalari
| Metrika | Qiymat | Sana |
|---|---|---|
| Testlar | 27 o'tdi, ~3 s | 2026-10-02 |
| CI (ruff + pytest) | ~25 s | 2026-10-02 |
| Haqiqiy yuklash, Apple (CIK 320193), 5 hujjat | 1-ishga tushirish: 5 saqlandi; 2-ishga tushirish: 0 saqlandi, 5 o'tkazib yuborildi, 0 yuklab olish | 2026-10-02 |
| Xom saqlash hajmi | 5 hujjat = 256 KB | 2026-10-02 |

## Ochiq muammolar
- `.claude/settings.json` dagi `Read(./.env)` va `Read(./.env.*)` taqiqlari Claude'ga `.env` yaratish va
  `.env.example` ni tahrirlashni ham yopadi. `.env` ni foydalanuvchi o'zi yaratadi; sinovlarda
  `EDGAR_USER_AGENT` qobiq o'zgaruvchisi sifatida beriladi.
- Yuklangan namunada bitta `8-K/A` bor (0001140361-26-035325), lekin u tuzatayotgan asl `8-K` oxirgi
  5 talikda emas — 3-bosqichda superseding namoyishi uchun mos juftlik tanlash kerak.
- Starlette `TestClient` httpx bo'yicha eskirish ogohlantirishi beradi; hozircha zararsiz.
