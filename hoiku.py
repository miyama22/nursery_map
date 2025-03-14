import polars as pl
import datetime
from form_filter import FilterForm, get_nursery_type, get_age_availability


def cond_holiday(column: pl.Expr, saturday_flg: int, sunday_flg: int) -> pl.Expr:
    """
    指定した曜日のデータを含む行をフィルターする

    Args:
        column: フィルター対象のカラム
        saturday_flg: 土曜日にチェックが入っているか
        sunday_flg: 日曜日にチェックが入っているか

    Returns:
        フィルターする行の条件式
    """
    if sunday_flg == 1:
        return column.str.contains("日")
    elif saturday_flg == 1:
        return column.str.contains("土")
    else:
        # どちらのチェックもなければ、すべての行を返す
        return pl.lit(True)


def cond_list(column: pl.Expr, cond_list: list) -> pl.Expr:
    """
    リストに含まれる種別の保育園にフィルターする
    """
    return column.is_in(cond_list)


def start_time(column: pl.Expr, hh_and_mm: tuple) -> pl.Expr:
    """
    指定した時刻以前のデータを含む行にフィルターする
    """
    return column <= pl.time(*hh_and_mm)


def end_time(column: pl.Expr, hh_and_mm: tuple) -> pl.Expr:
    """
    指定した時刻以降のデータを含む行にフィルターする
    """
    return column >= pl.time(*hh_and_mm)


def between_num_filter(column: pl.Expr, num_min: int|None, num_max: int|None, num_max_breaker: int|None=None, num_infinite=999) -> pl.Expr:
    """
    数値が指定範囲内の行をフィルターする

    num_max の数値が num_max_breaker の数値より大きい場合、num_infinite に置き換えます。
    """
    if num_max_breaker is not None and num_max is not None and num_max >= num_max_breaker:
        num_max = num_infinite

    if num_min and num_max:
        return column.is_null() | ((column >= num_min) & (column <= num_max))
    elif num_min:
        return column.is_null() | (column >= num_min)
    elif num_max:
        return column.is_null() | (column <= num_max)

    return pl.lit(True)


def vacancy_by_age(age_list: list) -> pl.Expr:
    """
    指定した年齢の空きが1以上の行にフィルターする
    """
    # 年齢の指定がなければ全ての行を返す
    if age_list == []:
        return pl.lit(True)

    # 指定された年齢の空きが1以上の行を返す
    conditions = []
    for col in age_list:
        condition = f'(pl.col("{col}") >= 1)'
        conditions.append(condition)
    conditions = " & ".join(conditions)  # or検索にする場合は&を|に置き換えでいけるはず
    return eval(conditions)


def has_or_not(column: pl.Expr, condition: int) -> pl.Expr:
    """
    'あり'/'なし'の二値をとるカラムのフィルター
    """
    if condition == 1:
        return (column == "あり") | (column == "有り")
    else:
        return pl.lit(True)


def str_contain_filter(column: pl.Expr, condition: str|None) -> pl.Expr:
    """
    文字列が含まれる行をフィルターする
    """
    if condition is None:
        return pl.lit(True)
    else:
        return column.str.contains(condition)


def filter_data(lf: pl.LazyFrame, form: FilterForm) -> pl.DataFrame:
    """
    LazyFrameからフィルターした結果のdataframeを返す

    Args:
        lf: hoikuen.csv の LazyFrame
        form: フィルター条件フォームデータ
    Returns:
        フィルターしたデータの DataFrame
    """

    def b_to_i(val: bool) -> int:
        """
        Converts a boolean value to 1 or 0
        """
        return 1 if val else 0

    def time_to_tuple(val: datetime.time | None) -> tuple[int, int]:
        if val is None:
            return (0, 0)
        return (val.hour, val.minute)

    def codes_to_names(codes: list[str], code_dict: dict[str, str]):
        return [code_dict[code] for code in codes if code in code_dict]

    start_times = form.start_time.to_numbers()
    end_times = form.end_time.to_numbers()
    extended_end_times: list[int] = form.extended_end_time.to_numbers()

    print(start_times)
    print(end_times)
    print(extended_end_times)

    df = (
        lf.filter(str_contain_filter(pl.col("名称"), form.nursery_name.data))
        .filter(str_contain_filter(pl.col("所在地"), form.address.data))
        .filter(
            cond_holiday(
                pl.col("利用可能曜日"),
                b_to_i(form.saturday.data),
                b_to_i(form.sunday.data),
            )
        )
        .filter(
            cond_list(
                pl.col("種別"), codes_to_names(form.type.data or [], get_nursery_type())
            )
        )
        .filter(start_time(pl.col("開始時間"), (start_times[2], start_times[3])))
        .filter(end_time(pl.col("終了時間"), (end_times[0], end_times[1])))
        .filter(
            end_time(
                pl.col("延長保育終了時間"),
                (extended_end_times[0], extended_end_times[1]),
            )
        )
        .filter(
            vacancy_by_age(
                codes_to_names(form.age_availability.data or [], get_age_availability())
            )
        )
        .filter(has_or_not(pl.col("園庭の有無"), b_to_i(form.garden.data)))
        .filter(has_or_not(pl.col("駐輪場の有無"), b_to_i(form.bicycle_parking.data)))
        .filter(
            has_or_not(
                pl.col("ベビーカー置き場の有無"), b_to_i(form.stroller_area.data)
            )
        )
        .filter(
            has_or_not(
                pl.col("障害児の受け入れ体制"), b_to_i(form.disability_acceptance.data)
            )
        )
        .filter(
            has_or_not(pl.col("病児保育事業の実施"), b_to_i(form.sick_child_care.data))
        )
        .filter(
            between_num_filter(
                pl.col("収容定員_合計"), form.capacity_min.data, form.capacity_max.data,
                num_max_breaker=200, num_infinite=999
            )
        )
        .collect(streaming=True)
    )

    return df
