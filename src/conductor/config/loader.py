"""Loads configs/instances/** into typed, path-tagged config objects.

Every parsed object remembers its source YAML file (`Loaded.source_file`), so
error messages and `pull` know exactly which file to point at / rewrite.
Referential checks (space -> org, org -> gcp project coverage) run here,
before any network call, so `conductor validate` can catch them for free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Generic, TypeVar

from pydantic import ValidationError

from .schema import (
    GcpProject,
    GcpProjectsFile,
    Instance,
    InstancesFile,
    Organization,
    OrgsFile,
    Space,
    SpaceFile,
)
from ..yaml_io import read_yaml

DEFAULT_CONFIG_ROOT = Path("configs/instances")

T = TypeVar("T")


@dataclass
class Loaded(Generic[T]):
    value: T
    source_file: Path


@dataclass
class ConfigError:
    file: Path
    message: str

    def __str__(self) -> str:
        return f"{self.file}: {self.message}"


class ConfigValidationError(Exception):
    def __init__(self, errors: list[ConfigError]) -> None:
        self.errors = errors
        super().__init__("\n".join(str(e) for e in errors))


@dataclass
class InstanceConfig:
    instance: Instance
    instance_file: Path
    root: Path

    orgs: dict[str, Loaded[Organization]]
    orgs_file: Path

    gcp_projects: list[Loaded[GcpProject]]
    gcp_projects_file: Path
    org_to_project: dict[str, str] = field(default_factory=dict)

    spaces: list[Loaded[Space]] = field(default_factory=list)

    def project_id_for_org(self, org_name: str) -> str:
        try:
            return self.org_to_project[org_name]
        except KeyError:
            raise KeyError(
                f"org '{org_name}' has no gcp_projects.yaml coverage "
                f"(should have been caught by validate)"
            ) from None

    def space_org_pairs(self) -> list[tuple[Loaded[Space], str]]:
        """Every (space, org) fan-out pairing across all space files."""
        return [
            (loaded_space, org_name)
            for loaded_space in self.spaces
            for org_name in loaded_space.value.organizations
        ]


def load_instances(config_root: Path = DEFAULT_CONFIG_ROOT) -> tuple[list[Instance], Path]:
    instances_file = config_root / "instances.yaml"
    if not instances_file.exists():
        raise ConfigValidationError(
            [ConfigError(instances_file, "instances.yaml not found")]
        )
    try:
        data = InstancesFile.model_validate(read_yaml(instances_file))
    except ValidationError as e:
        raise ConfigValidationError([ConfigError(instances_file, str(e))]) from e
    return data.instances, instances_file


def load_instance_config(
    name: str, config_root: Path = DEFAULT_CONFIG_ROOT
) -> InstanceConfig:
    instances, instances_file = load_instances(config_root)
    instance = next((i for i in instances if i.name == name), None)
    if instance is None:
        known = ", ".join(i.name for i in instances) or "(none defined)"
        raise ConfigValidationError(
            [
                ConfigError(
                    instances_file,
                    f"no instance named '{name}' (known instances: {known})",
                )
            ]
        )

    root = config_root / name
    errors: list[ConfigError] = []

    # -- organizations --------------------------------------------------
    orgs_file = root / "orgs.yaml"
    orgs: dict[str, Loaded[Organization]] = {}
    if orgs_file.exists():
        try:
            orgs_data = OrgsFile.model_validate(read_yaml(orgs_file))
            for org in orgs_data.organizations:
                if org.name in orgs:
                    errors.append(
                        ConfigError(orgs_file, f"duplicate org name '{org.name}'")
                    )
                orgs[org.name] = Loaded(org, orgs_file)
        except ValidationError as e:
            errors.append(ConfigError(orgs_file, str(e)))
    else:
        errors.append(ConfigError(orgs_file, "orgs.yaml not found"))

    # -- gcp projects -----------------------------------------------------
    gcp_file = root / "gcp_projects.yaml"
    gcp_projects: list[Loaded[GcpProject]] = []
    org_to_project: dict[str, str] = {}
    if gcp_file.exists():
        try:
            gcp_data = GcpProjectsFile.model_validate(read_yaml(gcp_file))
            for proj in gcp_data.gcp_projects:
                gcp_projects.append(Loaded(proj, gcp_file))
                for org_name in proj.orgs:
                    if org_name in org_to_project and org_to_project[org_name] != proj.project_id:
                        errors.append(
                            ConfigError(
                                gcp_file,
                                f"org '{org_name}' is listed under multiple gcp "
                                f"projects ('{org_to_project[org_name]}' and "
                                f"'{proj.project_id}') — an org must map to exactly "
                                f"one GCP project",
                            )
                        )
                    org_to_project[org_name] = proj.project_id
        except ValidationError as e:
            errors.append(ConfigError(gcp_file, str(e)))
    else:
        errors.append(ConfigError(gcp_file, "gcp_projects.yaml not found"))

    # -- spaces -------------------------------------------------------------
    spaces: list[Loaded[Space]] = []
    seen_space_names: set[str] = set()
    spaces_dir = root / "spaces"
    if spaces_dir.exists():
        for space_file in sorted(spaces_dir.glob("*.yaml")):
            try:
                sf = SpaceFile.model_validate(read_yaml(space_file))
            except ValidationError as e:
                errors.append(ConfigError(space_file, str(e)))
                continue
            for s in sf.space:
                if s.name in seen_space_names:
                    errors.append(
                        ConfigError(space_file, f"duplicate space name '{s.name}'")
                    )
                seen_space_names.add(s.name)
                spaces.append(Loaded(s, space_file))

    # -- referential checks (space -> org, org -> gcp project) --------------
    for loaded_space in spaces:
        s = loaded_space.value
        if not s.organizations:
            errors.append(
                ConfigError(
                    loaded_space.source_file,
                    f"space '{s.name}' lists no organizations — nothing to onboard it to",
                )
            )
        for org_name in s.organizations:
            if org_name not in orgs:
                errors.append(
                    ConfigError(
                        loaded_space.source_file,
                        f"space '{s.name}' references unknown org '{org_name}' "
                        f"(not found in {orgs_file})",
                    )
                )
            elif org_name not in org_to_project:
                errors.append(
                    ConfigError(
                        loaded_space.source_file,
                        f"space '{s.name}' onboards org '{org_name}', but '{org_name}' "
                        f"has no coverage in {gcp_file} — can't derive its AI "
                        f"provider/service key without a GCP project",
                    )
                )

    if errors:
        raise ConfigValidationError(errors)

    return InstanceConfig(
        instance=instance,
        instance_file=instances_file,
        root=root,
        orgs=orgs,
        orgs_file=orgs_file,
        gcp_projects=gcp_projects,
        gcp_projects_file=gcp_file,
        org_to_project=org_to_project,
        spaces=spaces,
    )
