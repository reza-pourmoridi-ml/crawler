from datetime import datetime
from string import Formatter
import unicodedata
from urllib.parse import urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    field_validator,
)


ALLOWED_DATE_CALENDARS = {
    "jalali",
    "gregorian",
}

REQUIRED_URL_PLACEHOLDERS = {
    "origin_path",
    "destination_path",
    "date",
}


def clean_website_name(
    value: str,
) -> str:

    value = value.strip()

    if not value:
        raise ValueError(
            "نام وب‌سایت نمی‌تواند خالی باشد."
        )

    if len(value) > 255:
        raise ValueError(
            "نام وب‌سایت نمی‌تواند "
            "بیشتر از ۲۵۵ نویسه باشد."
        )

    if any(
        unicodedata.category(char) == "Cc"
        for char in value
    ):
        raise ValueError(
            "نام وب‌سایت نمی‌تواند شامل "
            "نویسه‌های کنترلی باشد."
        )

    return value


def clean_url_format(
    value: str,
    label: str = "فرمت URL",
) -> str:

    value = value.strip()

    message = (
        f"{label} باید یک URL کامل با "
        "http:// یا https:// باشد و "
        "سه placeholder "
        "{origin_path}، "
        "{destination_path} و "
        "{date} را داشته باشد."
    )

    if (
        not value
        or len(value) > 4096
        or not value.lower().startswith(
            ("http://", "https://")
        )
        or "\\" in value
        or any(
            char.isspace()
            or unicodedata.category(char) == "Cc"
            for char in value
        )
    ):
        raise ValueError(message)

    try:
        fields = {
            field_name
            for (
                _,
                field_name,
                _,
                _,
            ) in Formatter().parse(value)
            if field_name is not None
        }

    except ValueError as exc:
        raise ValueError(
            message
        ) from exc

    if fields != REQUIRED_URL_PLACEHOLDERS:
        raise ValueError(message)

    sample_url = value.format(
        origin_path="THR",
        destination_path="MHD",
        date="1405-06-20",
    )

    parts = urlsplit(sample_url)

    if (
        parts.scheme not in {
            "http",
            "https",
        }
        or not parts.netloc
    ):
        raise ValueError(message)

    return value


def clean_date_calendar(
    value: str,
) -> str:

    value = value.strip().lower()

    if value not in ALLOWED_DATE_CALENDARS:
        raise ValueError(
            "نوع تقویم باید "
            "jalali یا gregorian باشد."
        )

    return value


def clean_date_format(
    value: str,
) -> str:

    value = value.strip().upper()

    if (
        not value
        or len(value) > 32
        or any(
            unicodedata.category(char) == "Cc"
            for char in value
        )
        or value.count("YYYY") != 1
        or value.count("MM") != 1
        or value.count("DD") != 1
    ):
        raise ValueError(
            "فرمت تاریخ باید دقیقاً شامل "
            "YYYY، MM و DD باشد؛ "
            "مثلاً YYYY-MM-DD."
        )

    remainder = (
        value
        .replace("YYYY", "")
        .replace("MM", "")
        .replace("DD", "")
    )

    if any(
        char not in "-/."
        for char in remainder
    ):
        raise ValueError(
            "برای جداکنندهٔ تاریخ فقط "
            "از - یا / یا . استفاده کنید؛ "
            "مثلاً YYYY-MM-DD."
        )

    return value


class WebsiteWriteRequest(BaseModel):
    name: str

    domestic_url_format: str
    international_url_format: str

    date_calendar: str
    date_format: str

    @field_validator("name")
    @classmethod
    def validate_name(
        cls,
        value: str,
    ) -> str:
        return clean_website_name(
            value
        )

    @field_validator(
        "domestic_url_format"
    )
    @classmethod
    def validate_domestic_url_format(
        cls,
        value: str,
    ) -> str:
        return clean_url_format(
            value,
            "فرمت URL داخلی",
        )

    @field_validator(
        "international_url_format"
    )
    @classmethod
    def validate_international_url_format(
        cls,
        value: str,
    ) -> str:
        return clean_url_format(
            value,
            "فرمت URL خارجی",
        )

    @field_validator(
        "date_calendar"
    )
    @classmethod
    def validate_date_calendar(
        cls,
        value: str,
    ) -> str:
        return clean_date_calendar(
            value
        )

    @field_validator(
        "date_format"
    )
    @classmethod
    def validate_date_format(
        cls,
        value: str,
    ) -> str:
        return clean_date_format(
            value
        )


class WebsiteResponse(BaseModel):
    id: int
    name: str

    domestic_url_format: str | None
    international_url_format: str | None

    date_calendar: str | None
    date_format: str | None

    created_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )