from typing import Dict, Any
from decimal import Decimal
import json
import time

import boto3
import pandas as pd
import streamlit as st


class DynamoDBConnector:
    """AWS DynamoDB connector for both prices and ingredients data"""

    def __init__(self) -> None:
        """Initialize DynamoDB client using streamlit secrets"""
        self.dynamodb = boto3.resource(
            "dynamodb",
            aws_access_key_id=st.secrets.aws.access_key_id,
            aws_secret_access_key=st.secrets.aws.secret_access_key,
            region_name=st.secrets.aws.region,
        )
        self.prices = self.dynamodb.Table("prices")
        self.ingredients = self.dynamodb.Table("ingredients")

    def _get_all_items_as_df(self, table) -> pd.DataFrame:
        """Generic method to get all items from a table as DataFrame"""
        response = table.scan()
        items = response.get("Items", [])
        # Pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))
        if not items:
            return pd.DataFrame()

        def decimal_default(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError

        items_json = json.loads(json.dumps(items, default=decimal_default))
        return pd.DataFrame(items_json)

    def get_all_prices(self) -> pd.DataFrame:
        """Get all price entries as DataFrame"""
        return self._get_all_items_as_df(self.prices)

    def get_all_ingredients(self) -> pd.DataFrame:
        return self._get_all_items_as_df(self.ingredients)


def get_db() -> DynamoDBConnector:
    """Get unified database connector"""
    return DynamoDBConnector()


## shared, improve this


def get_new_entries(df, subset) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_values("timestamp", ascending=False).drop_duplicates(
        subset=subset,
    )


def display_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "timestamp" not in df.columns:
        return df
    display = df.copy()
    display["date"] = pd.to_datetime(display["timestamp"], unit="s", utc=True)
    display["date"] = display["date"].dt.strftime("%Y-%m-%d (UTC)")
    display.drop(
        columns=["timestamp", "id", "ingredient_id"], inplace=True, errors="ignore"
    )
    st.dataframe(display, use_container_width=True)


available_units = (
    "g",
    "kg",
    "lb",
    "oz",
    "ml",
    "l",
    "cup",
    "tbsp",
    "tsp",
    "gal",
    "unit",
)
