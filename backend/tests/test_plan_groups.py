import pytest
from pydantic import ValidationError

from app.main import app
from app.schemas.admin_profiles import AdminPlanGroupCreate, AdminProfileUpdate


def test_plan_group_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/admin/plan-groups" in paths
    assert "/api/admin/plan-groups/{group_key}" in paths
    assert "/api/admin/hostels/{router_id}/plan-groups" in paths
    assert "/api/admin/hostels/{router_id}/plan-groups/{group_id}" in paths


def test_plan_group_input_is_normalized() -> None:
    group = AdminPlanGroupCreate(
        name="  Weekly   bundles  ",
        description="  Best   value for a week.  ",
        display_order=2,
        sort_by_price=True,
        profile_names=[" weekly-basic ", "WEEKLY-BASIC", "weekly-plus"],
    )

    assert group.name == "Weekly bundles"
    assert group.description == "Best value for a week."
    assert group.display_order == 2
    assert group.sort_by_price is True
    assert group.profile_names == ["weekly-basic", "weekly-plus"]


def test_plan_group_position_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        AdminPlanGroupCreate(name="Daily bundles", display_order=-1)


def test_published_zero_price_plan_must_be_promotional() -> None:
    with pytest.raises(ValidationError):
        AdminProfileUpdate(display_name="Free access", amount=0, is_visible=True)

    plan = AdminProfileUpdate(
        display_name="Welcome offer",
        amount=0,
        is_promotional=True,
        is_visible=True,
    )
    assert plan.amount == 0
