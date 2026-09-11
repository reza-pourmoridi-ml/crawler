from datetime import date, datetime
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class SearchRequestCreate(BaseModel):
    route_type: Literal[
        "domestic",
        "international",
    ]

    origin_airport_id: int = Field(gt=0)
    destination_airport_id: int = Field(gt=0)

    departure_date_jalali: str

    @model_validator(mode="after")
    def validate_different_airports(self):
        if (
            self.origin_airport_id
            == self.destination_airport_id
        ):
            raise ValueError(
                "مبدأ و مقصد نمی‌توانند یکسان باشند."
            )

        return self


class SearchAirportResponse(BaseModel):
    id: int
    name_fa: str
    category: str

    model_config = ConfigDict(
        from_attributes=True
    )


class SearchRequestResponse(BaseModel):
    id: int

    route_type: Literal[
        "domestic",
        "international",
    ]

    origin_airport_id: int
    destination_airport_id: int

    departure_date: date
    departure_date_jalali: str

    created_at: datetime

    origin_airport: SearchAirportResponse
    destination_airport: SearchAirportResponse

    model_config = ConfigDict(
        from_attributes=True
    )