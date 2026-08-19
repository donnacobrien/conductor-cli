"""Pydantic models mirroring the mocked YAML shapes exactly.

configs/instances/instances.yaml            -> InstancesFile
configs/instances/<name>/orgs.yaml           -> OrgsFile
configs/instances/<name>/gcp_projects.yaml   -> GcpProjectsFile
configs/instances/<name>/spaces/*.yaml       -> SpaceFile
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Instance(BaseModel):
    name: str
    description: str = ""
    display_name: str = ""
    endpoint: str
    scheme: str = "https"
    api_key_env: str

    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.endpoint}"


class InstancesFile(BaseModel):
    instances: list[Instance] = Field(default_factory=list)


class Organization(BaseModel):
    name: str
    description: str = ""


class OrgsFile(BaseModel):
    organizations: list[Organization] = Field(default_factory=list)


class GcpProject(BaseModel):
    project_id: str
    orgs: list[str] = Field(default_factory=list)
    default_location: str | None = None


class GcpProjectsFile(BaseModel):
    gcp_projects: list[GcpProject] = Field(default_factory=list)


class Space(BaseModel):
    name: str
    description: str = ""
    organizations: list[str] = Field(default_factory=list)
    gcp_shortname: str
    location: str
    is_private: bool = False


class SpaceFile(BaseModel):
    space: list[Space] = Field(default_factory=list)
