ENV_FILE ?= .env.local
PYTHON ?= python3
MANAGE := $(PYTHON) src/backend/InvenTree/manage.py

define LOAD_ENV
	@set -a; \
	if [ -f $(ENV_FILE) ]; then . $(ENV_FILE); fi; \
	set +a;
endef

.PHONY: up migrate seed test

up:
	docker-compose up -d

migrate:
	$(LOAD_ENV) $(MANAGE) migrate

seed:
	$(LOAD_ENV) $(MANAGE) seed_wws

test:
	$(LOAD_ENV) $(MANAGE) test tenancy channels wws billing
