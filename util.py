# This file will contain utility functions
import polars as pl
import datetime
import base58
import xxhash
from flask import request
from urllib.parse import urlparse, urljoin
from typing import List


def to_url(url):
    """
    Converts a relative url to absolute
    """
    if bool(urlparse(url).netloc):  # is already an absolute url
        return url
    return urljoin(request.url, url)


def shorten_address(address: str, ommitables: List[str]):
    """
    住所短縮
    """
    for ommitable in ommitables:
        if address.startswith(ommitable):
            address = address[len(ommitable) :]
        else:
            break
    return address


def is_enrollable(number_of_seat: int | str | None) -> bool:
    """
    空き状況の判断
    """
    if number_of_seat is None:
        return False
    try:
        as_number = int(number_of_seat)
        return as_number > 0
    except ValueError:
        return False


def time_to_HHMM_ja(time: datetime.time | str | None) -> str:
    """
    時間フォーマット
    """
    if time is None:
        return ""
    if isinstance(time, str):
        if (len(time) <= 5) and (":" in time):
            try:
                hours, minutes = map(int, time.split(":"))
                time = datetime.time(hours, minutes)
            except ValueError:
                return time
        else:
            return time
    if time.minute == 0:
        return time.strftime(f"{time.hour}時")
    return f"{time.hour}時{time.minute:02d}分"


def times_to_HHMM_ja(time1: datetime.time | None, time2: datetime.time | None) -> str:
    """
    時間フォーマット
    """
    return f"{time_to_HHMM_ja(time1)}～{time_to_HHMM_ja(time2)}"


def date_to_mmdd_ja(date: datetime.date | None) -> str:
    """
    日付フォーマット
    """
    if date is None:
        return ""
    return date.strftime("%Y年%m月%d日")


def dates_to_mmdd_ja(date1: datetime.date | None, date2: datetime.date | None) -> str:
    """
    日付フォーマット
    """
    return f"{date_to_mmdd_ja(date1)}～{date_to_mmdd_ja(date2)}"


def create_google_map_url(lat: float, lng: float) -> str:
    return f"http://maps.google.com/maps?daddr={lat},{lng}&ll=&hl=ja"


def xx58_str_to_hashstr(text: str) -> str:
    """
    Converts text to a hash string which is friendly to url and humans.

    * `hashstr  = Base58(xxHash64(text)) = Base58(hashbyte)`
    * `hashbyte = xxHash64(text)`
    """
    b_hash = xxhash.xxh64(bytes(text, encoding="utf-8")).digest()
    str_hash = base58.b58encode(b_hash).decode("utf-8")
    return str_hash

    return str


def xx58_str_to_hashbyte(text: str) -> bytes:
    return xxhash.xxh64(bytes(text, encoding="utf-8")).digest()


def xx58_hashstr_to_hashbyte(hashstr: str) -> bytes:
    return base58.b58decode(hashstr)


def load_hoikuen_csv(filename: str = "data/hoikuen.csv") -> pl.LazyFrame:
    """
    保育園データのロード
    """
    lf = pl.scan_csv(filename)

    # データの前処理
    lf = (
        lf
        # 時間の型を変換
        .with_columns(
            pl.col("開始時間").str.to_time("%H:%M"),
            pl.col("終了時間").str.to_time("%H:%M"),
            pl.col("延長保育終了時間").str.to_time("%H:%M"),
        )
        # 空き状況を数値型に変換
        .with_columns(
            pl.col("0歳児").replace({"（なし）": None}).cast(pl.Int64),
            pl.col("1歳児").replace({"（なし）": None}).cast(pl.Int64),
            pl.col("2歳児").replace({"（なし）": None}).cast(pl.Int64),
            pl.col("3歳児").replace({"（なし）": None}).cast(pl.Int64),
            pl.col("4歳児").replace({"（なし）": None}).cast(pl.Int64),
            pl.col("5歳児").replace({"（なし）": None}).cast(pl.Int64),
            pl.col("3歳児から5歳児")
            .replace({"（なし）": None})
            .cast(pl.Float64)
            .cast(pl.Int64),
            pl.col("4歳児から5歳児")
            .replace({"（なし）": None})
            .cast(pl.Float64)
            .cast(pl.Int64),
        )
        # 3歳児から5歳児の空き状況を補完
        .with_columns(
            pl.when(pl.col("3歳児から5歳児").is_not_null())
            .then(
                pl.col(["3歳児", "4歳児", "5歳児"]).fill_null(pl.col("3歳児から5歳児"))
            )
            .otherwise(pl.col(["3歳児", "4歳児", "5歳児"]))
        )
        # 4歳児から5歳児の空き状況を補完
        .with_columns(
            pl.when(pl.col("4歳児から5歳児").is_not_null())
            .then(pl.col(["4歳児", "5歳児"]).fill_null(pl.col("4歳児から5歳児")))
            .otherwise(pl.col(["4歳児", "5歳児"]))
        )
    )

    return lf
