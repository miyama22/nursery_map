import json
import polars as pl
from typing import cast, Any, List, Dict
from compact_json import Formatter, EolStyle
from flask import render_template, request

from flask_wtf import FlaskForm  # type: ignore
from wtforms import BooleanField, StringField
from wtforms.validators import Optional as WtfOptional

from __version__ import VERSION
from hoiku import filter_data
from util import (
    load_hoikuen_csv,
    shorten_address,
    xx58_str_to_hashstr,
    to_url,
    is_enrollable,
    time_to_HHMM_ja,
)

# Below are requried by fn_hoikuen_search_result()
from branca.element import Figure
import folium
from folium.features import CustomIcon
from folium.template import Template
import geopandas as gpd
from mapping import make_nursery_map
from form_filter import FilterForm

# JSON 整形用ユーティリティ
json_formatter = Formatter(
    ensure_ascii=False,
    indent_spaces=2,
    json_eol_style=EolStyle.LF,
    east_asian_string_widths=True,
)
json_formatter.init_internals()


class ClickToPanIcon(CustomIcon):
    """
    Icon with click event to pan.
    Works as a drop-in replacement of CustomIcon.
    """

    _template = Template(
        """
        {% macro script(this, kwargs) %}
        var {{ this.get_name() }} = L.icon({{ this.options|tojavascript }});
        {{ this._parent.get_name() }}.setIcon({{ this.get_name() }});
        {{this._parent.get_name()}}.on('click', function (e) {
            const lat = e.latlng.lat;
            const lng = e.latlng.lng;
            {{ this._parent.get_name() }}._map.setView(new L.LatLng(lat, lng), 17);
        });
        {% endmacro %}
        """
    )


def info(message: Any) -> None:
    print(message)


class IndexForm(FlaskForm):
    q = StringField("名称", validators=[WtfOptional()])  # q = query
    qex = BooleanField("完全一致", validators=[WtfOptional()])  # qex = query exact
    h = StringField("ハッシュ", validators=[WtfOptional()])  # h = hash

    def __init__(self, *args, **kwargs):
        super().__init__(meta={"csrf": False}, *args, **kwargs)


def fn_hoikuen_index() -> str:
    """
    / : 保育園マップ ベースレイアウト
    """
    form = IndexForm(request.args)
    context = {"form": form, "version": VERSION}
    return render_template("hoikuen/index.html", **context)


