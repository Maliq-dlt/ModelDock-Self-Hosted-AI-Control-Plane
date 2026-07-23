import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from sqlalchemy import select

from app.core.db import init_db, session_factory
from app.core.security import create_api_key
from app.models import APIKey, Environment, ModelRecord, Project, Provider, VirtualModel


async def main() -> None:
    await init_db()
    async with session_factory() as session:
        project = await session.scalar(select(Project).where(Project.slug == "demo"))
        if not project:
            project = Project(name="Demo Project", slug="demo", description="ModelDock MVP demo project")
            session.add(project)
            await session.flush()
            environment = Environment(project_id=project.id, name="Production", type="production")
            session.add(environment)
            await session.flush()
        else:
            environment = await session.scalar(select(Environment).where(Environment.project_id == project.id))
        provider = await session.scalar(select(Provider).where(Provider.name == "ollama_local"))
        if not provider:
            provider = Provider(name="ollama_local", provider_type="ollama", base_url="http://host.docker.internal:11434", enabled=True)
            session.add(provider)
            await session.flush()
        model = await session.scalar(select(ModelRecord).where(ModelRecord.provider_id == provider.id, ModelRecord.model_name == "llama3.2"))
        if not model:
            model = ModelRecord(provider_id=provider.id, model_name="llama3.2", display_name="Llama 3.2 Local", context_window=128000, capabilities_json=["chat"], pricing_json={"input_cost_per_million": 0, "output_cost_per_million": 0}, tags_json=["local"])
            session.add(model)
            await session.flush()
        virtual = await session.scalar(select(VirtualModel).where(VirtualModel.project_id == project.id, VirtualModel.name == "smart-router"))
        if not virtual:
            virtual = VirtualModel(project_id=project.id, name="smart-router", strategy="priority", configuration_json={"candidates": [{"model_id": model.id}]})
            session.add(virtual)
        existing_key = await session.scalar(select(APIKey).where(APIKey.project_id == project.id, APIKey.status == "active"))
        if existing_key:
            print(f"Existing active API key prefix: {existing_key.key_prefix}")
        else:
            raw_key, prefix, key_hash = create_api_key("live")
            session.add(APIKey(project_id=project.id, environment_id=environment.id, name="demo-client", key_prefix=prefix, key_hash=key_hash))
            print(f"MODELDOCK_API_KEY={raw_key}")
        await session.commit()
        print(f"MODELDOCK_PROJECT_ID={project.id}")
        print("Next: run Ollama, pull llama3.2, then call http://localhost:8080/v1/chat/completions")


if __name__ == "__main__":
    asyncio.run(main())
