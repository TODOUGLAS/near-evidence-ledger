> **ГОТОВОЕ ВИДЕО (14.11 02:50 CST): `docs/video/ledger_demo.mp4`** (1920x1080, H.264+AAC, 59.92 с, 2.8 МБ), субтитры `ledger_demo.srt` (вшиты в mp4), текст озвучки `ledger_voiceover.txt`.
> Английская озвучка (Piper `en_US-ryan-high`, офлайн) и вшитые английские субтитры. Видео = реальный вывод `python -m ledger all --offline`, `verify` (RESULT: ALL MATCH), `status` + карточка транзакции `publish_run` из testnet RPC + таблица устойчивости вердиктов (`output/robustness.json`). Код, claims/data/forecast/robustness/sources/stats и snapshots не менялись.
> Готовое видео лежит в `docs/video/`. Скрипт пересборки в этот репозиторий не входит.
> Отличия видео от таблицы ниже: (1) формулировка про C2 исправлена: C2 не дотягивает до порога 100 000, а «ниже, чем год назад» относится только к C1 (0.15); (2) challenge на C3 назван «нашим собственным тестовым», а не внешним спором (как в README); (3) вместо открытия NearBlocks (Cloudflare блокирует бота) показана карточка из RPC с хэшами, 10 вердиктами из аргументов tx и URL эксплорера текстом; (4) вместо скролла дашборда показана нативная таблица устойчивости; (5) про Counterparty Guard в видео ничего не сказано.

# Demo video script, 30-60 s (screen recording + voice-over)

Re-read the numbers on screen before recording: they come from your last `python -m ledger all --offline`, not from this file.
Target length ~58 s, ~140 words. One take, terminal on the left, browser on the right. Record in a clean terminal with a large font.

| time | on screen | voice-over |
|---|---|---|
| 0:00-0:06 | title card "NEAR Evidence Ledger", track: Investment Thesis | "Most investment theses are about conviction. This one is built to be proven wrong." |
| 0:06-0:16 | terminal: `python -m ledger all --offline`; the CLAIMS table appears with ten rows C1..C10 | "One command tests ten claims on public NEAR data, each with a numeric threshold fixed in advance." |
| 0:16-0:26 | zoom on the verdict column (green SUPPORTED / red REFUTED / yellow INCONCLUSIVE) | "Verdicts are computed, not written. Several claims are refuted: usage and active accounts are well below last year. We show them first." |
| 0:26-0:40 | terminal: `python -m ledger verify`; lines turn into MATCH, last line `RESULT: ALL MATCH`; then the browser opens the NearBlocks publish transaction | "The verdicts and the hashes of the exact data and code live on a NEAR testnet contract. This command re-runs everything offline and compares it with the chain. One changed byte, and it says mismatch." |
| 0:40-0:49 | dashboard section "How fragile is each verdict?", then the line `challenge #0 on C3 ... flips: True` from `python -m ledger status` | "Each verdict shows how fragile it is. Anyone can challenge it with other data: the contract recomputes the verdict itself. Here, gas-only fees flip revenue to refuted." |
| 0:49-0:58 | dashboard forecast section with coverage bars, then end card with repo link | "Forecasts are pre-registered on-chain, so they cannot be backdated. Evidence over conviction. Built at NEAR Hackathon." |

Say "testnet" at least once, and do not call it an oracle. Do not show or mention wallets, keys or prices as advice. If you speak about Counterparty Guard, one sentence only: "Our other project, Counterparty Guard, protects AI agents' payments."
Tip: run `python -m ledger verify` once before recording so the RPC is warm (it takes ~10-40 s; cut or speed up the wait).