def fn_hoikuen_search_result() -> str:
    """
    /search_result : 保育園マップ 検索インターフェース
    """
    # time_start = time.time()

    # バス関連のデータの読み込み
    bus_stop = gpd.read_file("data/geojson/shibuya_busstop.geojson")
    bus_stop["経度"] = bus_stop.geometry.x
    bus_stop["緯度"] = bus_stop.geometry.y
    bus_route = gpd.read_file("data/geojson/shibuya_busline.geojson")

    # 幼稚園・小学校関連のデータの読み込み
    school = gpd.read_file("data/geojson/shibuya_school.geojson")
    school["経度"] = school.geometry.x
    school["緯度"] = school.geometry.y
    school_area = gpd.read_file("data/geojson/shibuya_schoolarea.geojson")

    # 保育園データのロード
    lf = load_hoikuen_csv()

    # メッセージ
    messages: list[str] = []

    # リクエストから、フィルターを取得
    form = FilterForm()
    # if app.debug:
    formatted_json = json_formatter.format_dict(0, form.to_dict()).value
    info(f"form: {formatted_json}")
    # else:
    # info(f"form: {form.data}")

    # フィルター後のデータを取得
    filtered_data = filter_data(lf, form)

    # 地図を作成
    nursery_map = make_nursery_map(filtered_data)

    # バス停の出し分け
    if form.bus_stop.data:
        bus_group = folium.FeatureGroup(name="バス停")
        bus_icon_image = to_url("/asset/bus.png")

        def create_bus_stop_marker(row):
            popup_text = f"<p style='font-size: 15px;'>バス停名: {row['bus_stop_name']}<br> バス事業者:{row['bus_operator']} <br>路線番号: {row['route_number']}</p>"
            folium.Marker(
                location=[row["緯度"], row["経度"]],
                popup=folium.Popup(popup_text, max_width=300, autoPan=False),
                icon=ClickToPanIcon(
                    icon_image=bus_icon_image,
                    icon_size=(45, 45),
                ),
            ).add_to(bus_group)

        bus_stop.apply(create_bus_stop_marker, axis=1)
        bus_group.add_to(nursery_map)

    # バスルートの出し分け
    if form.bus_route.data:
        bus_route_group = folium.FeatureGroup(name="バスルート")
        folium.GeoJson(bus_route).add_to(bus_route_group)
        bus_route_group.add_to(nursery_map)

    # 小学校/幼稚園の出し分け
    if form.elementary_school.data or form.kindergarten.data:
        # マーカー用関数
        def create_school_marker(row, icon_image, group):
            popup_text = f"<p style='font-size: 15px;'>{row['school_name']}</p>"
            folium.Marker(
                location=[row["緯度"], row["経度"]],
                popup=folium.Popup(popup_text, max_width=300, autoPan=False),
                icon=ClickToPanIcon(
                    icon_image=icon_image,
                    icon_size=(50, 50),
                ),
                tooltip=folium.Tooltip(
                    text=f"{row['school_name']}",
                    sticky=True,
                    style="background-color: white; font-size: 13px; font-weight: bold;",
                ),
            ).add_to(group)

        if form.elementary_school.data:
            elementary_group = folium.FeatureGroup(name="小学校")
            (
                school.query('school_class == "小学校"').apply(
                    create_school_marker,
                    icon_image=to_url("/asset/elementary.png"),
                    group=elementary_group,
                    axis=1,
                )
            )
            elementary_group.add_to(nursery_map)

        if form.kindergarten.data:
            kindergarten_group = folium.FeatureGroup(name="幼稚園")
            (
                school.query('school_class == "幼稚園"').apply(
                    create_school_marker,
                    icon_image=to_url("/asset/kindergarten.png"),
                    group=kindergarten_group,
                    axis=1,
                )
            )
            kindergarten_group.add_to(nursery_map)

    # 小学校区の出し分け
    if form.school_district.data:
        school_area_group = folium.FeatureGroup(name="小学校区")

        def style_function(feature):
            return {
                "color": "#34D15F",
                "fillOpacity": 0.1,
                "weight": 3,
            }

        folium.GeoJson(
            school_area,
            style_function=style_function,
            popup=folium.GeoJsonPopup(fields=["school_name"], labels=False),
        ).add_to(school_area_group)
        school_area_group.add_to(nursery_map)

    # レイヤーコントロールを追加(確認用)
    folium.LayerControl().add_to(nursery_map)

    # Folium height fix: https://stackoverflow.com/questions/79051048
    cast(Figure, nursery_map.get_root()).height = "100%"

    # htmlに変換
    map_html = nursery_map._repr_html_()

    # メッセージを用意
    data_count = filtered_data.height
    info(f"filtered_data.height: {data_count}")
    if data_count == 0:
        messages.append("マッチする保育園はありません")
    else:
        messages.append(f"件数: {data_count}")

    # フィルター後のデータを取得
    df: pl.DataFrame = filtered_data.with_columns(pl.col(pl.Time).cast(pl.String))

    # JSON 出力の場合
    is_json = request.args.get("json")
    if is_json:
        df = df.with_columns(pl.col(pl.Time).cast(pl.String))
        return json_formatter.serialize(json.loads(df.write_json()))

    # Render the template with the map and data
    context = {
        "df": df,
        "map_html": map_html,
        "data": df.write_json(),
        "version": VERSION,
        "form": form,
        "messages": messages,
        "shorten_address": shorten_address,
        "is_enrollable": is_enrollable,
        "to_hhmm": time_to_HHMM_ja,
    }
    is_map = request.args.get("map")
    template_html = "hoikuen/search_result.html" if not is_map else "hoikuen/map.html"
    response = render_template(template_html, **context)

    """
    time_end = time.time()
    info(f"Response is built in {(time_end - time_start) * 1000}ms")
    """
    return response


