"""Validated finite IR for Vodoo namespace generation."""

import keyword
import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TYPESCRIPT_RESERVED = {
    "await",
    "break",
    "case",
    "catch",
    "class",
    "const",
    "continue",
    "debugger",
    "default",
    "delete",
    "do",
    "else",
    "enum",
    "export",
    "extends",
    "false",
    "finally",
    "for",
    "function",
    "if",
    "implements",
    "import",
    "in",
    "instanceof",
    "interface",
    "let",
    "new",
    "null",
    "package",
    "private",
    "protected",
    "public",
    "return",
    "static",
    "super",
    "switch",
    "this",
    "throw",
    "true",
    "try",
    "typeof",
    "var",
    "void",
    "while",
    "with",
    "yield",
}
_GENERATED_PARAMETER_NAMES = {"domain", "self"}
_TYPESCRIPT_CLASS_MEMBERS = {
    "constructor",
    "client",
    "metadata",
    "decodeRecord",
    "list",
    "get",
    "set",
    "fields",
    "comment",
    "commentWithId",
    "note",
    "noteWithId",
    "messages",
    "tags",
    "addTag",
    "attachments",
    "attach",
    "attachmentData",
    "allAttachmentData",
    "downloadAttachments",
    "download",
    "url",
    "postMessage",
}
_PYTHON_CLASS_MEMBERS = {
    "__init__",
    "_client",
    "_model",
    "_tag_model",
    "_default_fields",
    "_default_detail_fields",
    "_record_type",
    "list",
    "get",
    "set",
    "fields",
    "comment",
    "comment_with_id",
    "note",
    "note_with_id",
    "messages",
    "tags",
    "add_tag",
    "attachments",
    "attach",
    "download",
    "attachment_data",
    "all_attachment_data",
    "url",
}


def _snake_case(value: str) -> str:
    with_word_boundaries = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", value)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", with_word_boundaries).lower()


def _python_constant_name(value: str) -> str:
    snake = _snake_case(value)
    if snake.endswith("ies"):
        snake = f"{snake[:-3]}y"
    elif snake.endswith("s"):
        snake = snake[:-1]
    return f"{snake.upper()}_FIELDS"


def _typescript_constant_name(class_name: str, value: str) -> str:
    return f"{_snake_case(class_name).upper()}_{_snake_case(value).upper()}"


def _validate_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{value!r} is not a portable identifier")
    python_name = _snake_case(value)
    if keyword.iskeyword(value) or keyword.iskeyword(python_name):
        raise ValueError(f"{value!r} is a Python keyword")
    if value in _TYPESCRIPT_RESERVED:
        raise ValueError(f"{value!r} is a TypeScript keyword")
    return value


class StrictModel(BaseModel):
    """Forbid unnoticed additions to the generator specification."""

    model_config = ConfigDict(extra="forbid")


class _DomainBase(StrictModel):
    @field_validator("parameter", check_fields=False)
    @classmethod
    def validate_parameter(cls, value: str) -> str:
        identifier = _validate_identifier(value)
        python_name = _snake_case(identifier)
        if python_name in _GENERATED_PARAMETER_NAMES:
            raise ValueError(f"{identifier!r} collides with a generated local name")
        return identifier


class RequiredDomain(_DomainBase):
    kind: Literal["required"]
    parameter: str
    field: str
    operator: str


class OptionalDomain(_DomainBase):
    kind: Literal["optional"]
    parameter: str
    field: str
    operator: str


class OptionalListDomain(_DomainBase):
    kind: Literal["optionalList"]
    parameter: str
    field: str
    operator: str


DomainSpec = Annotated[
    RequiredDomain | OptionalDomain | OptionalListDomain,
    Field(discriminator="kind"),
]


class _OperationBase(StrictModel):
    @field_validator("name", check_fields=False)
    @classmethod
    def validate_name(cls, value: str) -> str:
        identifier = _validate_identifier(value)
        if identifier in _TYPESCRIPT_CLASS_MEMBERS:
            raise ValueError(f"{identifier!r} collides with a generated TypeScript member")
        python_name = _snake_case(identifier)
        if python_name in _PYTHON_CLASS_MEMBERS:
            raise ValueError(f"{identifier!r} collides with a generated Python member")
        return identifier


class SearchReadOperation(_OperationBase):
    name: str
    kind: Literal["searchRead"]
    description: str
    model: str
    fields: str
    order: str
    domain: DomainSpec | None = None
    python_keyword_only: bool = Field(default=False, alias="pythonKeywordOnly")


class WriteOperation(_OperationBase):
    name: str
    kind: Literal["write"]
    description: str
    model: str
    id_parameter: str = Field(alias="idParameter")
    values: dict[str, bool | int | float | str | None]

    @field_validator("id_parameter")
    @classmethod
    def validate_id_parameter(cls, value: str) -> str:
        identifier = _validate_identifier(value)
        python_name = _snake_case(identifier)
        if python_name in _GENERATED_PARAMETER_NAMES:
            raise ValueError(f"{identifier!r} collides with a generated local name")
        return identifier


OperationSpec = Annotated[SearchReadOperation | WriteOperation, Field(discriminator="kind")]
DateKind = Literal["date", "datetime"]
Capability = Literal["crud", "messaging", "tags", "attachments"]
Target = Literal["python", "asyncPython", "typescript", "swift"]
Edition = Literal["community", "enterprise"]


