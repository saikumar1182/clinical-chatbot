up:                    ## Start all services (postgres + app + airflow)
	docker compose up -d

down:                  ## Stop all services
	docker compose down

rebuild:               ## Rebuild app image only
	docker compose up -d --build app

logs:                  ## Tail all logs
	docker compose logs -f

# ── Airflow ──────────────────────────────────────────────────
airflow-trigger-ingest: ## Manually trigger ingestion DAG now
	docker compose exec airflow-scheduler \
	  airflow dags trigger clinicalchat_ingestion

airflow-trigger-dbt:   ## Manually trigger dbt DAG
	docker compose exec airflow-scheduler \
	  airflow dags trigger clinicalchat_dbt

airflow-trigger-embed: ## Manually trigger embeddings DAG
	docker compose exec airflow-scheduler \
	  airflow dags trigger clinicalchat_embeddings

airflow-logs:          ## Show Airflow scheduler logs
	docker compose logs -f airflow-scheduler

airflow-dags-list:     ## List all registered DAGs
	docker compose exec airflow-scheduler airflow dags list

# ── Database ─────────────────────────────────────────────────
psql:                  ## Open psql shell on pharmachat DB
	docker compose exec postgres psql -U clinicaluser -d clinicaldb

# ── Tests ─────────────────────────────────────────────────────
test:                  ## Run all pytest tests including DAG tests
	docker compose run --rm app pytest tests/ -v --tb=short

test-dags:             ## Run only DAG unit tests
	docker compose run --rm app pytest tests/test_dags.py -v

eval:                  ## Run Weave eval (or trigger DAG 4)
	docker compose exec airflow-scheduler \
	  airflow dags trigger pharmachat_eval_monitor

clean:                 ## Remove all volumes (DELETES ALL DATA)
	docker compose down -v