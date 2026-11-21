.PHONY: help install lint typecheck test ui-check ui-test security check dev demo ui-dev ui-build image app-bundle clean

UV ?= uv
NPM ?= npm --prefix frontend
IMAGE ?= ha-music-manager:dev

help:  ## Show this help
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install:  ## Install Python + npm dependencies and git hooks
	$(UV) sync --frozen
	$(NPM) ci
	$(UV) run pre-commit install

lint:  ## Ruff lint + format check
	$(UV) run ruff check src tests scripts
	$(UV) run ruff format --check src tests scripts

typecheck:  ## mypy --strict
	$(UV) run mypy src

test:  ## Backend tests with coverage gate
	$(UV) run pytest --cov --cov-report=term

ui-check:  ## svelte-check (types + a11y)
	$(NPM) run check

ui-test:  ## Frontend unit tests
	$(NPM) test

security:  ## bandit + pip-audit + npm audit
	$(UV) run bandit -q -r src
	$(UV) export --frozen --no-dev --no-emit-project -o .audit-requirements.txt >/dev/null
	$(UV) run pip-audit -r .audit-requirements.txt --disable-pip
	@rm -f .audit-requirements.txt
	$(NPM) audit --omit=dev

check: lint typecheck test ui-check ui-test security  ## Everything. Runs locally, not in CI

ui-build:  ## Build the UI into the Python package so the backend serves it
	$(NPM) run build
	rm -rf src/ha_music_manager/static && cp -r frontend/dist src/ha_music_manager/static

dev:  ## Backend on :8099 against your own slskd (HMM_SLSKD_URL, HMM_SLSKD_API_KEY)
	HMM_SLSKD_URL=$${HMM_SLSKD_URL:-http://localhost:5030} $(UV) run ha-music-manager

demo: ui-build  ## Full app on http://localhost:8099 with a fake slskd and canned results
	$(UV) run python scripts/fake_slskd.py & echo $$! > .fake_slskd.pid; \
	trap 'kill $$(cat .fake_slskd.pid); rm -f .fake_slskd.pid' EXIT INT TERM; \
	HMM_SLSKD_URL=http://127.0.0.1:5031 HMM_SLSKD_API_KEY=demo HMM_SOULSEEK_USERNAME=demo \
		$(UV) run ha-music-manager

ui-dev:  ## Vite dev server with hot reload (proxies /api to :8099; run `make demo` too)
	$(NPM) run dev

image:  ## Build the app image for this machine
	docker build -f music_manager/Dockerfile -t $(IMAGE) .

app-bundle:  ## Self-contained app folder for /addons on Home Assistant (built on the device)
	rm -rf dist/music_manager && mkdir -p dist/music_manager
	cp -r music_manager/. pyproject.toml uv.lock README.md src dist/music_manager/
	mkdir -p dist/music_manager/frontend
	cp -r frontend/package.json frontend/package-lock.json frontend/index.html \
		frontend/vite.config.ts frontend/svelte.config.js frontend/tsconfig.json frontend/src \
		dist/music_manager/frontend/
	sed -i '/^image:/d' dist/music_manager/config.yaml
	find dist/music_manager \( -name '__pycache__' -o -name static \) -prune -exec rm -rf {} +
	@echo "Copy dist/music_manager to /addons/ on Home Assistant"

clean:
	rm -rf dist frontend/dist src/ha_music_manager/static .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov
