"""Validated finite IR for Vodoo namespace generation."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """Forbid unnoticed additions to the generator specification."""

    model_config = ConfigDict(extra="forbid")


class RequiredDomain(StrictModel):
    kind: Literal["required"]
    parameter: str
    field: str
    operator: str


class OptionalListDomain(StrictModel):
    kind: Literal["optionalList"]
    parameter: str
    field: str
    operator: str


DomainSpec = Annotated[RequiredDomain | OptionalListDomain, Field(discriminator="kind")]


class SearchReadOperation(StrictModel):
    name: str
    kind: Literal["searchRead"]
    model: str
    fields: str
    order: str
    domain: DomainSpec | None = None


class WriteOperation(StrictModel):
    name: str
    kind: Literal["write"]
    model: str
    id_parameter: str = Field(alias="idParameter")
    values: dict[str, bool | int | float | str | None]


OperationSpec = Annotated[SearchReadOperation | WriteOperation, Field(discriminator="kind")]


class NamespaceSpec(StrictModel):
    spec_version: Literal[1] = Field(alias="specVersion")
    namespace: str
    class_name: str = Field(alias="className")
    model: str
    record_type: str = Field(alias="recordType")
    default_fields: list[str] = Field(alias="defaultFields")
    default_detail_fields: list[str] = Field(alias="defaultDetailFields")
    date_fields: dict[str, Literal["date", "datetime"]] = Field(alias="dateFields")
    field_sets: dict[str, list[str]] = Field(alias="fieldSets")
    operations: list[OperationSpec]
