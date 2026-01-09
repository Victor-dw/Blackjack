## Blackjack Operating System (Backend)

This repository is scaffolded from `docs/ARCHITECTURE.md`.

### Architecture

The system follows an **8-layer pipeline**:

1. Perception (data collection/cleaning)
2. Variables (raw → normalized variables)
3. Signals (variables → opportunity/regime)
4. Strategies (signals → candidate actions)
5. Risk (approval + final position sizing)
6. Execution (mechanical execution; no "smart" judgement)
7. Post-Mortem (decision snapshot + evaluation)
8. Evolution (backtest/optimization; isolated from live trading)

### Quick Start (skeleton)

1. Copy and edit configs under `config/`
2. Start infra/services:

   - `docker compose up -d`

3. Start API locally (when deps are installed):

   - `python -m src.api.main`

See `docs/STANDARDS.md` for development conventions.
