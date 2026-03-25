up:                    ## Start all services (postgres + app + airflow)
	docker compose up -d

down:                  ## Stop all services
	docker compose down

build:               ## Build all services
	docker compose build --no-cache

logs:                  ## Tail all logs
	docker compose logs -f

restart:               ## Restart all services
	docker compose restart

clean:                 ## Remove all volumes (DELETES ALL DATA)
	docker compose down --remove-orphans

# ── Airflow ──────────────────────────────────────────────────
airflow-trigger-ingest: ## Manually trigger ingestion DAG now
	docker compose exec airflow-scheduler \
	  airflow dags trigger clinical_ingestion

airflow-trigger-dbt:   ## Manually trigger dbt DAG
	docker compose exec airflow-scheduler \
	  airflow dags trigger clinical_dbt

airflow-trigger-embed: ## Manually trigger embeddings DAG
	docker compose exec airflow-scheduler \
	  airflow dags trigger clinical_embeddings

airflow-logs:          ## Show Airflow scheduler logs
	docker compose logs -f airflow-scheduler

airflow-dags-list:     ## List all registered DAGs
	docker compose exec airflow-scheduler airflow dags list

# ── Database ─────────────────────────────────────────────────
psql:                  ## Open psql shell on clinicalchat DB
	docker compose exec postgres psql -U clinical_user -d clinicaldb

# ── Tests ─────────────────────────────────────────────────────
test:                  ## Run all pytest tests including DAG tests
	docker compose run --rm app pytest tests/ -v --tb=short

test-dags:             ## Run only DAG unit tests
	docker compose run --rm app pytest tests/test_dags.py -v

eval:                  ## Run Weave eval (or trigger DAG 4)
	docker compose exec airflow-scheduler \
	  airflow dags trigger clinical_eval_monitor
