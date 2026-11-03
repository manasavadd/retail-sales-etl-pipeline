"""Unit tests for src/transform.py."""

import pandas as pd
import pytest

from src.transform import clean_sales_data, parse_dates, standardize_names, CATEGORY_MAP, REGION_MAP

TODAY = pd.Timestamp("2025-12-31")


def make_raw(rows):
    cols = ["Order_ID", "Order_Date", "Customer_ID", "Product", "Category", "Quantity", "Unit_Price", "Region"]
    return pd.DataFrame(rows, columns=cols)


def good_row(order_id="ORD-1", **overrides):
    row = {
        "Order_ID": order_id, "Order_Date": "2025-01-15", "Customer_ID": "CUST-0001",
        "Product": "Wireless Mouse", "Category": "Electronics", "Quantity": "2",
        "Unit_Price": "500.00", "Region": "North",
    }
    row.update(overrides)
    return row


def clean(rows):
    df, report = clean_sales_data(make_raw(rows), today=TODAY)
    return df, report


def test_total_sales_is_quantity_times_price():
    df, _ = clean([good_row(Quantity="3", Unit_Price="199.50")])
    assert df.loc[0, "Total_Sales"] == pytest.approx(598.50)


def test_exact_duplicates_are_removed():
    df, report = clean([good_row(), good_row(), good_row("ORD-2")])
    assert len(df) == 2
    assert report["exact_duplicates_removed"] == 1


def test_duplicates_differing_only_in_case_are_removed_after_standardisation():
    df, _ = clean([good_row(Region="north"), good_row(Region="NORTH ")])
    assert len(df) == 1
    assert df.loc[0, "Region"] == "North"


def test_missing_order_id_or_product_rows_are_dropped():
    df, report = clean([good_row(), good_row("", Product="Hoodie"), good_row("ORD-3", Product="")])
    assert list(df["Order_ID"]) == ["ORD-1"]
    assert report["dropped_missing_order_id_or_product"] == 2


def test_missing_customer_and_region_are_filled():
    df, report = clean([good_row(Customer_ID="", Region="")])
    assert df.loc[0, "Customer_ID"] == "UNKNOWN"
    assert df.loc[0, "Region"] == "Unknown"
    assert report["customer_filled_unknown"] == 1


def test_missing_category_is_recovered_from_product():
    df, _ = clean([good_row("ORD-1"), good_row("ORD-2", Category="")])
    assert set(df["Category"]) == {"Electronics"}


def test_missing_price_is_imputed_with_product_median():
    rows = [good_row("ORD-1", Unit_Price="100"), good_row("ORD-2", Unit_Price="300"),
            good_row("ORD-3", Unit_Price="")]
    df, report = clean(rows)
    assert df.loc[df["Order_ID"] == "ORD-3", "Unit_Price"].iloc[0] == pytest.approx(200.0)
    assert report["unit_price_imputed"] == 1


def test_zero_and_negative_prices_are_treated_as_invalid_and_imputed():
    rows = [good_row("ORD-1", Unit_Price="100"), good_row("ORD-2", Unit_Price="-5"),
            good_row("ORD-3", Unit_Price="0")]
    df, _ = clean(rows)
    assert (df["Unit_Price"] == 100).all()


def test_price_is_dropped_when_product_has_no_valid_price():
    df, report = clean([good_row("ORD-1", Unit_Price=""), good_row("ORD-2", Product="Hoodie", Unit_Price="900")])
    assert list(df["Order_ID"]) == ["ORD-2"]
    assert report["dropped_unrecoverable_price"] == 1


@pytest.mark.parametrize("bad_qty", ["", "0", "-3", "two", "N/A", "2.5", "5000"])
def test_invalid_quantities_are_dropped(bad_qty):
    df, report = clean([good_row("ORD-1"), good_row("ORD-2", Quantity=bad_qty)])
    assert list(df["Order_ID"]) == ["ORD-1"]
    assert report["dropped_invalid_quantity"] == 1


def test_invalid_and_future_dates_are_dropped():
    rows = [good_row("ORD-1"), good_row("ORD-2", Order_Date="not a date"),
            good_row("ORD-3", Order_Date="2099-01-01"), good_row("ORD-4", Order_Date="")]
    df, report = clean(rows)
    assert list(df["Order_ID"]) == ["ORD-1"]
    assert report["dropped_invalid_date"] == 3


def test_mixed_date_formats_are_standardised_to_iso():
    rows = [good_row("ORD-1", Order_Date="2025-03-05"), good_row("ORD-2", Order_Date="05/03/2025"),
            good_row("ORD-3", Order_Date="05-Mar-2025"), good_row("ORD-4", Order_Date="Mar 05, 2025")]
    df, _ = clean(rows)
    assert set(df["Order_Date"]) == {"2025-03-05"}


def test_category_and_region_names_are_standardised():
    rows = [good_row("ORD-1", Category=" apparel ", Region="N", Product="Hoodie"),
            good_row("ORD-2", Category="Office  supplies", Region="  south", Product="Stapler")]
    df, _ = clean(rows)
    assert set(df["Category"]) == {"Clothing", "Office Supplies"}
    assert set(df["Region"]) == {"North", "South"}


def test_record_counts_are_reported():
    df, report = clean([good_row(), good_row(), good_row("ORD-2", Quantity="-1")])
    assert report["records_before"] == 3
    assert report["records_after"] == len(df) == 1
    assert report["records_removed_total"] == 2


def test_empty_input_raises():
    with pytest.raises(ValueError):
        clean_sales_data(make_raw([]), today=TODAY)


def test_missing_columns_raise():
    with pytest.raises(ValueError):
        clean_sales_data(pd.DataFrame({"Order_ID": ["1"]}), today=TODAY)


def test_helper_functions():
    names = standardize_names(pd.Series(["GROCERY", None, "toys"]), CATEGORY_MAP)
    assert names.iloc[0] == "Groceries" and pd.isna(names.iloc[1]) and names.iloc[2] == "Toys"
    assert standardize_names(pd.Series(["w"]), REGION_MAP).tolist() == ["West"]
    parsed = parse_dates(pd.Series(["2025-01-02", "garbage"]))
    assert parsed.iloc[0] == pd.Timestamp("2025-01-02") and pd.isna(parsed.iloc[1])
