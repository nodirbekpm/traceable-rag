# Anchor

Hujjatlar ustida ishlaydigan, javobini isbotlay oladigan RAG servisi. Portfolio loyihasi.
To'liq talablar: `TZ.md`. Joriy holat: `docs/STATUS.md` — sessiya boshida shuni o'qi.

## Uch va'da (voz kechilmaydi)

1. **Provenance** — har qiymat va sitata manbaning `span_start`/`span_end` oralig'iga olib boradi. Manbada topilmagan qiymat `verified` bo'lmaydi va javobga chiqmaydi.
2. **Versiyalash** — eski natija o'chirilmaydi; yangisi yoziladi, eskisi `is_current = false`. `8-K/A` eskisini `supersedes_id` orqali bosadi.
3. **O'lchov** — aniqlik, sitata to'g'riligi, kechikish, narx raqam bilan README'da.

## Stack

Python 3.12 · FastAPI · PostgreSQL + pgvector · SQLAlchemy 2 + Alembic · Pydantic v2 · Celery + Redis · Docker Compose · pytest · uv · ruff

## Buyruqlar

```bash
uv sync                              # bog'liqliklar
docker compose up -d                 # db, redis, api
uv run alembic upgrade head          # migratsiyalar
uv run pytest -q 2>&1 | tail -30     # testlar (db konteyneri ishlab turishi kerak)
uv run ruff check . && uv run ruff format --check .
uv run python -m anchor.ingest --cik 320193 --limit 5
```

## Kod uslubi

- `src/anchor/` tuzilmasi; tur belgilari hamma joyda; ruff qoidalariga mos
- Kod, izoh, commit, README — inglizcha. Foydalanuvchi bilan muloqot va `docs/STATUS.md` — o'zbekcha
- Tashqi tarmoq testlarda yo'q (`httpx.MockTransport`); baza testlari haqiqiy Postgres'da
- Testni o'tkazish uchun testni o'zgartirma

## Git

- `main` ga to'g'ridan-to'g'ri commit yo'q (`docs/`, `README.md` dan tashqari). Qisqa branch: `feat/`, `fix/`, `refactor/`, `perf/`, `test/`, `chore/`, `docs/`
- Conventional Commits, bitta commit — bitta mantiqiy o'zgarish, kod va testi birga
- Chiziqli tarix: rebase, PR → o'z ko'rigi → `gh pr merge --squash --delete-branch`
- Commit/PR'da hech qanday AI attribution yozilmaydi
- Hech qachon commit qilinmaydi: `.env`, kalitlar, `data/`, dumplar

## Qaror va to'xtash

- Texnik detallarni o'zing hal qil; TZ dan chetlashsang o'lchab ko'rsat va `docs/decisions/NNN-nom.md` yoz
- To'xtab so'ra: uch va'da xavf ostida, soha o'zgarsa, yangi til/infratuzilma, pulli xizmat, ikki urinishda hal bo'lmagan to'siq
- Yangi texnologiya: o'lcha → soddani sina → yetmasa qo'sh → oldin/keyin raqamini README'ga yoz

## Hisobot

Bosqich oxirida o'zbekcha, qisqa: nima qilindi, o'lchov, TZ dan chetlashish, mendan kerak, keyingi. Resurs sarfi ham.

# Compact instructions
Siqishda shularni saqla: joriy bosqich holati, qabul qilingan qarorlar va
o'lchov natijalari. Tashlab yubor: fayllarning to'liq matni, o'tgan test
chiqishlari, muhokama qilingan va rad etilgan variantlar.
