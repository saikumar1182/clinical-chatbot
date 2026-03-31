# ClinicalTrialsChatBot

ClinicalTrialsChatBot is an AI-powered application designed to help users find and understand clinical trials more easily. It uses a combination of Natural Language Processing (NLP) and a structured database of clinical trials to provide relevant information in a conversational format. A production-grade conversational AI system on PostgreSQL + pgvector, dbt via Astronomer Cosmos, LangChain, AWS Bedrock, and Streamlit — orchestrated by Apache Airflow, fully Dockerized with GitHub Actions.

## Features

- **Conversational Interface**: Chat with the bot to find clinical trials that match your criteria.
- **Advanced Search**: Filter trials by condition, prompts, phase, and status.
- **Data Integration**: Connects to external APIs to fetch the latest clinical trial data.
- **Modern UI**: Built with Streamlit for a fast and interactive user experience.
- **Production-Grade**: Built with PostgreSQL + pgvector, dbt via Astronomer Cosmos, LangChain, AWS Bedrock, and Streamlit — orchestrated by Apache Airflow, fully Dockerized with GitHub Actions.

## Getting Started

### Prerequisites

- Docker
- Docker Compose

### Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd clinical-chatbot
   ```

2. Start the application:
   ```bash
   make build
   make up
   ```

3. Access the application:
   - **Web App**: http://localhost:8501
   - **Airflow UI**: http://localhost:8080
