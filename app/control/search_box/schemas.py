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


class LowestAirlineOfferResponse(BaseModel):
    airline: str
    price: int
    time: str
    website_id: int
    website_name: str
    source_job_id: int
    updated_at: datetime


class ProviderSearchResultResponse(BaseModel):
    website_id: int
    website_name: str
    status: Literal[
        "scraping",
        "processing",
        "updating",
        "ready",
        "stale",
        "failed",
        "waiting",
    ]
    offers_count: int
    source_job_id: int | None
    updated_at: datetime | None


class SearchResultResponse(BaseModel):
    search_request_id: int
    status: Literal[
        "waiting",
        "processing",
        "partial",
        "completed",
        "failed",
    ]
    updated_at: datetime | None
    offers: list[LowestAirlineOfferResponse]
    providers: list[ProviderSearchResultResponse]
