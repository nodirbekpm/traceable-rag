# ANCHOR — TZ
### Traceable RAG over Documents

> Portfolio loyihasi №1. Muallif: Nodirbek Eshnazarov.
> Ishchi nom: **Anchor**. Nom bo'yicha qaror ochiq (14-bo'lim).
> Manba: Upwork'dagi 6 ta zakas tahlili.

---

# 1. MUAMMO

Hujjatlar ustida ishlaydigan AI tizimlar ikki turga bo'linadi, ikkalasi ham bir xil kasallikka chalingan.

**Ekstraksiya tizimlari.** Hujjatdan raqam ajratib bazaga yozadi. Bir haftada prototip ishlaydi. Produksiyada to'rt savol paydo bo'ladi, javob yo'q:

- Dashboarddagi bu raqam qaysi hujjatning qaysi jumlasidan olindi?
- Hujjat ikki marta qayta ishlansa — bazada ikkita yozuv, qaysi biri to'g'ri?
- Kompaniya e'lonni tuzatib qayta chiqarsa, eski raqam nima bo'ladi?
- Model yangilansa, 10 000 ta eski yozuv nima bo'ladi? Va yangi model haqiqatan aniqroqmi?

**RAG tizimlari.** Demo ajoyib ishlaydi. Produksiyada:

- Javobdagi raqam noto'g'ri chiqadi va buni hech kim payqamaydi — javob ishonchli ohangda yozilgan
- "Rule 12.4", "$4.2M" kabi aniq belgilarni topa olmaydi — vektor qidiruv raqamlarni yomon topadi
- Javob 8 soniyada keladi, foydalanuvchi ketib qolgan
- Hujjat yangilansa, eski javoblar noto'g'ri bo'lib qoladi, buni bilish yo'li yo'q
- "Aniqligi qancha?" degan savolga javob yo'q — o'lchov qurilmagan

**Ildiz bitta:** LLM chiqishi oddiy matn sifatida qabul qilinadi. Aslida u **dalil** — manbasi, versiyasi, ishonch darajasi va o'lchangan aniqligi bo'lishi shart.

## Bozor dalili

| Zakas | Nima deyilgan |
|---|---|
| Mineral Metrics ($500, Expert) | provenance, dublikat, tuzatilgan e'lon, yangi model bilan qayta ishlash — 5 savoldan 3 tasi |
| AI RAG Engine (ongoing) | "noto'g'ri javoblarni yozib borish usulim bor... keyingi qadamni bilmayman" |
| Scraping Infrastructure (senior) | jim nosozliklar, idempotentlik, sifat tekshiruvi |
| Django RAG Integration | RAG, pgvector, validatsiya, logging |

---

# 2. LOYIHA NIMA

**Anchor** — hujjatlar ustida ishlaydigan, javobini isbotlay oladigan RAG servisi.

Uch xususiyati bilan ajraladi:

1. **Har bir raqam manbasiga mixlangan.** Javobdagi qiymat bosiladi, hujjatning aynan o'sha jumlasi yoritiladi. Model qaytargan qiymat manba matnida topilmasa — javobga umuman chiqmaydi.
2. **Tezligi o'lchangan va byudjetlangan.** Retrieval p95 < 150 ms, birinchi belgi < 1.5 s, javob oqim bilan. Maqsadlar README'da raqam bilan turadi.
3. **Aniqligi raqam bilan aytiladi.** "Ishlaydi" emas — "137 maydonda 94.2% aniqlik, recall@5 = 0.91, sitata to'g'riligi 97%, so'rovga $0.004".

| Qatlam | Nima qiladi |
|---|---|
| **Anchor Core** | hujjat → strukturalangan, versiyalangan, provenance'li ma'lumot |
| **Anchor Ask** | savol → gibrid qidiruv → isbotlangan javob |

Ikkinchisi birinchisiz ishlamaydi. Aynan shu bog'lanish odatiy RAG demolaridan farq qiladi.

**Ramka:** bu kompaniya yoki platforma emas — **servis**. Bitta servis ichida ko'p og'riqni hal qiladi.

---

# 3. QAYERDA ISHLATILADI

