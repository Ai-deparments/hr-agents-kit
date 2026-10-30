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

**v0.2 da yangi:**
- **Keldim'ni soxtalashtirishdan himoya.** Filial geozonasi (GPS) yoki mudir telefonidagi har 60 soniyada yangilanadigan QR.
- **Mehnat kodeksi qoidalari.** 6 oydan oldingi ta'til belgilanadi; yiliga 120 soatdan ortiq qo'shimcha ish ogohlantiriladi.
- **Qoidalar bilan tanishish.** Xodim SOP'ni «o'qidim» deb tasdiqlaydi; panelda qamrov foizi ko'rinadi.
- **Anonim eNPS va ishdan ketish so'rovnomasi.** Natija kamida 5 ta javob bo'lsa ko'rsatiladi.
- **Ketish xavfi signallari.** Faqat HR ko'radi; bu suhbat uchun sabab, qaror emas.
- **Nomzod roziligi.** Shaxsiy ma'lumotlarga rozilik so'raladi; rad etilganlar ma'lumotlari 180 kundan keyin anonimlashtiriladi.
- **Xavfsizlik auditi:** [docs/SECURITY.md](docs/SECURITY.md).

### v0.3 da yangi

- **Bitta HR agent.** Rahbar, HR va egasi bitta agent bilan gaplashadi (barcha vositalar), xodim — o'z yordamchisi bilan. Tugmalar yo'q: hammasi oddiy so'z bilan.
- **Agent kontekstni ko'radi.** Javob berilgan (reply) xabarni o'qiydi; vakansiya qoralamasi /start dan keyin ham yo'qolmaydi; til xabar matnidan aniqlanadi (lotin → o'zbek, kirill → rus).
- **Vakansiyalar.** Agent HR so'zlaridan e'lon yozadi, tahrirlaydi, faqat buyruq bilan chop etadi; ommaviy /jobs sahifasi.
- **Suhbat vaqtlari va ish taklifi.** HR vaqtlarni qo'shadi → nomzod botda raqam yoki vaqtni yozib tanlaydi → bir kun oldin va 1 soat oldin eslatma. Taklifni «qabul qilaman» deb qabul qilsa — xodim kartasi (sinov muddati) va onboarding kursi avtomatik.
- **HR hujjatlar (PDF).** Tahrirlanadigan shablonlar: ish joyidan ma'lumotnoma, ishga qabul va ta'til buyruqlari. Noma'lum maydon bo'sh chiziq bo'lib qoladi — hech narsa o'ylab topilmaydi.
- **Onboarding materiallari.** Video va yo'riqnomalar lavozim/bo'lim bo'yicha, kunma-kun kurs, «ko'rdim» belgisi, suhbat eslatmalari.
- **Guruh mavzulari bo'yicha hisobotlar.** Bot forum-guruhdagi mavzu nomlarini o'zi aniqlaydi va har bir hisobotni o'z mavzusiga yuboradi (davomat, rekruting, onboarding, oylik, tahlil) — ertalab va kechqurun; aytadigan narsa bo'lmasa yubormaydi.
- **Telefon uchun format.** Rich-xabarlar: sarlavha, qisqa ro'yxatlar, keng jadvallarsiz.
- **Haftalik CEO hisoboti** (rich + Excel 3 varaq) va **intizom eslatmalari**: dushanba kuni qoralama, HR tasdiqlamaguncha hech kimga yuborilmaydi.
- **Integratsiyalar:** TimePay (Face ID davomat, jarima/bonus), Smartup (savdo), hh.uz (rezyume qidirish, faqat o'qish), KPI va ABC tahlil.
- **Panel:** foydalanuvchilar, botga ruxsat so'rovlari (begona odamlarga bot javob bermaydi), rollar konstruktori, bo'limlar.
- **Davomat aniqroq:** kirgan, lekin chiqishni belgilamagan xodim «keldi» deb hisoblanadi; 30 kun belgisiz xodim foizga kirmaydi va alohida ko'rsatiladi.

### v0.3.1 da yangi

- **AI kamera → davomat.** Imzolangan webhook (`POST /api/webhooks/camera`, HMAC, 5 daqiqalik oyna, takror yetkazish bir marta hisoblanadi). Kunning eng erta kelishi va eng kech ketishi olinadi; inson belgisi (Keldim, rahbar, HR tuzatishi) har doim ustun; rasmlar saqlanmaydi; ism faqat bitta xodimga aniq mos kelsa bog'lanadi, qolganlari HR uchun saqlanadi. Hisobotda kamera qatori (guruhda faqat sonlar), panelda «AI kamera» sahifasi (faqat o'qish).
- **Intizom qoidalari.** Ro'yxat `company.yaml` da; matn va summalarni faqat admin panelda o'zgartiradi (audit: oldin/keyin). Qoidani odam qo'llaydi: avval N ta ogohlantirish, keyin jarima; yozilgan jarima summasi qoida keyin o'zgarsa ham o'zgarmaydi.
- **Vakansiya studiyasi.** Kompaniya faktlari bloki (admin tasdiqlaydi) — agent faqat shundan va vakansiya kartasidan foydalanadi. Agent 2 ta variant yozadi; HR so'z bilan tanlaydi («2», «ikkinchisini ol») yoki o'zgartirishni yozadi. Har bir matn tekshiriladi: telefon/havolalar olib tashlanadi, raqamlar faqat manbadan, yosh faqat «18+», jins/tashqi ko'rinish/millat/din talablari yo'q. Panelda «agentga topshiriq» navbati — natijani odam qo'llaydi. Chop etish faqat aniq «e'lon qil» so'zi bilan («e'lon qilma» — chop etmaydi).
- **Taklif / rad etish oldindan ko'rish bilan.** HR nomzod oladigan aynan xabarni ko'radi; xabar bir marta yuboriladi (outbox). Nomzod vaqtni erkin yozadi («10:30», «12.11 10:30», so'z bilan) — model faqat taklif qilingan vaqtga bog'lay oladi; band qilish atomar; vaqtni ko'chirish/bekor qilish ham so'z bilan. Eslatmalar: bir kun oldin 18:00 da va 1 soat oldin.
- **Ishga olindi → onboarding.** Panelda «ishga olindi» deb belgilangan nomzod Onboarding'da «kutilmoqda» bo'ladi: bir bosishda xodim kartasi + 30/60/90 reja + kurs; sabab bilan olib tashlash. Onboarding hisobotida kutayotganlar soni.
- **Hisobotlar.** Oylik: 1-sanadan o'tgan oy tabeli yopilguncha har kuni eslatma (summalarsiz). Tahlil: haftalik filial signallari (oxirgi 7 kun ≥ 3 va oldingi 4 hafta o'rtachasidan ≥ 2×) — guruhga faqat son, filiallar bo'yicha — shaxsiy xabarda.

v0.3 dan yangilash va yangi `CAMERA_WEBHOOK_SECRET` (faqat AI kamera bo'lsa): [docs/IMPROVEMENTS.md](docs/IMPROVEMENTS.md#v031-2026-10-30).

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

**Новое в v0.2:**
- **Защита «Keldim» от подделки.** Геозона филиала (GPS) или QR, который меняется каждые 60 секунд на телефоне заведующего.
- **Правила Трудового кодекса.** Отпуск раньше 6 месяцев работы помечается; переработка больше 120 часов в год вызывает предупреждение.
- **Ознакомление с правилами.** Сотрудник подтверждает «прочитал» для SOP; в панели виден процент охвата.
- **Анонимный eNPS и exit-опрос.** Итоги показываются, только если ответов не меньше 5.
- **Сигналы риска увольнения.** Видит только HR; это повод для разговора, а не решение.
- **Согласие кандидата.** Бот спрашивает согласие на обработку персональных данных; данные отклонённых обезличиваются через 180 дней.
- **Аудит безопасности:** [docs/SECURITY.md](docs/SECURITY.md).

### Новое в v0.3

- **Один HR-агент.** Руководители, HR и владелец говорят с одним агентом (все инструменты), сотрудник — со своим помощником. Никаких кнопок: всё обычными словами.
- **Агент видит контекст.** Читает сообщение, на которое ответили (reply); черновик вакансии не теряется после /start; язык — по тексту сообщения (латиница → узбекский, кириллица → русский).
- **Вакансии.** Агент пишет объявление из слов HR, правит, публикует только по команде; публичная страница /jobs.
- **Слоты собеседований и оффер.** HR добавляет время → кандидат пишет номер или время в боте → напоминание накануне и за 1 час. Пишет «qabul qilaman» на оффер — создаётся карточка сотрудника (испытательный срок) и курс онбординга.
- **HR-документы (PDF).** Редактируемые шаблоны: справка с места работы, приказы о приёме и об отпуске. Неизвестные поля остаются пустой строкой — ничего не выдумывается.
- **Материалы онбординга.** Видео и инструкции по должности/отделу, курс по дням, отметка «ko'rdim», напоминания о беседах.
- **Отчёты по темам группы.** Бот сам узнаёт названия тем в форум-группе и шлёт каждый отчёт в свою тему (посещаемость, рекрутинг, онбординг, зарплата, аналитика) — утром и вечером; если сказать нечего — не шлёт.
- **Формат под телефон.** Rich-сообщения: заголовок, короткие списки, без широких таблиц.
- **Недельный CEO-дайджест** (rich + Excel на 3 листа) и **напоминания о дисциплине**: черновики по понедельникам, без подтверждения HR никому не уходят.
- **Интеграции:** TimePay (Face ID, штрафы/бонусы), Smartup (продажи), hh.uz (поиск резюме, только чтение), KPI и ABC-анализ.
- **Панель:** пользователи, запросы доступа к боту (незнакомым бот не отвечает), конструктор ролей, отделы.
- **Точнее посещаемость:** отметил приход без ухода — «пришёл»; кто 30 дней без отметок — не входит в процент и показывается отдельно.

### Новое в v0.3.1

- **AI-камера → посещаемость.** Подписанный webhook (`POST /api/webhooks/camera`, HMAC, окно 5 минут, повторная доставка учитывается один раз). Берётся самый ранний приход и самый поздний уход за день; отметка человека (check-in, руководитель, правка HR) всегда главнее; фото не сохраняются; имя связывается только при точном совпадении с одним сотрудником, остальные сохраняются для HR. Строка камеры в отчёте (в группе — только числа), страница «AI-камера» в панели (только чтение).
- **Правила дисциплины.** Список — в `company.yaml`; тексты и суммы меняет только админ в панели (аудит до/после). Правило применяет человек: сначала N предупреждений, потом штраф; сумма записанного штрафа не меняется, даже если правило потом изменят.
- **Студия вакансий.** Блок «факты о компании» (утверждает админ) — агент пишет только из них и карточки вакансии. Агент пишет 2 варианта; HR выбирает словами («2», «второй») или пишет, что изменить. Каждый текст проверяется: телефоны/ссылки вырезаются, числа только из источников, возраст только «18+», без требований к полу/внешности/национальности/религии. В панели — очередь «задача агенту», результат применяет человек. Публикация только точным словом «опубликуй» («не опубликуй» — не публикует).
- **Приглашение / отказ с предпросмотром.** HR видит ровно то сообщение, которое получит кандидат; оно уходит один раз (outbox). Кандидат пишет время свободно («10:30», «12.11 10:30», словами) — модель может сопоставить только с предложенным слотом; бронь атомарная; перенос/отмена — тоже словами. Напоминания: накануне в 18:00 и за 1 час.
- **Нанят → онбординг.** Кандидат со статусом «нанят» в панели попадает в Онбординг как «ждёт старта»: одним нажатием карточка + план 30/60/90 + курс; убрать — с причиной. В отчёте онбординга — число ожидающих.
- **Отчёты.** Зарплата: с 1-го числа каждый день, пока табель прошлого месяца не закрыт (без сумм). Аналитика: недельные сигналы по филиалам (последние 7 дней ≥ 3 и ≥ 2× среднего за 4 недели) — в группу только число, по филиалам — в личку.

Обновление с v0.3 и новая переменная `CAMERA_WEBHOOK_SECRET` (только если есть AI-камера): [docs/IMPROVEMENTS.md](docs/IMPROVEMENTS.md#v031-2026-10-30).

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
