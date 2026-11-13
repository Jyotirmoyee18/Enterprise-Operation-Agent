from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "Enterprise Operations Agent"
    app_env: str = "local"
    log_level: str = "INFO"
    api_key: str = ""
    approver_api_key: str = "change-me-approver-key"
    database_url: str = "postgresql://agent:agent@localhost:5432/enterprise_ops"
    sap_mode: str = "mock"
    sap_odata_base_url: str = ""
    sap_bearer_token: str = ""
    sap_allowed_write_entity: str = "PurchaseOrders"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    otel_service_name: str = "enterprise-operations-agent"
    otel_exporter_otlp_endpoint: str = "http://localhost:4317"

settings = Settings()
