# Wiki Agent Kit — qisqa qoʻllanma (oʻzbekcha)

**Vikipediyachilar uchun Claude Code plagini.** Maqola nomini va tilni aytasiz: kit maqolani
yuklaydi, Claude tarjima qiladi, har bir havola, turkum va andoza Vikidata orqali
**oʻzbekcha Vikipediyadagi** mos sahifaga ulanadi, manbalar baytma-bayt saqlanadi. Keyin
kit nimani tekshirish kerakligini aytadi. Nashrni **siz** qilasiz — kitda login ham, tahrir
kodi ham yoʻq.

## Asosiy buyruqlar

| Buyruq | Nima qiladi |
|---|---|
| `/wikikit:translate-article Ibn Jurayj` | Maqolani tarjima qiladi, tekshiradi, tahrir havolasi va izohini tayyorlaydi |
| `/wikikit:find-articles Category:Hadith scholars` | uz.wiki'da yoʻq maqolalarni topadi, siyosatingiz boʻyicha saralaydi |
| `/wikikit:daily-batch 8` | Navbatdagi 8 ta maqolani parallel tarjima qiladi, bitta jadval beradi |
| `/wikikit:review-translation` | Ikkinchi oʻqish — faqat xatolar roʻyxati, oʻzi tuzatmaydi |
| `/wikikit:verify-citations` | Manbalar haqiqatan shu gapni aytadimi — tekshiradi |
| `/wikikit:wikidata-labels` | Vikidata'da yetishmayotgan oʻzbekcha label/tavsiflar (QuickStatements) |
| `/wikikit:port-template` | Andoza yoki Lua modulini uz.wiki'ga koʻchirish rejasi va qoralamalari |

## wikipedia-translator'dan farqi

- **OpenAI kerak emas** — tarjimani Claude oʻzi (translator subagent) qiladi; LNK
  havolalarining nomini ham shu agent maqolani yozayotganda beradi, shuning uchun
  `[[…Nanutaviy|…Nanautaviy]]` kabi nomuvofiqliklar kamayadi.
- **Istalgan til juftligi** — oʻzbekcha profil (`wikikit/profiles/uz/`) eski loyihaning
  barcha qoidalarini (252 lokalizatsiya qoidasi, sana/hijriy tuzatishlari, transliteratsiya,
  `[[Lohur|Lahor]]` solishtirgichi, lead tekshiruvi) va ularning testlarini oʻz ichiga oladi.
- **Yangi tekshiruvlar**: manbada yoʻq URL (oʻylab topilgan iqtibos belgisi), oʻzgargan
  raqamlar, aniqlanmagan nomli `<ref>`, buzilgan belgilash.
- **Tuzatilgan xato**: uz.wiki'da muqobili yoʻq, lekin matn saqlaydigan andoza
  (masalan `{{Text and translation}}` — sheʼr misralari) endi oʻchirilmaydi, saqlanib
  hisobotda koʻrsatiladi. Eski loyihada bunday andozalar matni bilan birga yoʻqolardi.

## Oʻrnatish (Windows)

1. Claude Code va uv oʻrnatilgan boʻlsin (uv: PowerShell'da
   `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"`).
2. Claude Code ichida:
   ```
   /plugin marketplace add muzaffar-murodovich/wiki-agent-kit
   /plugin install wikikit@wiki-agent-kit
   ```
3. Sozlamalarda **contact** — email yoki Vikipediyadagi foydalanuvchi sahifangiz.

## Muhim

- Nashrdan oldin matnni **toʻliq** oʻqing; raqamlarni manba bilan solishtiring.
- Tahrir izohini aynan nusxa qiling — u CC BY-SA atributsiyasi va "mashina yordamida
  tarjima qilinib, inson tomonidan tekshirildi" degan oshkoralikni oʻz ichiga oladi.
- Koʻp maqola nashr qilishdan oldin Vikipediya:Forum'da qisqa xabar qoldiring —
  namuna: [COMMUNITY.md](COMMUNITY.md).
