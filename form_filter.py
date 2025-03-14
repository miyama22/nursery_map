from flask_wtf import FlaskForm  # type: ignore
from wtforms import (
    IntegerRangeField,
    SelectMultipleField,
    BooleanField,
    SubmitField,
    StringField,
    SelectField,
)
from wtforms.validators import DataRequired, Optional
from wtforms.validators import StopValidation, NumberRange
from wtforms import widgets
import datetime
from typing import Dict, List
from itertools import product


class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(html_tag="ol", prefix_label=False)
    option_widget = widgets.CheckboxInput()


class MultiCheckboxAtLeastOne:
    def __init__(self, message=None):
        if not message:
            message = "At least one option must be selected."
        self.message = message

    def __call__(self, form, field):
        if len(field.data) == 0:
            raise StopValidation(self.message)


class QuadNumbersSelectField(SelectField):
    """
    ４つの数字を入力する SelectField
    """

    def to_numbers(self) -> List[int]:
        if self.data is None:
            return [0, 0, 0, 0]
        print("aaa" + self.data)
        numbers = [
            int(x.strip()) for x in self.data.split("/")
        ]  # NOQA: I don't check if len is 4
        return numbers


def get_age_availability() -> Dict[str, str]:
    return {
        "0": "0歳児",
        "1": "1歳児",
        "2": "2歳児",
        "3": "3歳児",
        "4": "4歳児",
        "5": "5歳児",
    }


def get_nursery_type() -> Dict[str, str]:
    return {
        "1": "区立保育園",
        "2": "区立幼保一元化施設",
        "3": "私立保育園",
        "4": "認定こども園",
        "5": "小規模保育施設",
        "6": "区立保育室",
    }


class FilterForm(FlaskForm):
    nursery_name = StringField("名称", validators=[Optional()])
    address = StringField("住所", validators=[Optional()])
    type = MultiCheckboxField(
        "種別",
        choices=get_nursery_type().items(),
        default=["1", "2", "3", "4", "5", "6"],
    )
    age_availability = MultiCheckboxField(
        "年齢別空き状況", choices=get_age_availability().items(), default=[]
    )
    saturday = BooleanField("土曜日", default=False)
    sunday = BooleanField("日曜日", default=False)
    start_time = QuadNumbersSelectField(
        "開園時間",
        choices=[(f"07/00/07/{m:02d}", f"07:00 ～ 07:{m:02d}") for m in [0, 15, 30]],
        default="07/00/07/30",
        validators=[DataRequired()],
    )
    end_time = QuadNumbersSelectField(
        "通常保育終了時間",
        choices=[(f"18/{m:02d}/18/30", f"18:{m:02d} ～ 18:30") for m in [0, 15, 30]],
        default="18/00/18/30",
        validators=[DataRequired()],
    )
    extended_end_time = QuadNumbersSelectField(
        "延長保育終了時間",
        choices=[
            (f"{h:02d}/{m:02d}/21/30", f"{h:02d}:{m:02d} ～ 21:30")
            for h, m in product(range(19, 22), range(0, 60, 15))
        ][
            :-1  # "21:45-21:30"を除外
        ],
        default="19/00/21/30",
        validators=[DataRequired()],
    )

    garden = BooleanField("園庭", default=False)
    bicycle_parking = BooleanField("駐輪場", default=False)
    stroller_area = BooleanField("ベビーカー置き場", default=False)
    disability_acceptance = BooleanField("障害児の受け入れ体制", default=False)
    sick_child_care = BooleanField("病児保育事業", default=False)
    bus_stop = BooleanField("バス停", default=False)
    bus_route = BooleanField("バスルート", default=False)
    kindergarten = BooleanField("幼稚園", default=False)
    elementary_school = BooleanField("小学校", default=False)
    school_district = BooleanField("小学校区", default=False)
    capacity_min = IntegerRangeField("最低定員", default=0, validators=[NumberRange(min=0, max=999)] )
    capacity_max = IntegerRangeField("最大定員", default=200, validators=[NumberRange(min=0, max=999)])
    submit = SubmitField("この条件で探す")

    def to_dict(self):
        """Convert to a serializable json"""
        data = dict()
        for field in self:
            key, value = field.name, field.data
            if isinstance(value, datetime.time):
                value = (value.hour, value.minute)
            data.update({key: value})
        return data
