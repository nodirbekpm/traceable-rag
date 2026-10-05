# 005. Yuklangan hujjat: yangi versiya va o'chirish
Sana: 2026-10-05 | Holat: qabul qilindi

## Muammo
Foydalanuvchi yuklagan faylini tahrirlab qayta yuklashi (yangi versiya) va o'chirishi kerak.
Yangi versiya — versiyalash va'dasining aynan o'zi. O'chirish esa "eski natija hech qachon o'chirilmaydi"
va'dasiga zid ko'rinadi.

## Ko'rib chiqilgan variantlar
- O'chirish yo'q, faqat arxiv (yashirish) — portfolio demosiga begona fayl yuklaganlar uni o'chira olmaydi.
- Yumshoq o'chirish (belgi qo'yish, ma'lumot qoladi) — "o'chirdim" degan foydalanuvchini aldaydi.
- Faqat yuklangan hujjat uchun to'liq o'chirish (barcha versiyalar, faktlar, run'lar, bo'laklar, xom fayl);
  EDGAR hujjatlari o'chirilmaydi.

## Qaror
- **Versiya:** `POST /documents/{id}/versions` yangi `source_document` yaratadi, `supersedes_id` eski
  versiyaga. Tahlildan keyin eski versiyaning *barcha* joriy faktlari tarixga o'tadi (tuzatilgan 8-K/A dan
  farqli: u faqat qayta aytgan faktlarni bosadi). Qayta aytilgan faktlar vorisiga bog'lanadi.
- **Juftlash:** avval (maydon, entity), keyin bir xil maydon va bir xil normallashgan qiymat. Sabab:
  haqiqiy sinovda model bir qiymatni ikki run'da turlicha nomladi ("initial term start" /
  "initial term beginning date") va 3 ta haqiqiy o'zgarish 12 ta soxta "removed/added" bilan aralashdi.
- **O'chirish:** foydalanuvchi o'z fayliga egalik qiladi; "o'chirilmaydi" qoidasi tizim o'zi ishlab
  chiqqan natijalarni himoya qiladi, foydalanuvchining o'z faylini o'chirish huquqini emas. Faqat
  `doc_type = upload`; EDGAR — 403.

## Natija (haqiqiy model, namuna shartnoma)
| Taqqoslash | Juftlash yaxshilanishidan oldin | Keyin |
|---|---|---|
| v1 → v2 (3 ta haqiqiy o'zgarish) | 3 changed + 12 soxta removed/added | — (v2 eski qoida bilan bog'langan) |
| v2 → v3 (2 ta haqiqiy o'zgarish) | — | 2 changed, 0 soxta |