| Soha | Hujjat | Savol |
|---|---|---|
| Moliya / investitsiya | kompaniya e'lonlari, hisobotlar | "Q3 daromadi qancha va qayerda yozilgan?" |
| Tog'-kon, energetika | resurs hisobotlari | "zaxira hajmi qaysi hisobotda o'zgardi?" |
| Yuridik | shartnomalar | "bekor qilish sharti nima?" |
| Sport, tartibnoma | qoidalar kitobi | "bu harakat qoidaga to'g'ri keladimi?" |
| Ta'lim / universitet | ichki hujjatlar, nizomlar, baza | "talaba va xodim ma'lumotni qayerdan topadi?" |
| Davlat xaridlari | tender hujjatlari | "budjet va muddat qancha?" |

## Namoyish sohasi: SEC EDGAR (+ istalgan hujjat)

> **O'zgartirildi 2026-10-03** (docs/decisions/004-any-document.md): EDGAR namoyish va o'lchov
> korpusi bo'lib qoladi, lekin servis foydalanuvchi yuklagan istalgan hujjatni (PDF, DOCX, HTML,
> TXT, MD) ham tahlil qiladi. Sabab: portfolio ko'ruvchisi o'z hujjatini sinab ko'rmoqchi bo'ladi;
> faqat bitta soha "servis" emas, demo bo'lib ko'rinadi.

- **Bepul va rasmiy API** — skraping urushi yo'q, huquqiy savol yo'q
- **Tuzatishlar rasmiy mavjud** — `8-K` va tuzatilgan versiyasi `8-K/A`. "Hujjat keyinroq tuzatildi" ssenariysi haqiqiy ma'lumotda ko'rsatiladi, sun'iy misolda emas
- **Strukturasi bor** — `Item 2.02`, `Item 5.02` bo'limlari → bo'limga sezgir chunking sinaladi
- **Raqamlar muhim** — noto'g'ri ajratilsa ko'rinadi
- **G'arb mijozi darhol tanidi** — "EDGAR" tushuntirish talab qilmaydi

---

# 4. FUNKSIONAL TALABLAR

## QATLAM A — ANCHOR CORE

### 4.1 Yig'ish
- EDGAR API'dan `8-K` va `8-K/A` hujjatlari
- Xom hujjat o'zgarishsiz saqlanadi — qayta yuklab olishga hojat qolmasin
- Kontentdan barqaror xesh

### 4.2 Ajratish va provenance
- LLM'ga Pydantic sxemadan yaratilgan JSON Schema beriladi, faqat JSON qaytaradi
- **Har bir qiymat bilan birga model manba oralig'ini qaytarishi shart**
- Saqlanadi: hujjat ID, `span_start`/`span_end`, manba parchasi, model va prompt versiyasi, vaqt, narx
- **Qattiq qoida:** qaytarilgan qiymat manba matnida topilmasa — gallyutsinatsiya deb belgilanadi, `verified` holatida yozilmaydi

### 4.3 Idempotentlik, versiyalash, tuzatishlar
- Kalit: `content_hash + prompt_version + model_version`. Mos kelsa qayta ajratilmaydi
- Versiya o'zgarsa yangi `extraction_run`
- **Eski natija hech qachon o'chirilmaydi** — yangisi yoziladi, eskisi `is_current = false`
- `8-K/A` o'zi tuzatayotgan hujjatga bog'lanadi (`supersedes_id`), undan chiqqan qiymatlar eskisini bosadi
- Har doim javob bor: "bu raqam olti oy oldin qanday edi va nega o'zgardi?"

