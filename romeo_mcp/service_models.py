"""Schemas distincts pour chaque service, sans options sans objet."""
from typing import Annotated, Literal, Union
from pydantic import BaseModel, ConfigDict, Field


class ServiceBase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    env_path: str = Field(min_length=1, description='Venv existant de la meme architecture, service deja installe.')
    port: int = Field(default=8888, ge=1024, le=65535)


class JupyterConfig(ServiceBase):
    service: Literal['jupyter']


class TensorboardConfig(ServiceBase):
    service: Literal['tensorboard']
    logdir: str = Field(min_length=1)


class VllmConfig(ServiceBase):
    service: Literal['vllm']
    model: str = Field(min_length=1)


class MlflowConfig(ServiceBase):
    service: Literal['mlflow']


ServiceConfig = Annotated[Union[JupyterConfig, TensorboardConfig, VllmConfig, MlflowConfig], Field(discriminator='service')]
