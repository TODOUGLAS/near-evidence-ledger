# Чек-лист формы NEAR HACKATHON для проекта 2 (Evidence Ledger)

Форма: https://nearhackathon.com/#apply (или POST /api/applications; ассистент отправляет только после твоего «да» на полный JSON). **Ассистент ничего не отправляет, не публикует и не создаёт репозиторий.** Правила: `_сайт/HACKATHON.md`.

Окно: сдача до **сб 14.11.2026 17:59 CST**; целимся отправить до **16:30 CST**. Код заморожен после финального `publish` (14.11 ~02:11 CST); любая правка файлов из `code_hash` = новый запуск.

## Перед формой (по порядку)
- [ ] Тестнет: ничего делать не нужно для сдачи; по желанию после пн 16.11 00:00 UTC: `python -m ledger resolve` (закрывает первую неделю прогнозов; ключи testnet-аккаунтов только на box, поэтому попроси агента выполнить `resolve`).
- [ ] Посмотреть `site/index.html` и README; прогнать «как скринер»: чистая папка, 5 команд из README (ассистент уже прогнал, `docs/CLEAN_ROOM.md`).
- [ ] Записать видео 30–60 с по `docs/VIDEO_SCRIPT.md` (числа на экране сверить с последним `python -m ledger all --offline`; кадр `python -m ledger verify` обязателен).
- [ ] Создать **отдельный публичный репозиторий** для проекта 2 (один репо = одна подача; репо проекта 1 использовать нельзя). Залить содержимое проекта (без `.venv`, `data/raw`, `contract/target`; `contract/target/near/evidence_ledger.wasm` можно приложить в релиз, sha256 в `docs/deployment.json`). Репо должен быть публичным к 14.11 23:59 UTC (= 17:59 CST).
- [ ] Опубликовать пост в X по `docs/X_POST.md` (видео приложить, теги @NEARProtocol и #NEARHackathon, фраза «built at NEAR HACKATHON»). Скопировать ссылку на пост.
- [ ] Проверить, что в README проекта 2 назван Counterparty Guard, а в README проекта 1 назван Evidence Ledger (Q-015).

## Поля формы (значения даёшь ты; ассистент ничего не подставляет)
| поле | что вводить | ограничения |
|---|---|---|
| projectName | `NEAR Evidence Ledger` (предложение) | 2–80 символов |
| leadName | твоё имя | 2–80 |
| email | твой email; с одного email допустимо ≤2 подач (проект 1 + проект 2) | ≤160 |
| size | `1` (если один) | ровно одно из: `1`, `2 - 4`, `4 - 6`, `6 - 8`, `8+` |
| tracks | `["thesis"]` | id из списка: defi, thesis, privacy, business, swarms, security, agents, realworld, games, nfts, memecoins, social, open |
| nearAddress | `douglass.near` | 2–64, строчные |
| projectUrl | `https://github.com/TODOUGLAS/near-evidence-ledger` | http(s), ≤300, уникален |
| demoUrl | URL публичного поста в X | http(s), ≤300 |
| idea | текст ниже (числа вердиктов в нём намеренно не указаны; контракт и tx-ссылки лежат в README и `docs/testnet_txs.tsv`) | 20–2000 символов (сейчас 1033) |
| consent | `true` после прочтения: «I agree that the organizers may use these details to review our submission and contact us about this hackathon.» | — |

Поле `website` — ловушка для спама, его не трогать. Если после отправки нашёл ошибку: не подавать повторно, а https://nearhackathon.com/request-changes.

### Текст для поля idea (1076 символов)
```
NEAR Evidence Ledger is an investment thesis for NEAR that tests itself. It states ten falsifiable claims with numeric thresholds fixed before the verdict (usage, active accounts, fee yield, TVL, stablecoins, price-usage link, validator concentration, dilution, NEAR Intents volume and take rate) and computes SUPPORTED / REFUTED / INCONCLUSIVE from public data (NearBlocks, NEAR RPC, DefiLlama, FastNEAR) with bootstrap intervals. The verdicts plus hashes of the exact data and code are stored in a Rust contract on NEAR testnet, which re-checks the verdict rule itself; anyone can challenge a verdict with other data and the contract records whether it flips. 21 interval forecasts are pre-registered on-chain and scored later, and a CLI re-runs everything offline and compares it with the chain (ledger verify). Each verdict is shown with its robustness. Several claims come out refuted, which is the point: evidence, not conviction. Testnet only, no mainnet transaction. Companion project from the same team: Counterparty Guard (separate repo, tracks security and agents).
```

## После отправки
- [ ] Держать репо публичным и дашборд доступным до результатов (судейство с 16.11, итоги до 18.11).
- [ ] Выплата в NEAR одним платежом ≤30 дней (курсовой риск; налоги и вывод в фиат — вне проекта ❓).
