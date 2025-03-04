import time
import json
from decimal import Decimal
from typing import Dict, Any
from pathlib import Path
import uuid

from sqlalchemy import text, create_engine
import streamlit as st
import boto3
import pandas as pd


def get_local_connection():
    db_path = Path(".streamlit/db.db").absolute()
    db_path.parent.mkdir(exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}")
    with engine.connect() as conn:
        lockout_table_sql = """
        CREATE TABLE IF NOT EXISTS lockouts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 1,
            last_attempt INTEGER NOT NULL,
            UNIQUE(ip)
        );
        """
        try:
            conn.execute(text(lockout_table_sql))
        except Exception as e:
            if "already exists" not in str(e):
                raise e
        conn.commit()
    return st.connection("db", type="sql", url=f"sqlite:///{db_path}")


class DynamoDBConnector:
    """AWS DynamoDB connector for both prices and ingredients data"""

    # This setup with DynamoDB is hypothetically more expensive, but we're moving so little data that we can easily stay in free tier forever. Also it's like 10x faster than Lambdas.
    # In any case, it's good to maintain this interface where the PriceHistoryConnector can add_price or get all_prices as a df, and then if the backend changes to the Lambda solution none of the logic outside of this file has to change.

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

    # Price-related methods
    def put_price(
        self,
        ingredient_name: str,
        ingredient_id: str,
        price: float,
        unit: str,
        quantity: float,
    ) -> Dict[str, Any]:
        """Add a new price entry"""

        timestamp = int(time.time())
        item = {
            "id": f"{timestamp}_{ingredient_name.replace(' ', '_')}",
            "ingredient_name": ingredient_name,
            "ingredient_id": ingredient_id,
            "price": Decimal(str(price)),
            "unit": unit,
            "quantity": Decimal(str(quantity)),
            "timestamp": timestamp,
        }
        return self.prices.put_item(Item=item)

    def get_all_prices(self) -> pd.DataFrame:
        """Get all price entries as DataFrame"""
        return self._get_all_items_as_df(self.prices)

    # Ingredient-related methods
    def put_ingredient(self, name: str) -> Dict[str, Any]:
        """Create a brand new ingredient with new ID"""
        timestamp = int(time.time())
        ingredient_id = str(uuid.uuid4())[:12]

        item = {
            "id": ingredient_id,
            "name": name,
            "timestamp": timestamp,
        }

        self.ingredients.put_item(Item=item)
        return item

    def update_ingredient(
        self,
        ingredient_id: str,
        name: str,
    ) -> Dict[str, Any]:
        """Update an existing ingredient (creates new entry with same ID)"""
        timestamp = int(time.time())

        item = {
            "id": ingredient_id,
            "name": name,
            "timestamp": timestamp,
        }

        self.ingredients.put_item(Item=item)
        return item

    def get_all_ingredients(self) -> pd.DataFrame:
        return self._get_all_items_as_df(self.ingredients)

    # Helper method
    def _get_all_items_as_df(self, table) -> pd.DataFrame:
        """Generic method to get all items from a table as DataFrame"""
        response = table.scan()
        items = response.get("Items", [])
        # Handle pagination
        while "LastEvaluatedKey" in response:
            response = table.scan(ExclusiveStartKey=response["LastEvaluatedKey"])
            items.extend(response.get("Items", []))

        if not items:
            return pd.DataFrame()

        # Convert Decimal to float for DataFrame
        def decimal_default(obj):
            if isinstance(obj, Decimal):
                return float(obj)
            raise TypeError

        # Convert to DataFrame
        items_json = json.loads(json.dumps(items, default=decimal_default))
        return pd.DataFrame(items_json)


def get_db() -> DynamoDBConnector:
    """Get unified database connector"""
    return DynamoDBConnector()


## shared, improve this


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


def get_new_entries(df, subset) -> pd.DataFrame:
    if df.empty:
        return df
    return df.sort_values("timestamp", ascending=False).drop_duplicates(
        subset=subset,
    )


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
