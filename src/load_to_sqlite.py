"""Load the dunnhumby Complete Journey files into a local SQLite database.

Source: the open `completejourney` package (github.com/bradleyboehmke/completejourney),
which redistributes dunnhumby's "The Complete Journey" (2017 release, 2,469 households).

Usage:  python src/load_to_sqlite.py
Output: data/completejourney.db
"""
from pathlib import Path
import sqlite3
import warnings

import pandas as pd
import pyreadr

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
DB = ROOT / "data" / "completejourney.db"


def read(name: str) -> pd.DataFrame:
    path = next(RAW.glob(f"{name}.rd*"))
    df = next(iter(pyreadr.read_r(str(path)).values()))
    # categoricals/strings -> plain object so SQLite stores them as TEXT
    for c in df.columns:
        if isinstance(df[c].dtype, pd.CategoricalDtype) or pd.api.types.is_string_dtype(df[c]):
            df[c] = df[c].astype(object).where(df[c].notna(), None)
    return df


def main() -> None:
    DB.unlink(missing_ok=True)
    con = sqlite3.connect(DB)

    for name in ["campaign_descriptions", "campaigns", "coupon_redemptions", "coupons",
                 "demographics", "products"]:
        df = read(name)
        df.to_sql(name, con, index=False)
        print(f"{name:24s} {len(df):>10,} rows")

    tx = read("transactions")
    tx["transaction_timestamp"] = tx["transaction_timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    tx.to_sql("transactions", con, index=False, chunksize=200_000)
    print(f"{'transactions':24s} {len(tx):>10,} rows")

    # promotions is 21M store-level rows; collapse to product-week so it stays small
    promo = read("promotions")
    promo["on_display"] = promo["display_location"] != "0"
    promo["in_mailer"] = promo["mailer_location"] != "0"
    pw = (promo.groupby(["product_id", "week"], observed=True)
               .agg(stores=("store_id", "nunique"),
                    display_stores=("on_display", "sum"),
                    mailer_stores=("in_mailer", "sum"))
               .reset_index())
    pw.to_sql("promotions_product_week", con, index=False, chunksize=200_000)
    print(f"{'promotions_product_week':24s} {len(pw):>10,} rows (from {len(promo):,} store rows)")

    cur = con.cursor()
    for stmt in [
        "CREATE INDEX ix_tx_hh ON transactions(household_id)",
        "CREATE INDEX ix_tx_basket ON transactions(basket_id)",
        "CREATE INDEX ix_tx_product ON transactions(product_id)",
        "CREATE INDEX ix_tx_week ON transactions(week)",
        "CREATE INDEX ix_prod ON products(product_id)",
        "CREATE INDEX ix_camp ON campaigns(campaign_id, household_id)",
        "CREATE INDEX ix_pw ON promotions_product_week(product_id, week)",
    ]:
        cur.execute(stmt)
    con.commit()
    con.close()
    print(f"Wrote {DB.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
