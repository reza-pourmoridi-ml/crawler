from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)

from app.control.flight_paths.service import clean_code


class FlightPathRequest(BaseModel):
    website_id: int = Field(gt=0)
    airport_id: int = Field(gt=0)
    code: str = Field(max_length=255)

    @field_validator(
        "code",
        mode="before",
    )
    @classmethod
    def validate_code(cls, value):
        if isinstance(value, str):
            return clean_code(value)

        return value


class FlightPathWebsiteResponse(BaseModel):
    id: int
    name: str

    domestic_url_format: str | None
    international_url_format: str | None

    date_calendar: str | None
    date_format: str | None

    model_config = ConfigDict(
        from_attributes=True
    )


class FlightPathAirportResponse(BaseModel):
    id: int
    name_fa: str
    category: str

    model_config = ConfigDict(
        from_attributes=True
    )


class FlightPathResponse(BaseModel):
    id: int
    website_id: int
    airport_id: int
    airport_name_fa: str
    code: str
    created_at: datetime

    website: FlightPathWebsiteResponse
    airport: FlightPathAirportResponse

    model_config = ConfigDict(
        from_attributes=True
    )