# HR Agents Kit

**[O'zbekcha](#ozbekcha) · [Русский](#русский) · [English](README.en.md)**

> Yopiq repozitoriy / Приватный репозиторий. Muallif / Автор: Komron (CEO AI team, HR AI agents).

---

## O'zbekcha

Smenali ishlaydigan va filiallari ko'p bo'lgan har qanday biznes (dorixona, do'kon, klinika, restoran) uchun tayyor HR bo'limi:
- **Telegram'da 7 ta AI agent**;
- **veb HR panel**;
- **mudir kabineti va Keldim/Ketdim Mini App**.

Hammasi bitta bazada ishlaydi va bitta fayl bilan sozlanadi.

Asos — BioLife zavodida ishlayotgan NOVA-KIT HR tizimi va uni Ozone dorixonalar tarmog'iga moslashtirish tajribasi. Bu uning **standart versiyasi**: brend, filiallar, smenalar va oylik qoidalari `config/company.yaml` faylida turadi, kodda mijoz nomi yo'q.

### Agentlar

| Agent | Kim uchun | Vazifasi |
|---|---|---|
| **Hamza** — HR rahbar va davomat | egasi, HR rahbar, mudirlar | yagona kirish nuqtasi; 09:00 / 18:30 davomat hisoboti + Excel; oy tabeli; 3 tagacha agentdan so'raydi |
| **Ozoda** — adaptatsiya | HR, mudirlar | lavozim shablonidan 30/60/90 reja, cheklist, ustoz, test ballari, SOP |
| **Bexruz** — oylik tekshiruvi | egasi, HR rahbar, buxgalter | to'lovdan oldingi muammolar va xavf ostidagi summa; hisoblamaydi va tasdiqlamaydi |
| **Husayn** — analitika | egasi, HR, mudirlar | shtat, kadrlar qo'nimsizligi (birinchi 30 kunda ketganlar ham), davomat — doim baza va davr bilan |
| **Suhayl** — xodim yordamchisi | har bir xodim | smenam, ta'til qoldig'i, arizalarim, rejam, hujjatlarim, qoidalar; ariza ochadi |
| **Rauf** — rekruter | nomzodlar / HR | Telegram'da jonli suhbat, 4 mezonli baho, ball ≥ 70 bo'lsa shortlist, vakansiya qoralamasi, SLA |
| **Reklama** — kanallarda reklama | HR | ish kanallarini byudjet bilan qayd qiladi; birinchi xabarni va to'lovni doim inson qiladi |

**Veb panel bo'limlari:**
- dashboard, xodimlar, davomat;
- tabel: sababi ko'rsatilgan tuzatish, Excel, oyni yopish;
- oylik: har bir raqamning formulasi, to'lovdan oldingi tekshiruv, tasdiqlash;
- arizalar, tasdiqlar navbati, adaptatsiya, hujjat muddatlari, rekruting, analitika;
- agentlar bilan chat, SOP bazasi, audit.

**Mini App:**
- xodim uchun «Keldim / Ketdim» tugmalari;
- mudir uchun Keldi/Kelmadi va soatlar (24 soatgacha), oy, avans, jarima, mukofot va ogohlantirish (sababi bilan).

**Rauf'ning alohida paneli (`/rauf`)** — rekruter uchun o'z kirishi bilan:
- dashboard: ochiq vakansiyalar, nomzodlar, o'rtacha ball, yopish muddati, SLA svetofori;
- voronka: yangi → shortlist → ishga olindi / rad etildi; manbalar bo'yicha (bot, hh, forma);
- pipeline (kanban), vakansiyalar va nomzodlar, arxiv;
- kanallardagi reklama bitimlari;
- integratsiyalar holati (kalit qiymatlari ko'rsatilmaydi).

Hammasi filial bo'yicha ruxsat bilan cheklangan.

**Rauf Mini App (`/m/rauf`)** — Rauf botida faqat HR uchun ochiladi:
- nomzodlar ballari bilan;
- tugmalar: Shortlist / Ishga olindi / Rad etish. Qarorni faqat inson qabul qiladi.

### Qoidalar

- **7 qarorni faqat inson qabul qiladi**: oylikni tasdiqlash, ushlab qolish, shartnomani o'zgartirish, ishga olish, bo'shatish, ommaviy xabar va arizani tasdiqlash.
- **Filial bo'yicha ruxsat kodda tekshiriladi**: mudir faqat o'z dorixonasini, hududiy menejer faqat o'z dorixonalarini ko'radi.
- **"Belgilamagan" degani "kelmagan" emas.** Chiqish belgilanmasa, kun "tekshirish kerak" holatiga o'tadi (8 soat qo'yilmaydi). Noma'lum oylik `—` bilan ko'rsatiladi.
- **Kun manbalarining ustuvorligi:** HR tuzatishi > ta'til/kasallik > mudir raporti > o'zi belgilash.

### Tez ishga tushirish (demo)

```powershell
cd backend
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
$env:DEBUG="1"; $env:DEV_TELEGRAM_ID="1001"
.venv\Scripts\python -m app.seed
.venv\Scripts\python -m uvicorn app.main:app --reload
# ikkinchi terminal
cd web; npm install; npm run dev        # http://localhost:5173 , Mini App: /m
```

Demo loginlar:
- `admin / admin12345`;
- `demo12345` paroli bilan: `hr`, `buh`, `ceo`, `regional`, `recruiter`.

`ANTHROPIC_API_KEY` bo'lmasa, agentlar buyruqlar bilan ishlaydi (`/hisobot`, `/payrollcheck`, `/tahlil`, `/menu`…).

### Yangi mijozga joriy qilish

1. `config/company.yaml` faylini to'ldiring.
2. `.env` faylini to'ldiring: `JWT_SECRET`, `ADMIN_PASSWORD`, bot tokenlari, `ANTHROPIC_API_KEY`.
3. Ishga tushiring:
   ```
   docker compose up -d --build
   docker compose run --rm api python -m app.seed --no-demo
   ```
4. 2–3 filialda 2 haftalik pilot o'tkazing.

Stek va kod qoidalari: [`.claude/skills/default-stack`](.claude/skills/default-stack/SKILL.md). Yaxshilanishlar va reja: [docs/IMPROVEMENTS.md](docs/IMPROVEMENTS.md).

---

## Русский

Готовый HR-отдел для любого бизнеса со сменами и множеством точек (аптеки, магазины, клиники, рестораны):
- **7 ИИ-агентов в Telegram**;
- **веб HR-панель**;
- **кабинет заведующего и Mini App «Keldim / Ketdim»**.

Всё работает на одной базе и настраивается одним файлом.

Основа — HR-система NOVA-KIT, которая работает на заводе BioLife, и опыт её адаптации под сеть аптек Ozone. Это **дефолтная версия**: бренд, филиалы, смены и правила зарплаты лежат в `config/company.yaml`, в коде нет названия клиента.

### Агенты

| Агент | Для кого | Задача |
|---|---|---|
| **Hamza** — HR-руководитель и посещаемость | владелец, HR-директор, заведующие | единая точка входа; отчёты 09:00 / 18:30 + Excel; табель месяца; спрашивает до 3 агентов |
| **Ozoda** — адаптация | HR, заведующие | план 30/60/90 по шаблону должности, чек-лист, наставник, тесты, SOP |
| **Bexruz** — проверка зарплаты | владелец, HR-директор, бухгалтер | проблемы до выплаты и сумма под риском; не считает и не утверждает |
| **Husayn** — аналитика | владелец, HR, заведующие | штат, текучесть (включая ушедших в первые 30 дней), посещаемость — всегда с базой и периодом |
| **Suhayl** — помощник сотрудника | каждый сотрудник | моя смена, остаток отпуска, мои заявки, мой план, мои документы, правила; создаёт заявки |
| **Rauf** — рекрутер | кандидаты / HR | живое интервью в Telegram, оценка по 4 критериям, shortlist от 70 баллов, черновики вакансий, SLA |
| **Реклама** — каналы | HR | регистрирует каналы с бюджетом; первое сообщение и оплату всегда делает человек |

**Разделы веб-панели:**
- дашборд, сотрудники, посещаемость;
- табель: правка с причиной, Excel, закрытие месяца;
- зарплата: формула у каждой цифры, проверка перед выплатой, утверждение;
- заявки, очередь одобрений, адаптация, сроки документов, рекрутинг, аналитика;
- чат с агентами, база SOP, аудит.

**Mini App:**
- для сотрудника кнопки «Keldim / Ketdim»;
- для заведующего Keldi/Kelmadi и часы (до 24), месяц, аванс, штраф, премия и предупреждение (с причиной).

**Отдельная панель Rauf (`/rauf`)** — для рекрутера, со своим входом:
- дашборд: открытые вакансии, кандидаты, средний балл, срок закрытия, светофор SLA;
- воронка: новый → shortlist → принят / отказ; по источникам (бот, hh, форма);
- pipeline (канбан), вакансии и кандидаты, архив резюме;
- сделки рекламного агента;
- состояние интеграций (значения ключей не показываются).

Всё ограничено доступом по филиалам.

**Mini App Rauf (`/m/rauf`)** — открывается в боте Rauf только для HR:
- кандидаты с баллами;
- кнопки Shortlist / Ishga olindi / Rad etish. Решение принимает только человек.

### Принципы

- **7 решений принимает только человек**: утверждение зарплаты, удержание, изменение договора, найм, увольнение, массовая рассылка и одобрение заявки.
- **Доступ по филиалу проверяется в коде**: заведующий видит только свою аптеку, региональный менеджер — только свои аптеки.
- **«Не отметился» ≠ «не пришёл».** Если нет отметки ухода, день уходит «на проверку» (8 часов не подставляются). Неизвестная зарплата показывается как `—`.
- **Приоритет источников дня:** правка HR > отпуск/больничный > рапорт заведующего > самоотметка.

### Быстрый старт (демо)

```powershell
cd backend
python -m venv .venv; .venv\Scripts\pip install -r requirements.txt
$env:DEBUG="1"; $env:DEV_TELEGRAM_ID="1001"
.venv\Scripts\python -m app.seed
.venv\Scripts\python -m uvicorn app.main:app --reload
# второй терминал
cd web; npm install; npm run dev        # http://localhost:5173 , Mini App: /m
```

Демо-логины:
- `admin / admin12345`;
- с паролем `demo12345`: `hr`, `buh`, `ceo`, `regional`, `recruiter`.

Без `ANTHROPIC_API_KEY` агенты работают по командам (`/hisobot`, `/payrollcheck`, `/tahlil`, `/menu`…).

### Запуск у нового клиента

1. Заполните `config/company.yaml`.
2. Заполните `.env`: `JWT_SECRET`, `ADMIN_PASSWORD`, токены ботов, `ANTHROPIC_API_KEY`.
3. Запустите:
   ```
   docker compose up -d --build
   docker compose run --rm api python -m app.seed --no-demo
   ```
4. Проведите пилот на 2–3 филиалах в течение 2 недель.

Стек и правила кода: [`.claude/skills/default-stack`](.claude/skills/default-stack/SKILL.md). Улучшения и план развития: [docs/IMPROVEMENTS.md](docs/IMPROVEMENTS.md).

### Tests / Тесты

```powershell
cd backend; .venv\Scripts\python -m pytest -q
```
