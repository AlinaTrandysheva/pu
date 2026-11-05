# Лабораторная работа 4

Зырянова С. С., ФБИ-34. Агрегатор авиаперелётов, три версии исполнения.

Требуется Docker Desktop с Docker Compose. Все команды выполняются из каталога проекта.

## Запуск

```sh
docker compose up -d --build --wait
docker compose exec -T search python -m app.seed
```

Сервис: http://localhost:18040. Пример запроса:
`/search?origin=OVB&destination=SVO&date=2026-10-19`.
Проверка работоспособности: `/health`.

Генератор создаёт 180 000 рейсов (1500 в сутки) с 19.10.2026 по 15.02.2027 включительно. Повторный запуск не меняет рейсы и не добавляет дубликаты. Время — UTC, цена — рубли.

Версия по умолчанию — `sync`. Для задачи 4.1 установите переменную окружения `SERVICE_VERSION=blocking_async`, для задачи 4.2 — `SERVICE_VERSION=async` и пересоздайте сервис:

```sh
SERVICE_VERSION=async docker compose up -d --no-deps --force-recreate --wait search
```

## Измерения и профили

Замер (прогрев 10 с, измерение 60 с, тайм-аут клиента 30 с — значения по умолчанию). Режим `closed` — с `--clients 1/10/40/80`, `open` — 5 запросов в секунду:

```sh
docker compose exec -T search python load.py --mode closed --clients 10
docker compose exec -T search python load.py --mode open --rate 5
```

Профили при C = 10 (во время нагрузки, в другом окне терминала):

```sh
docker compose exec -T -u root search py-spy record --pid 1 --duration 60 -o /tmp/sync_profile.svg
docker compose exec -T -u root search py-spy record --pid 1 --duration 60 --idle -o /tmp/sync_profile_idle.svg
docker compose exec -T -u root search py-spy dump --pid 1
```

Скрипт выводит показатели поиска и `/health` в терминал. RPS — число запросов измеряемой выборки, завершившихся до конца окна, делённое на 60 с. Перцентили и ошибки рассчитаны для всех запросов, отправленных в 60-секундном окне, с ожиданием их завершения после окна. Запросы прогрева исключены. Профили сняты отдельными прогонами C=10 и сохранены в `results`.

`diagrams` содержит две диаграммы последовательности UML в SVG. `app/service.py` содержит три реализации; в версии `blocking_async` относительно `sync` меняется только `def` на `async def` у двух обработчиков. База данных и поставщики одинаковы для всех версий.

Остановка стенда с сохранением базы:

```sh
docker compose down
```