class NameSearchForm(FlaskForm):
    q = StringField("名称", validators=[WtfOptional()])  # q = query
    qex = BooleanField("完全一致", validators=[WtfOptional()])  # qex = query exact
    x = StringField("Partial", validators=[WtfOptional()])  # x = html fragment
    h = StringField("ハッシュ", validators=[WtfOptional()])  # h = hash
    json = BooleanField("JSON", validators=[WtfOptional()])

    def __init__(self, *args, **kwargs):
        super().__init__(meta={"csrf": False}, *args, **kwargs)


def get_view_perma_url(item: Dict[str, Any]) -> str:
    """
    Get Perma URL for `/view`
    """
    hashstr = xx58_str_to_hashstr(item["名称"])
    return f"{to_url('/hoikuen/view')} + ?h={hashstr}"


def fn_hoikuen_view() -> str:
    """
    /view : 保育園閲覧

    名称文字列もしくはハッシュで検索し、最初の１件を表示

    * q : 検索文字列
    * h : 検索ハッシュ
    * qex : 厳密マッチか？
    * x : 部分HTML出力
    * json : JSON出力
    """

    def render_error(messages: List[str], context: Dict | None = None) -> str:
        if context is None:
            context = {}
        return render_template("hoikuen/view_error.html", messages=messages, **context)

    lf = load_hoikuen_csv()

    form = NameSearchForm(request.args)
    info(form.data)

    # フィルター後のデータを取得
    q, h = form.q.data, form.h.data
    if q or h:
        # 検索クエリを構築
        if q:
            qex = form.qex.data
            expr = pl.col("名称").eq(q) if qex else pl.col("名称").str.contains(q)
            lf = lf.filter(expr)
        if h:
            # hashbyte = xx58_hashstr_to_hashbyte(h)
            # NOQA: This's fu-king inefficient. 元データにハッシュ列があるべき
            expr = (
                pl.col("名称").map_elements(lambda txt: xx58_str_to_hashstr(txt)).eq(h)
            )
            lf = lf.filter(expr)
    else:
        # エラー: クエリなし
        query = q or h
        render_error(["クエリを指定してください"])

    is_json = form.json.data
    if is_json:
        df = lf.with_columns(pl.col(pl.Time).cast(pl.String)).collect()
        if df.height == 0:
            return "{}"
        item = df.row(0, named=True)
        data = json_formatter.format_dict(3, item).value
        return data

    df = lf.with_columns(
        pl.col("0歳児", "1歳児", "2歳児", "3歳児", "4歳児", "5歳児").fill_null("-")
    ).collect()

    if df.height == 0:
        # エラー: 0 件マッチ
        query = q or h
        render_error([f"「{query}」に一致する情報が見つかりません"])
    item = df.row(0, named=True)
    context = {
        "row": item,
        "xx58_str_to_hashstr": xx58_str_to_hashstr,
        "is_enrollable": is_enrollable,
        "to_hhmm": time_to_HHMM_ja,
        "to_url": to_url,
    }

    x = form.x.data
    return render_template(
        "hoikuen/view.html" if x else "hoikuen/view_full.html", **context
    )


def fn_hoikuen_list() -> str:
    """
    /view : 保育園一覧

    エントリ抽出ロジックは「名称文字列で検索」
    * q : 検索文字列
    * qex : 厳密マッチか？
    * x : 部分HTML出力
    * json : JSON出力
    """
    lf = load_hoikuen_csv()

    form = NameSearchForm(request.args)
    # app.logger.info(f"form: {form.to_dict()}")
    info(form.data)

    # フィルター後のデータを取得
    q = form.q.data
    if q:
        qex = form.qex.data
        expr = pl.col("名称").eq(q) if qex else pl.col("名称").str.contains(q)
        lf = lf.filter(expr)

    is_json = form.json.data
    if is_json:
        df = lf.with_columns(pl.col(pl.Time).cast(pl.String)).collect()
        data = json_formatter.format_dict(3, df.to_dict(as_series=False)).value
        return data

    context = {
        "df": lf.collect(),
        "shorten_address": shorten_address,
    }
    x = form.x.data
    return render_template(
        "hoikuen/list.html" if x else "hoikuen/list_full.html", **context
    )
