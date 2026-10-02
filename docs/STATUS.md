# STATUS

Oxirgi yangilanish: 2026-10-02
Joriy bosqich: 1 — Repo skeleti, CI, EDGAR fetcher, xom saqlash, xesh, ma'lumot modeli, migratsiyalar
Holat: to'xtagan (kod tayyor; merge va haqiqiy yuklash foydalanuvchini kutmoqda)

## Tugallangan bosqichlar
- (hali yo'q)

## Joriy bosqichda qilinganlar
- `main`: boshlang'ich commit (LICENSE, hook, CLAUDE.md, TZ.md) — push qilingan
- `chore/project-skeleton`: uv loyihasi, FastAPI `/health`, compose (db, redis, migrate, api), CI — push qilingan
- `feat/data-model` (skeleton ustida): 4 ta Core jadvali, migratsiya `0001`, cheklovlar — push qilingan
- `feat/edgar-fetcher` (data-model ustida): EDGAR mijozi, `RawStore`, `anchor.ingest`, README, CHANGELOG — push qilingan
- Lokal: 27 test yashil, `ruff` toza, `docker compose up` ishlaydi, `/health` = ok

## Keyingi aniq qadam
1. Foydalanuvchi `gh auth login` qiladi va `.env` ga `EDGAR_USER_AGENT` yozadi.
2. Uchta PR ketma-ket: skeleton → data-model → edgar-fetcher. Har biri: `gh pr create --fill`,
   `gh pr diff` bilan ko'rik, CI yashil, `gh pr merge --squash --delete-branch`.
   Branch'lar ustma-ust qurilgan: har squash'dan keyin keyingisini
   `git rebase --onto main <oldingi-branch-uchi> <branch>` va `git push --force-with-lease`.
3. Haqiqiy yuklash: `docker compose run --rm api python -m anchor.ingest --cik 320193 --limit 5`,
   ikkinchi marta ishga tushirib `stored=0` ekanini tekshirish. Raqamlarni shu faylga yozish.
4. `git tag -a v0.1.0`, `git push --tags`, Notion sahifasiga progress.
5. Keyin 2-bosqich: extractor, Pydantic sxema, span provenance, validator.

## Qabul qilingan qarorlar (TZ dan chetlashishlar)
- `chunk`, `query_log`, `eval_result` jadvallari 4–6-bosqichlarga qoldirildi; `source_document` ga
  `external_id`, `publisher_id` qo'shildi → docs/decisions/001-defer-ask-tables.md
- Bog'liqliklar `uv` bilan boshqariladi (TZ da ko'rsatilmagan)
- `supersedes_id` ustuni bor, lekin `8-K/A` ni asl hujjatga bog'lash mantig'i 3-bosqichda

## O'lchov natijalari
| Metrika | Qiymat | Sana |
|---|---|---|
| Testlar | 27 o'tdi, ~3 s | 2026-10-02 |

## Ochiq muammolar
- `.claude/settings.json` dagi `Read(./.env.*)` taqiqi `.env.example` ni ham yopadi — Claude uni tahrir
  qila olmaydi. Fayldagi bo'sh qiymatlar zararsiz (`env_ignore_empty`), lekin yangi o'zgaruvchi
  qo'shish kerak bo'lsa foydalanuvchi qo'lda qo'shadi yoki taqiq `Read(./.env)` gacha toraytiriladi.
- CI hali GitHub'da ishlamagan (PR ochilmagan) — birinchi PR'da tekshiriladi.
- Starlette `TestClient` httpx bo'yicha eskirish ogohlantirishi beradi; hozircha zararsiz.
