from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class AirlineAliasResponse(BaseModel):
    id: int
    alias_name: str

    model_config = ConfigDict(
        from_attributes=True
    )


class AirlineResponse(BaseModel):
    id: int
    official_name_fa: str
    aliases: list[AirlineAliasResponse] = Field(
        default_factory=list
    )

    model_config = ConfigDict(
        from_attributes=True
    )


class AirlineWriteRequest(BaseModel):
    official_name_fa: Annotated[
        str,
        StringConstraints(strip_whitespace=True, min_length=1, max_length=255),
    ]

    aliases: list[
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]
    ] = Field(
        default_factory=list
    )


class AirlineCreateRequest(AirlineWriteRequest):
    pass


class AirlineUpdateRequest(AirlineWriteRequest):
    pass
