from datetime import date
import re


_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def _normalize_digits(value: str) -> str:
    return value.translate(
        _DIGIT_TRANSLATION
    )


def jalali_to_gregorian(
    year: int,
    month: int,
    day: int,
) -> date:
    """
    Convert Jalali date to Gregorian date
    without any third-party package.
    """

    original = (
        year,
        month,
        day,
    )

    if month < 1 or month > 12:
        raise ValueError(
            "ماه شمسی باید بین ۱ تا ۱۲ باشد."
        )

    if day < 1 or day > 31:
        raise ValueError(
            "روز شمسی معتبر نیست."
        )

    jy = year + 1595

    days = (
        -355668
        + (365 * jy)
        + ((jy // 33) * 8)
        + (((jy % 33) + 3) // 4)
        + day
    )

    if month < 7:
        days += (
            month - 1
        ) * 31

    else:
        days += (
            186
            + ((month - 7) * 30)
        )

    gy = 400 * (
        days // 146097
    )

    days %= 146097

    if days > 36524:
        days -= 1

        gy += 100 * (
            days // 36524
        )

        days %= 36524

        if days >= 365:
            days += 1

    gy += 4 * (
        days // 1461
    )

    days %= 1461

    if days > 365:
        gy += (
            days - 1
        ) // 365

        days = (
            days - 1
        ) % 365

    gd = days + 1

    is_leap = (
        (
            gy % 4 == 0
            and
            gy % 100 != 0
        )
        or
        gy % 400 == 0
    )

    month_days = [
        0,
        31,
        29 if is_leap else 28,
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ]

    gm = 1

    while gd > month_days[gm]:

        gd -= month_days[gm]

        gm += 1

    result = date(
        gy,
        gm,
        gd,
    )

    if (
        gregorian_to_jalali(
            result
        )
        != original
    ):
        raise ValueError(
            "تاریخ شمسی واردشده معتبر نیست."
        )

    return result


def gregorian_to_jalali(
    value: date,
) -> tuple[int, int, int]:
    """
    Convert Gregorian date to:
    (jalali_year, jalali_month, jalali_day)
    """

    gy = value.year
    gm = value.month
    gd = value.day

    cumulative_days = [
        0,
        31,
        59,
        90,
        120,
        151,
        181,
        212,
        243,
        273,
        304,
        334,
    ]

    gy2 = (
        gy + 1
        if gm > 2
        else gy
    )

    days = (
        355666
        + (365 * gy)
        + ((gy2 + 3) // 4)
        - ((gy2 + 99) // 100)
        + ((gy2 + 399) // 400)
        + gd
        + cumulative_days[
            gm - 1
        ]
    )

    jy = (
        -1595
        + 33
        * (
            days // 12053
        )
    )

    days %= 12053

    jy += 4 * (
        days // 1461
    )

    days %= 1461

    if days > 365:

        jy += (
            days - 1
        ) // 365

        days = (
            days - 1
        ) % 365

    if days < 186:

        jm = (
            1
            + days // 31
        )

        jd = (
            1
            + days % 31
        )

    else:

        jm = (
            7
            + (
                days - 186
            ) // 30
        )

        jd = (
            1
            + (
                days - 186
            ) % 30
        )

    return (
        jy,
        jm,
        jd,
    )


def parse_jalali_date(
    value: str,
) -> date:
    """
    Accept:
        1405-06-20
        1405/06/20
        ۱۴۰۵-۰۶-۲۰

    Return Gregorian Python date.
    """

    value = _normalize_digits(
        value.strip()
    )

    match = re.fullmatch(
        (
            r"(\d{4})"
            r"\s*[-/.]\s*"
            r"(\d{1,2})"
            r"\s*[-/.]\s*"
            r"(\d{1,2})"
        ),
        value,
    )

    if match is None:

        raise ValueError(
            "تاریخ را به فرمت شمسی "
            "YYYY-MM-DD وارد کنید؛ "
            "مثلاً 1405-06-20."
        )

    year, month, day = map(
        int,
        match.groups(),
    )

    return jalali_to_gregorian(
        year,
        month,
        day,
    )


def format_jalali_date(
    value: date,
) -> str:

    year, month, day = (
        gregorian_to_jalali(
            value
        )
    )

    return (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )
