# Цифровий деканат — практична робота 1, варіант 1

Розв’язок продовжує історію форку `abramochkinvl-ops/digital-dean-api-starter`, базова фіксація `7dde819`.
Номер у списку — 1; остача `1 % 4 = 1`; індивідуальне поле — `enrollment_year`.

## Швидкий запуск у Windows CMD або терміналі VS Code

Відкрийте корінь проєкту, де розташований `pyproject.toml`:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
python -m pip install -e ".[dev]"
python -m pytest
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Потрібен Python 3.12+. Для зручності є `setup.cmd`, `verify.cmd` та `run.cmd`.
Після запуску: <http://127.0.0.1:8000/docs>, <http://127.0.0.1:8000/health>, <http://127.0.0.1:8000/openapi.json>.
Дані синтетичні; після перезапуску вони зникають. Не додавайте до API реальні персональні дані.

## Конфігурація закладу

Межі в `app/institution.json` — навчальне припущення, а не правило всіх університетів:

```json
{"enrollment_year_min": 2000, "enrollment_year_max": 2030}
```

Їх можна перевизначити у CMD перед запуском:

```bat
set ENROLLMENT_YEAR_MIN=2010
set ENROLLMENT_YEAR_MAX=2026
python -m uvicorn app.main:app --reload
```

Після зміни конфігурації повністю перезапустіть процес. Якщо мінімум більший за максимум, запуск відхиляється.
Схеми, query-фільтр і документація використовують одні межі. JSON-значення року має бути цілим числом: `true`, `2026.5` і рядок `"2026"` не приймаються в тілі. Query-параметр передається як текст URL і розбирається як ціле число.

## Контракт

| Метод | Шлях | Успіх | Передбачені помилки |
|---|---|---|---|
| GET | `/health` | 200 | — |
| POST | `/api/v1/students` | 201 | 409, 422 |
| GET | `/api/v1/students?enrollment_year=2026` | 200 | 422 |
| GET | `/api/v1/students/{student_id}` | 200 | 404, 422 |
| PATCH | `/api/v1/students/{student_id}` | 200 | 404, 409, 422 |

```json
{
  "full_name": "Олена Коваль",
  "email": "olena.koval@example.com",
  "group_code": "КН-31",
  "enrollment_year": 2026
}
```

`full_name`: 5–120 символів після обрізання крайніх пробілів. `email`: синтаксично валідна, унікальна без урахування регістру. `group_code`: великі латинські/українські літери або цифри, дефіс та рівно дві цифри. `id`: UUIDv4, задається лише сервером.

PATCH приймає один або кілька дозволених полів. `{}`, явний `null`, `id`, `is_admin` та інші невідомі поля дають 422. `model_dump(exclude_unset=True)` зберігає непередані значення. Конфлікт email не змінює жодного поля запису. Оновлення власною незмінною email дозволене. Відповідь PATCH — повний `StudentRead`.

## Структура

- `app/config.py`, `app/institution.json` — явні межі закладу;
- `app/schemas/student.py` — моделі й валідація;
- `app/repositories/student_repository.py` — тимчасове сховище без залежності від HTTP;
- `app/api/students.py` — HTTP-операції та перетворення помилок у 404/409;
- `app/main.py` — застосунок, `/health` та підключення маршрутизатора;
- `tests/` — ізольовані тести через dependency override;
- `postman/digital-dean-practice-01.postman_collection.json` — 24 послідовні запити;
- `openapi.json` — знімок контракту для навчальних меж 2000–2030.

## Postman

1. Запустіть API.
2. Імпортуйте JSON із каталогу `postman`.
3. Перевірте змінні колекції: `base_url=http://127.0.0.1:8000`, `enrollment_year=2026`, `year_min=2000`, `year_max=2030`.
4. Якщо змінили межі, змініть ці змінні; `enrollment_year` має належати новому інтервалу.
5. Запустіть **усю колекцію з першого запиту** через Collection Runner. Перший pre-request script генерує унікальні синтетичні email; другий запит зберігає `student_id`.
6. Збережіть результати Runner для власного захисту роботи.

Еквівалентний запуск колекції з Node.js:

```bat
npx --yes newman run postman/digital-dean-practice-01.postman_collection.json
```

Перевіряються 10 обов’язкових кроків, межі року, null/порожній PATCH/id, конфлікт email в оновленні та незмінність стану після відмови. Колекцію можна запускати повторно: вона не потребує DELETE і створює нові email. Весь список може містити попередні записи — перевіряється наявність створеного UUID та правильність фільтра, а не довільна загальна кількість.

## Перевірки та межі реалізації

`python -m pytest` запускає 51 тест, включно з параметризованими сценаріями. Кожен тест починається з незалежного репозиторію. Перевіряються всі HTTP-операції, нормалізація, помилки, атомарність конфлікту, межі, зміна конфігурації в новому процесі та паралельне створення однакової email.

`RLock` захищає операції в одному процесі; це не спільне сховище кількох workers. API не реалізує автентифікацію, авторизацію, TLS, постійне зберігання, аудит та обмеження частоти запитів. UUID не є дозволом доступу. `/health` не перевіряє зовнішню БД, бо її в цій роботі немає. DELETE за завданням відсутній.

## Продовження вашої історії Git

Це гілка `practice-01` того самого форку, а не новий непов’язаний проєкт. `origin` — ваш форк, `upstream` — шаблон викладача.

Перед публікацією перевірте чистий стан, результати та адреси:

```bat
git status
git remote -v
git branch --show-current
git log --oneline --decorate -n 10
python -m pytest
git push -u origin HEAD:refs/heads/practice-01
git push origin tag practice-01
git ls-remote --heads --tags origin practice-01
```

Не використовуйте `--force` і не перезаписуйте свою локальну папку поверх незбережених змін.

Якщо отримали архів з Git bundle, повну перевірену історію можна відкрити в окремій папці:

```bat
git clone -b practice-01 digital-dean-practice-01.bundle digital-dean-api-ready
cd digital-dean-api-ready
git remote set-url origin https://github.com/abramochkinvl-ops/digital-dean-api-starter.git
git remote add upstream https://github.com/serhii-ch-eu/digital-dean-api-starter.git
```

Це ще один клон тієї самої історії. Наявний локальний проєкт лишається цілим. Після публікації з цього клону можна отримати гілку у попередньому клоні через `git fetch origin`; незакомічені зміни спочатку збережіть.