### 4.4 Validatsiya va inson nazorati
- Tur va format (Pydantic), birlik normallashtirish (`$4.2M`, `4,200,000 USD`, `4.2 million` → bitta ko'rinish)
- Diapazon va maydonlararo tekshiruv (jamlanma qismlar yig'indisiga tengmi)
- Ishonch darajasi = model ishonchi + validatsiya natijasi + provenance topildimi
- Chegaradan pastlari avtomatik qabul qilinmaydi → ko'rib chiqish navbati

## QATLAM B — ANCHOR ASK

### 4.5 Chunking
Kamida uch strategiya qurilib **taqqoslanadi**: belgilangan o'lcham + qoplama (bazaviy) · jumla oynasi · **bo'limga sezgir** (EDGAR `Item` chegaralari).

Har bo'lak o'z manba oralig'ini saqlaydi — javobdan hujjatgacha yo'l uzilmaydi.

### 4.6 Gibrid qidiruv
- **pgvector** — ma'no bo'yicha (HNSW indeks)
- **PostgreSQL `tsvector` + GIN** — kalit so'z va aniq belgilar (`8-K`, `Item 2.02`, `$4.2M`)
- Natijalar birlashtiriladi (RRF yoki og'irlikli), keyin reranking

Sabab: sof vektor qidiruv raqam va kodlarni yomon topadi, sof matn qidiruvi ma'noni tushunmaydi.

**Uchalasi o'lchanadi:** faqat vektor / faqat matn / gibrid — bir xil test to'plamida.

### 4.7 Javob berish
- Reranking bosqichi (cross-encoder yoki LLM-based, taqqoslanadi)
- Javob **oqim bilan** (streaming)
- Har bir da'vo yoniga sitata: hujjat, bo'lim, belgi oralig'i
- **Sitata tekshiriladi** — ko'rsatilgan oraliq da'voni qo'llab-quvvatlaydimi. Yo'q bo'lsa, da'vo olib tashlanadi
- Javob topilmasa — **"topilmadi" deyiladi** (o'lchanadigan xususiyat)
- Takroriy so'rovlar uchun Redis kesh

### 4.8 Tezlik byudjeti

| Bosqich | Maqsad |
|---|---|
| Retrieval (rerank'gacha) | p95 < 150 ms |
| Reranking | p95 < 100 ms |
| Birinchi belgi (TTFT) | < 1.5 s |
| Kesh urgani | < 50 ms |
| Embedding (batch) | > 200 bo'lak/soniya |

Har biri o'lchanadi, README'da p50/p95 bilan yoziladi. **Maqsadga yetmagani ham yoziladi** — bu halollik belgisi.

## UMUMIY

### 4.9 O'lchov quvuri (eval harness) — farqlanish nuqtasi

Uch oltin to'plam, bitta buyruq bilan ishga tushadi.

**Ekstraksiya** (25+ hujjat, 100+ maydon): maydon aniqligi · provenance to'g'riligi · gallyutsinatsiya darajasi · hujjatiga narx va vaqt

**Retrieval** (60+ savol): recall@5, recall@10, MRR · vektor/matn/gibrid taqqoslanadi · chunking strategiyalari taqqoslanadi

**Javob** (60+ savol, shundan 10 tasi javobi yo'q): javob aniqligi · sitata to'g'riligi · **rad etish darajasi** — javobi yo'q savolga to'g'ri "topilmadi" dedimi yoki o'ylab topdimi

Har prompt, model yoki parametr o'zgarishida qayta ishga tushadi. Natijalar tarixi bazada — regressiya ko'rinadi.

**Bu bo'lim loyihaning yuragi.** Usiz Anchor yana bitta RAG demosi.

### 4.10 Monitoring va jim nosozliklar
- Manba bo'yicha kutilgan hajm kuzatiladi
- Anomaliyalar: `null` ulushi keskin oshsa, hujjat hajmi keskin o'zgarsa, retrieval bo'sh qaytarsa, "topilmadi" javoblari ko'paysa

### 4.11 Viewer (minimal, ko'rgazmali)
Bitta sahifa: chapda hujjat matni (ajratilgan va sitata qilingan joylar rangli) · o'ngda javob va strukturalangan jadval · javobdagi raqamga bosilsa chapda mos jumla yoritiladi · yon panel: model versiyasi, ishonch darajasi, versiyalar tarixi, kechikish bosqichma-bosqich.

Bu sahifaning skrinshoti portfolio'dagi eng kuchli rasm bo'ladi.

---

### 4.12 Istalgan hujjatni yuklash (2026-10-03 da qo'shildi)
- Formatlar: PDF (matn qatlami bor), DOCX, HTML, TXT, MD; 25 MB gacha
- Yuklangach **tahlil boshlanmaydi**: avval taxmin ko'rsatiladi — sahifa, so'z, model chaqiruvlari,
  vaqt (soniyada) va narx. Vaqt shu o'rnatmaning o'z tarixidan o'lchanadi (avvalgi run'lar), tarix
  bo'lmasa standart qiymat; bepul tarif chegarasi kutishlari ham qo'shiladi
- Foydalanuvchi tasdiqlasa — fonda tahlil, jarayon foizi va qadam nomi ko'rsatiladi
- Uzun hujjat qismlarga bo'linib o'qiladi; iqtiboslar butun matnda qidiriladi, provenance buzilmaydi
- Yuklangan hujjatlar uchun umumiy maydonlar: sana, kuchga kirish, muddat, summa, foiz, tomon,
  shaxs, joy, davomiylik (`schema g1`); EDGAR hujjatlari 8-K maydonlarida qoladi (`s1`)
- Savolni bitta hujjat bilan cheklash mumkin
- Skanerlangan PDF (OCR) kirmaydi — matn topilmasa aniq xabar beriladi
- Yuklangan faylning yangi versiyasi va versiyalar farqi; foydalanuvchi o'z yuklagan faylini
  o'chira oladi, EDGAR hujjatlari o'chirilmaydi (docs/decisions/005)

# 5. ARXITEKTURA

```
EDGAR API
    │
    ▼
[ fetcher ] ──► xom hujjat (blob + xesh)
    │
    ▼
[ Celery navbat ] ── idempotentlik: xesh + prompt_v + model_v
    │
    ├──────────────────────────────┐
    ▼                              ▼
[ extractor ]                 [ chunker ]
 LLM + sxema + span'lar        3 strategiya
    │                              │
    ▼                              ▼
[ validator ]                 [ embedder ] ── batch
 tur, birlik, diapazon,            │
 provenance tekshiruvi             ▼
    │                         pgvector (HNSW)
    ├─► past ishonch          tsvector (GIN)
    │   ──► review_queue           │
    ▼                              │
[ PostgreSQL ] ◄───────────────────┘
 versiyalangan faktlar, audit trail, bo'laklar, indekslar
    │
    ├──► [ Anchor Ask ] ── gibrid qidiruv → rerank → LLM → sitata tekshiruvi → streaming
    │         └── Redis kesh
    ├──► FastAPI (o'qish API)
    ├──► viewer (bitta sahifa)
    └──► eval harness ──► metrikalar + tarix
```

**Stack:** Python 3.12 · FastAPI · **PostgreSQL + pgvector** · SQLAlchemy + Alembic · Pydantic v2 · Celery + Redis · OpenAI yoki Anthropic API · Docker Compose · pytest · locust

**Bepul stack sharti:** loyiha to'liq bepul vositalarda ishlashi, lekin professional darajada bo'lishi kerak (LLM API'dan tashqari). Yechim mashinaga moslashsin — foydalanuvchi kompyuteriga qarab mos profilni ishlatsin, bitta qattiq profil emas.

---

# 6. MA'LUMOT MODELI (skelet)

```
source_document
  id · source_url · doc_type · publisher · published_at
  retrieved_at · content_hash · raw_path
  supersedes_id → source_document.id        (8-K/A → 8-K)

extraction_run
  id · document_id · model_name · model_version
  prompt_version · schema_version · chunk_strategy
  started_at · finished_at · status
  token_input · token_output · cost_usd

extracted_fact
  id · run_id · document_id · entity_id
  field_name · value_raw · value_normalized · unit
  span_start · span_end · source_excerpt
  confidence · validation_status
  is_current · superseded_by → extracted_fact.id

chunk
  id · document_id · chunk_strategy · ordinal
  text · span_start · span_end
  embedding vector(1536) · tsv tsvector

query_log
  id · question · retrieved_chunk_ids · answer
  citations · latency_retrieval_ms · latency_rerank_ms
  latency_ttft_ms · latency_total_ms · cost_usd · cache_hit

eval_result
  id · suite (extraction|retrieval|answer) · run_config · executed_at
  metrics jsonb · avg_cost · p50_ms · p95_ms

review_queue
  id · fact_id · reason · created_at · resolved_at · resolution
```

---

# 7. POSTGRESQL MUHANDISLIGI

Loyihaning og'irlik markazi Python'da emas, **bazada**. "Faqat Python bilaman" taassurotini yo'q qiladigan yagona narsa — so'rov rejasini o'qiy olish.

Qilinadi va hujjatlashtiriladi:

- **HNSW va IVFFlat taqqoslanadi** — `m`, `ef_construction`, `ef_search` va `lists`, `probes` bilan. Har biri uchun: indeks qurish vaqti, hajmi, recall, p95 kechikish
- **`EXPLAIN (ANALYZE, BUFFERS)` chiqishlari README'da** — oldin va keyin
- **Partial indeks** — `WHERE is_current = true`. Nega kerak, qancha tejadi
- **Gibrid so'rov rejasi** — vektor va matn qidiruvi bitta so'rovda birlashganda planner nima qiladi
- **Bog'lanish hovuzi** — parametrlari va yuklama ostidagi ta'siri
- **`VACUUM` va indeks shishishi** — takroriy qayta ishlashdan keyin

Yakuniy natija: bitta jadval — "qaysi o'zgarish p95 ni necha ms ga tushirdi".

---

# 8. TEXNOLOGIYA QO'SHISH QOIDASI

Yangi texnologiya (boshqa til, gRPC, Kafka, Elasticsearch, alohida servis) **taqiqlanmagan**. Faqat bitta yo'l bilan kiradi:

1. **O'lcha.** Bo'g'iz raqam bilan nomlanadi
2. **Sodda yechimni avval sina** — indeks, kesh, batch, so'rovni qayta yozish, `N+1` ni yo'qotish
3. **Yetmasa — yangi texnologiya, faqat o'sha bo'g'iz uchun**
4. **Oldin/keyin raqamini README'ga yoz**

Sababsiz qo'shilgan texnologiya portfolio'da kuch emas, zaiflik bo'lib ko'rinadi. Sabab bilan qo'shilgani esa eng kuchli dalil.

| Texnologiya | Qachon kiradi |
|---|---|
| **gRPC** | Embedding servisi ajratilgan va HTTP/JSON qatlami o'lchangan ortiqcha yuk bersa (masalan bo'lakka 8 ms serializatsiya). Tejagan ms yoziladi |
| **Go yoki Rust servisi** | Tokenizatsiya yoki embedding tayyorlash Python'da o'lchangan bo'g'iz bo'lsa. "400 ms edi → 90 ms bo'ldi" — bu dalil |
| **Kafka** | Navbat chuqurligi o'lchangan holda Celery+Redis ko'tara olmasa. 10 hujjat/soniyada kerak emas |
| **Elasticsearch** | PostgreSQL `tsvector` recall'i o'lchangan holda yetarli bo'lmasa. Avval GIN indeks va so'rov sozlamalari |
| **Kubernetes** | Bu loyihada kirmaydi. Bitta node, `docker compose` |

Har bir kiritilgan texnologiya uchun README'da blok: **muammo → o'lchov → muqobillar → tanlov → natija.** Bu bloklar mijoz uchun kod sifatidan qimmatliroq — fikrlash usulini ko'rsatadi.

---

# 9. NIMA KIRMAYDI

- Foydalanuvchi autentifikatsiyasi, ko'p ijarachi — keyingi masala
- React yoki boshqa frontend freymvork (bitta HTML sahifa yetadi)
- Model fine-tuning
- ~~Bir nechta soha (faqat EDGAR)~~ — bekor qilindi, 4.12 ga qarang
- OCR (skanerlangan PDF)
- Kubernetes, avtomatik miqyoslash
- Agent'lar, ko'p qadamli reja tuzish
- Real vaqt oqimi (batch yetadi)

---

# 10. BOSQICHLAR

Bosqichli MVP — qat'iy ketma-ketlik emas. Har bosqich oxirida repo **ishlaydigan holatda** bo'lishi shart; yarim tugagan branch qolmaydi.

| # | Bosqich | Taxminiy soat |
|---|---|---|
| 1 | Repo skeleti, CI, EDGAR fetcher, xom saqlash, xesh, ma'lumot modeli, migratsiyalar | 7 |
| 2 | Extractor, Pydantic sxema, span provenance, validator | 8 |
| 3 | Versiyalash, superseding, idempotentlik, review navbati | 7 |
| — | **▼ MVP KESIMI — shu yergacha Anchor Core ishlaydi va ko'rsatsa bo'ladi** | |
| 4 | Chunking (3 strategiya), embedding, pgvector + tsvector indekslar | 8 |
| 5 | Gibrid qidiruv, reranking, javob qatlami, sitata tekshiruvi, streaming, kesh | 7 |
| 6 | Eval harness: uch oltin to'plam, metrikalar, taqqoslash jadvallari | 7 |
| 7 | Tezlik sozlash (`EXPLAIN`, indeks parametrlari), viewer, README, case study | 6 |

Jami ~50 soat. Kalendar sanasi qo'yilmagan — bosqich tugaganda keyingisi boshlanadi.

---

# 11. MUVAFFAQIYAT MEZONI

1. `docker compose up` — begona odam 10 daqiqada ishga tushiradi
2. Ekstraksiya: **100+ maydon** o'lchangan, **provenance to'g'riligi ≥ 95%**
3. Retrieval: **60+ savol**, uch qidiruv turi taqqoslangan, gibrid eng yaxshisi ekani raqam bilan ko'rsatilgan
4. Javob: **sitata to'g'riligi ≥ 95%**, javobi yo'q savollarda **rad etish ≥ 90%**
5. Tezlik: retrieval **p95 < 150 ms**, TTFT **< 1.5 s** — yoki yetmagani sababi bilan yozilgan
6. Tuzatish ssenariysi haqiqiy `8-K/A` da namoyish etilgan, tarix to'liq ko'rinadi
7. Kamida **uchta muhandislik qarori** README'da "muammo → o'lchov → muqobillar → tanlov → natija" formatida

---

# 12. NATIJALAR

1. **GitHub repo** — toza tarix, `docker compose up` bilan ishga tushadi
2. **README** — muammo, arxitektura, ma'lumot modeli, uch eval jadvali, tezlik jadvali, texnologiya qarorlari bloklari
3. **Eval hisoboti** — chunking, qidiruv turi va model bo'yicha taqqoslash
4. **Tezlik hisoboti** — bosqichma-bosqich p50/p95, oldin/keyin
5. **Skrinshotlar (4 ta)** — yoritilgan javob va sitata, versiyalar tarixi, eval hisoboti, `EXPLAIN` taqqoslashi
6. **Case study (EN, ~400 so'z)** — sayt va Upwork uchun
7. **Upwork portfolio yozuvi** — sarlavha ~37 belgi, tavsif ~300 belgi

---

# 13. BU QANDAY SOTADI

Mineral Metrics zakasidagi beshta skrining savoli:

| Savol | Javob |
|---|---|
| Hujjatni strukturali yozuvga aylantirgan tizim — shaxsan nima qurdingiz? | Anchor. To'liq o'zim. Repo, arxitektura, o'lchangan natija |
| AI ajratgan raqamning provenance'ini qanday saqlaysiz? | Belgi oralig'i + manba parchasi + model va prompt versiyasi. Manbada topilmasa yozilmaydi. Mana viewer |
| Hujjat ikki marta ishlansa, tuzatilsa, yangi model bilan qayta ishlansa? | Xesh + versiya kaliti bo'yicha idempotentlik. Eski yozuv o'chmaydi. Haqiqiy `8-K/A` misolida |
| Qayta qurmasdan yaxshilangan tizim? | *(alohida javob kerak — mavjud ishlardan)* |
| Birinchi soatlarda nimani tekshirardingiz? | Provenance bormi, idempotentlik bormi, eval to'plami bormi. Uchtasi yo'q bo'lsa muammo shu yerda |

Sport RAG turidagi mijozga bitta jumla yetadi: *"Muammoyingiz retrieval'dami yoki generatsiyadami — buni o'lchamasdan bilib bo'lmaydi. Men shuni o'lchaydigan tizim qurganman, mana natijalari."*

**Asosiy natija:** Anchor tugagach "Python backend qila olaman" degan mingta odamdan biri emassiz. **LLM chiqishiga qanday ishonish mumkinligini o'lchab ko'rsatgan** odamsiz. Bozorda bunisi kam.

---

# 14. OCHIQ QARORLAR

- **Nom.** Ishchi nom `anchor`. Repo nomi uchun tavsiya: `traceable-rag`. Muqobillar: `provenant`, `sourcebound`, `factspan`. GitHub'da bandligini tekshirish kerak
- **4-savol** ("qayta qurmasdan yaxshilangan tizim") Anchor bilan yopilmaydi — mavjud ishlardan alohida javob kerak

---

# 15. BOG'LIQ HUJJATLAR

- Notion TZ sahifasi: https://app.notion.com/p/3ede13bf66e2819faac4ea09d5b18974
- Audit hujjati: https://claude.ai/code/artifact/a7118dda-8a28-411d-a04d-c91bec392435
- Servis dizayni: https://claude.ai/code/artifact/61c2ca22-c25e-4440-847d-0d2c6ca09685

Har bosqich oxirida progress Notion sahifasiga yoziladi — case study oxirida noldan yozilmasin, jarayonda yig'ilsin.
