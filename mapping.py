from typing import Any, Optional, Tuple, cast

import folium
import folium.plugins
import polars as pl
from branca.element import Figure
from folium import Icon
from folium.template import Template
from folium.utilities import image_to_url, remove_empty

from util import to_url


class DispatcherIcon(Icon):
    """
    Icon that also dispatches a JS event.
    Works as a drop-in replacement of CustomIcon.
    """
    # NOTE:
    # e = {
    #   containerPoint: { x: 141, y: 426 },
    #   latlng: { lat: 35.67221, lng: 139.6671 }, layerPoint: { x: 141, y: 426 },
    #   originalEvent: eventObject, target: iconObject,
    #   ...
    # }
    _template = Template(
        """
        {% macro script(this, kwargs) %}
        let {{ this.get_name() }} = L.icon({{ this.options|tojavascript }});
        {{ this._parent.get_name() }}.setIcon({{ this.get_name() }});
        // let {{this.get_name()}} = L.popup();
        {{this._parent.get_name()}}.on('click', function (e) {
            const lat = e.latlng.lat;
            const lng = e.latlng.lng;
            {{ this._parent.get_name() }}._map.setView(new L.LatLng(lat, lng), 17);
            let load = { detail: { text: '{{this.query}}' }, bubbles: true };
            window.parent.window.dispatchEvent(new CustomEvent('openview', load));
        });
        {% endmacro %}
        """
    )  
    def __init__(
        self,
        query: str,
        icon_image: Any,
        icon_size: Optional[Tuple[int, int]] = None,
        icon_anchor: Optional[Tuple[int, int]] = None,
        shadow_image: Any = None,
        shadow_size: Optional[Tuple[int, int]] = None,
        shadow_anchor: Optional[Tuple[int, int]] = None,
        popup_anchor: Optional[Tuple[int, int]] = None,
    ):
        super(Icon, self).__init__()
        self._name = "DispatcherIcon"
        self.options = remove_empty(
            icon_url=image_to_url(icon_image),
            icon_size=icon_size,
            icon_anchor=icon_anchor,
            shadow_url=shadow_image and image_to_url(shadow_image),
            shadow_size=shadow_size,
            shadow_anchor=shadow_anchor,
            popup_anchor=popup_anchor,
        )
        self.query = query


def nursery_type_to_code(type: str) -> str:
    return {
        "区立保育園": "1",
        "区立幼保一元化施設": "2",
        "私立保育園": "3",
        "認定こども園": "4",
        "小規模保育施設": "5",
        "区立保育室": "6",
    }.get(type, "0")


def make_map(center, zoom_start):
    m = folium.Map(
        location=center,
        control_scale=True,
        zoom_start=zoom_start,
        min_zoom=13,
        min_lat=35.55,
        max_lat=35.8,
        min_lon=139.49,
        max_lon=139.85,
        max_bounds=True,
        zoomSnap=0.5,
        zoomDelta=0.5,
    )
    # Add a CSS link at the end of a map html
    cast(Figure, m.get_root()).html.add_child(folium.CssLink("/asset/css/map.css"))
    return m


def make_nursery_map(df: pl.DataFrame):
    # 初期地図を作成
    shibuya_center = 35.66367, 139.69772  # 渋谷区役所
    nursery_map = make_map(shibuya_center, 14)

    # データが0件の場合はその旨を表示(動作確認用/実際はフロント側で表示)
    if df.height == 0:
        folium.Marker(
            location=shibuya_center,
            popup=folium.Popup(
                "条件に一致する保育園がありません", max_width=300, show=True
            ),
            icon=folium.Icon(color="red"),
        ).add_to(nursery_map)
        return nursery_map

    # マップ表示中央点を調整
    def to_f(floatish: Any) -> float:
        return cast(float, floatish)

    latitude_center = (
        to_f(df.get_column("緯度").max()) + to_f(df.get_column("緯度").min())
    ) / 2
    longitude_center = (
        to_f(df.get_column("経度").max()) + to_f(df.get_column("経度").min())
    ) / 2
    map_center = latitude_center, longitude_center

    # マップのズームレベルを調整
    latitude_diff = to_f(df.get_column("緯度").max()) - to_f(
        df.get_column("緯度").min()
    )
    longitude_diff = to_f(df.get_column("経度").max()) - to_f(
        df.get_column("経度").min()
    )

    if latitude_diff < 0.015 and longitude_diff < 0.019:
        zoom_level = 15
    elif latitude_diff < 0.027 and longitude_diff < 0.04:
        zoom_level = 14.5
    else:
        zoom_level = 14

    nursery_map = make_map(map_center, zoom_level)

    # データフレームからマップに描画
    for nursery_type in df.get_column("種別").unique():
        for row in df.filter(pl.col("種別") == nursery_type).iter_rows(named=True):
            folium.Marker(
                location=(row["緯度"], row["経度"]),
                # マウスオーバー時に名称を表示
                tooltip=folium.Tooltip(
                    text=f"{row['名称']}",
                    sticky=True,
                    style="background-color: white; font-size: 13px; font-weight: bold;",
                ),
                # 保育園種別によってアイコンを変更
                icon=DispatcherIcon(
                    query=f"{row['名称']}",
                    icon_image=to_url(
                        f"/asset/icon/{nursery_type_to_code(nursery_type)}.png"
                    ),
                    icon_size=(50, 50),
                ),
            ).add_to(nursery_map)

    # クロスヘアを表示(実装するかは相談)
    crosshair = to_url("/asset/crosshair.png")

    center_marker_html = f"""
    <div
        style="
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            z-index: 999;  /* 地図よりも前面に表示する */
            pointer-events: none; /* マウスイベントをスルー（地図操作を邪魔しない） */
        "
    >
        <!-- 好きなアイコンを指定 -->
        <img src={crosshair}
             style="width:50px; height:50px;">
    </div>
    """

    cast(Figure, nursery_map.get_root()).html.add_child(
        folium.Element(center_marker_html)
    )

    # Add a fullscreen button
    folium.plugins.Fullscreen(
        position="topright",
        title="拡大する",
        title_cancel="元に戻す",
        force_separate_button=True,
    ).add_to(nursery_map)

    # Add a geocider search
    folium.plugins.Geocoder(
        position="topleft",
        provider_options={
            "geocodingQueryParams": {
                "viewbox": "139.66327,35.69244,139.72876,35.64223",
                "accept-language": "ja",
                "countrycodes": "jp",
                "bounded": "1",
            },
        },
        placeholder="地名・駅名で探す…",
        errorMessage="見つかりませんでした",
        iconLabel="新しく検索しています",
        collapsed=True,
    ).add_to(nursery_map)

    return nursery_map
