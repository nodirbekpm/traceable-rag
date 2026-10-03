# 004. Istalgan hujjatni yuklash — faqat EDGAR emas
Sana: 2026-10-03 | Holat: qabul qilindi

## Muammo
TZ namoyish sohasini EDGAR bilan cheklagan (9-bo'lim: "bir nechta soha kirmaydi"). Jonli sinovda
ma'lum bo'ldi: portfolio ko'ruvchisi (Upwork mijozi) o'z hujjatini sinab ko'rmoqchi bo'ladi. Faqat
EDGAR'dan yuklaydigan tizim "servis" emas, bitta ma'lumot manbasi uchun yozilgan demo bo'lib ko'rinadi.
Foydalanuvchi (loyiha egasi) TZ'ni o'zgartirishni talab qildi.

## Ko'rib chiqilgan variantlar
- Faqat EDGAR, istalgan kompaniya CIK bo'yicha — mijoz o'z hujjatini sinay olmaydi.
- Yuklash + darhol tahlil — katta faylda kutilmagan vaqt va narx, mijoz nima bo'layotganini bilmaydi.
- Yuklash → taxmin (vaqt, narx) → tasdiq → fonda tahlil, jarayon ko'rsatiladi.

## Qaror
Uchinchi variant. Konvertatsiya (`text.document_to_text`) formatga qarab: HTML, PDF (pypdf), DOCX
(python-docx), TXT/MD. Barcha oraliqlar shu chiqishga nisbatan, xom baytlar o'zgarmas saqlanadi.
Yuklangan hujjatlar umumiy maydonlar profilida (`g1`), EDGAR — `s1`; 8-K prompt matni bayt-bayt
o'zgarmagani xesh bilan tekshirildi, shuning uchun mavjud run'lar va idempotentlik kaliti amal qiladi.
Uzun hujjat 40 000 belgilik qismlarga bo'linadi; iqtibos butun matnda qidiriladi.

Taxmin shu o'rnatmaning tarixidan: tugagan run'larning soniya / 1000 kirish tokeni nisbati (3 tadan
kam run bo'lsa — standart 3 s), embedding tezligi (o'lchangan 20 bo'lak/s), bepul tarif kutishlari.

## Natija
- Uch va'da saqlandi: provenance (iqtibos tekshiruvi format-mustaqil), versiyalash (bir xil xesh —
  dublikat yaratilmaydi), o'lchov (taxmin haqiqiy tarixdan).
- O'lchov korpusi EDGAR bo'lib qoladi — natijalar takrorlanadigan bo'lishi uchun.
- Taxmin aniqligi (taxmin vs haqiqiy vaqt) jonli sinovda o'lchanadi va README'ga yoziladi.