class AvailabilitySpec(StrictModel):
    module: str
    editions: list[Edition]
    min_version: int = Field(alias="minVersion", ge=17, le=19)
    max_version: int | None = Field(default=None, alias="maxVersion", ge=17, le=19)

    @model_validator(mode="after")
    def validate_versions(self) -> Self:
        if self.max_version is not None and self.max_version < self.min_version:
            raise ValueError("maxVersion must be greater than or equal to minVersion")
        if len(self.editions) != len(set(self.editions)):
            raise ValueError("availability editions must be unique")
        return self


class CustomOperationSpec(StrictModel):
    name: str
    description: str
    targets: list[Target]

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return _validate_identifier(value)

    @field_validator("targets")
    @classmethod
    def validate_targets(cls, value: list[Target]) -> list[Target]:
        if not value:
            raise ValueError("custom operations must claim at least one target")
        if len(value) != len(set(value)):
            raise ValueError("custom operation targets must be unique")
        return value


class AccessDefinitionSpec(StrictModel):
    model: str
    perm_read: bool
    perm_write: bool
    perm_create: bool
    perm_unlink: bool


class RuleDefinitionSpec(AccessDefinitionSpec):
    domain: str


class GroupDefinitionSpec(StrictModel):
    name: str
    comment: str
    access: list[AccessDefinitionSpec]
    rules: list[RuleDefinitionSpec] = Field(default_factory=list)


class SecurityGroupsSpec(StrictModel):
    spec_version: Literal[1] = Field(alias="specVersion")
    groups: list[GroupDefinitionSpec]

    @model_validator(mode="after")
    def validate_groups(self) -> Self:
        names = [group.name for group in self.groups]
        if len(names) != len(set(names)):
            raise ValueError("security group names must be unique")
        return self


class NamespaceSpec(StrictModel):
    spec_version: Literal[1] = Field(alias="specVersion")
    namespace: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    class_name: str = Field(alias="className", pattern=r"^[A-Z][A-Za-z0-9]*$")
    model: str
    record_type: str = Field(alias="recordType")
    tag_model: str | None = Field(default=None, alias="tagModel")
    capabilities: list[Capability]
    availability: AvailabilitySpec
    default_fields: list[str] = Field(alias="defaultFields")
    default_detail_fields: list[str] | None = Field(default=None, alias="defaultDetailFields")
    date_fields: dict[str, DateKind] = Field(default_factory=dict, alias="dateFields")
    field_sets: dict[str, list[str]] = Field(default_factory=dict, alias="fieldSets")
    field_set_date_fields: dict[str, dict[str, DateKind]] = Field(
        default_factory=dict,
        alias="fieldSetDateFields",
    )
    operations: list[OperationSpec] = Field(default_factory=list)
    custom_operations: list[CustomOperationSpec] = Field(
        default_factory=list,
        alias="customOperations",
    )

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        return _validate_identifier(value)

    @field_validator("field_sets")
    @classmethod
    def validate_field_set_names(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for name in value:
            _validate_identifier(name)
        return value

    @model_validator(mode="after")
    def validate_references(self) -> Self:
        unknown_date_sets = set(self.field_set_date_fields) - set(self.field_sets)
        if unknown_date_sets:
            names = ", ".join(sorted(unknown_date_sets))
            raise ValueError(f"fieldSetDateFields references unknown field sets: {names}")

        for field_set, dates in self.field_set_date_fields.items():
            unknown_fields = set(dates) - set(self.field_sets[field_set])
            if unknown_fields:
                names = ", ".join(sorted(unknown_fields))
                raise ValueError(f"{field_set} date metadata references unknown fields: {names}")

        if not self.capabilities or self.capabilities[0] != "crud":
            raise ValueError("capabilities must start with crud")
        if len(self.capabilities) != len(set(self.capabilities)):
            raise ValueError("capabilities must be unique")
        if ("tags" in self.capabilities) != (self.tag_model is not None):
            raise ValueError("tags capability and tagModel must be declared together")

        operation_names = [operation.name for operation in self.operations]
        custom_names = [operation.name for operation in self.custom_operations]
        all_operation_names = [*operation_names, *custom_names]
        if len(all_operation_names) != len(set(all_operation_names)):
            raise ValueError("generated and custom operation names must be unique")
        python_operation_names = [_snake_case(name) for name in all_operation_names]
        if len(python_operation_names) != len(set(python_operation_names)):
            raise ValueError("operation names must be unique after Python normalization")

        python_constants = [_python_constant_name(name) for name in self.field_sets]
        if len(python_constants) != len(set(python_constants)):
            raise ValueError("field set names must produce unique Python constants")
        prefix = _snake_case(self.class_name).upper()
        typescript_constants = [
            f"{prefix}_MODEL",
            f"{prefix}_DEFAULT_FIELDS",
            f"{prefix}_DEFAULT_DETAIL_FIELDS",
            f"{prefix}_DATE_FIELDS",
            f"{prefix}_CAPABILITIES",
            f"{prefix}_AVAILABILITY",
            *(_typescript_constant_name(self.class_name, name) for name in self.field_sets),
            *(
                _typescript_constant_name(self.class_name, f"{name}DateFields")
                for name in self.field_set_date_fields
            ),
        ]
        if len(typescript_constants) != len(set(typescript_constants)):
            raise ValueError("generated TypeScript constant names must be unique")
        for operation in self.operations:
            if (
                isinstance(operation, SearchReadOperation)
                and operation.fields not in self.field_sets
            ):
                raise ValueError(
                    f"operation {operation.name!r} references unknown field set "
                    f"{operation.fields!r}"
                )
        return self
