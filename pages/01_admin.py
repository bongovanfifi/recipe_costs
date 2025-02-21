import streamlit as st
import json
from sqlalchemy import text
import sys
from pathlib import Path
import datetime as dt
import io

sys.path.append(str(Path(__file__).parent.parent))
from utils import get_connection
import time

import boto3
import datetime as dt


def log_action(conn, action, details):
    """Log an admin action"""
    timestamp = int(dt.datetime.now().timestamp())
    with conn.session as session:
        session.execute(
            text(
                "INSERT INTO logs (date, action, details) VALUES (:date, :action, :details)"
            ),
            {"date": timestamp, "action": action, "details": details},
        )
        session.commit()


def check_admin():
    """Check if user has admin password with persistent rate limiting"""
    if st.session_state.get("admin_authenticated"):
        return True

    # Get client IP
    ip = st.query_params.get("client_ip", ["unknown"])[0]

    # Check lockout status
    with get_connection().session as session:
        lockout = session.execute(
            text("SELECT attempts, last_attempt FROM lockouts WHERE ip = :ip"),
            {"ip": ip},
        ).fetchone()

        current_time = int(dt.datetime.now().timestamp())

        if lockout and lockout.attempts >= 10:
            if current_time - lockout.last_attempt < 300:  # 5 minute lockout
                st.error("Too many attempts. Please wait 5 minutes.")
                time.sleep(2)  # Add delay to prevent rapid refreshing
                return False
            else:
                # Reset attempts after lockout period
                session.execute(
                    text("UPDATE lockouts SET attempts = 0 WHERE ip = :ip"), {"ip": ip}
                )
                session.commit()

    with st.form("admin_login", clear_on_submit=True):
        password = st.text_input("Admin Password", type="password", key="pwd")
        submitted = st.form_submit_button("Login")

        if submitted:

            if password == st.secrets.passwords.admin:
                st.session_state.admin_authenticated = True
                st.rerun()
                return True
            else:
                # Record failed attempt
                with get_connection().session as session:
                    session.execute(
                        text(
                            """
                            INSERT INTO lockouts (ip, attempts, last_attempt) 
                            VALUES (:ip, 1, :time)
                            ON CONFLICT(ip) DO UPDATE SET 
                            attempts = attempts + 1,
                            last_attempt = :time
                        """
                        ),
                        {"ip": ip, "time": current_time},
                    )
                    session.commit()
                st.error("Incorrect password")
                time.sleep(1)
                return False

    return False


if not check_admin():
    st.stop()


st.markdown(
    """
<style>
    .stDataFrame {
        width: 100%;
    }
    .stDataFrame > div {
        width: 100%;
    }
    .stDataFrame [data-testid="stTable"] {
        width: 100%;
    }
    .stDataFrame [data-testid="stTable"] table {
        width: 100%;
    }
    div[data-testid="stHorizontalBlock"] > div:first-child {
        width: 100%;
    }
</style>
""",
    unsafe_allow_html=True,
)


st.title("Ingredient Administration")

conn = get_connection()
ingredients = conn.query("SELECT * FROM ingredients ORDER BY name", ttl=0)


if "ingredient_selector" not in st.session_state:
    st.session_state.ingredient_selector = None

# Export current ingredients
if st.button("Export Ingredients"):
    export_data = json.dumps(ingredients.to_dict("records"), indent=2)
    st.download_button(
        "Download JSON", export_data, "ingredients.json", "application/json"
    )

# Import ingredients
st.subheader("Import Ingredients")
uploaded = st.file_uploader("Upload Ingredients JSON", type="json")
if uploaded and st.button("Import"):
    try:
        data = json.load(uploaded)
        with conn.session as session:
            for ing in data:
                # Skip id to let autoincrement work
                session.execute(
                    text(
                        "INSERT INTO ingredients (name, unit_ok) VALUES (:name, :unit_ok)"
                    ),
                    params={"name": ing["name"], "unit_ok": ing["unit_ok"]},
                )
            session.commit()
            log_action(conn, "import", f"Imported {len(data)} ingredients")
            st.rerun()
        st.success("Ingredients imported!")

    except Exception as e:
        st.error(f"Import failed: {e}")

if ingredients.empty:
    st.error("No ingredients found in database. Please add ingredients.")
    st.stop()

selected = st.selectbox(
    "Select Ingredient", ingredients["name"], key="ingredient_selector", index=0
)

# Edit ingredients
st.subheader("Edit Ingredient")
with st.form("edit_ingredient", clear_on_submit=True):
    new_name = st.text_input("New Name", selected)
    if selected:
        unit_ok = st.checkbox(
            "Allow unit measurement",
            value=ingredients[ingredients["name"] == selected]["unit_ok"].iloc[0],
        )

    col1, col2 = st.columns(2)
    with col1:
        if st.form_submit_button("Update"):
            try:
                with conn.session as session:
                    session.execute(
                        text(
                            """
                            UPDATE ingredients 
                            SET name = :name, unit_ok = :unit_ok 
                            WHERE name = :old_name
                        """
                        ),
                        {
                            "name": new_name,
                            "unit_ok": int(unit_ok),
                            "old_name": selected,
                        },
                    )
                    session.commit()
                    log_action(
                        conn,
                        "update",
                        f"Updated {selected} to {new_name} (unit_ok: {unit_ok})",
                    )
                    # st.rerun()
                st.success(f"Updated {selected} to {new_name}")
            except Exception as e:
                st.error(f"Update failed: {e}")

    with col2:
        if st.form_submit_button("Delete"):
            try:
                with conn.session as session:
                    session.execute(
                        text("DELETE FROM ingredients WHERE name = :name"),
                        {"name": selected},
                    )
                    session.commit()
                    log_action(conn, "delete", f"Deleted {selected}")
                    # st.rerun()
                st.success(f"Deleted {selected}")
            except Exception as e:
                st.error(f"Delete failed: {e}")

# Current ingredients table
st.subheader("Current Ingredients")
ingredients = conn.query("SELECT * FROM ingredients ORDER BY name", ttl=0)
st.dataframe(ingredients)


st.subheader("Database Backup")
if st.button("Backup"):
    try:
        prices_data = conn.query(
            """
            SELECT 
                p.id,
                p.ingredient_id,
                i.name as ingredient_name,
                p.price,
                p.unit,
                p.quantity,
                p.date
            FROM prices p
            JOIN ingredients i ON p.ingredient_id = i.id
            ORDER BY p.date DESC
        """
        )
        parquet_buffer = io.BytesIO()
        prices_data.to_parquet(parquet_buffer)
        parquet_buffer.seek(0)
        backup_filename_parquet = (
            f"prices_backup_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.parquet"
        )
        s3_path_parquet = f"item-costs/backups/{backup_filename_parquet}"
        s3 = boto3.client(
            "s3",
            aws_access_key_id=st.secrets.aws.access_key_id,
            aws_secret_access_key=st.secrets.aws.secret_access_key,
        )
        s3.upload_fileobj(parquet_buffer, st.secrets.aws.bucket_name, s3_path_parquet)
        log_action(conn, "backup", f"Prices backed up to S3 as {s3_path_parquet}")
        st.success(f"Prices backed up successfully as {backup_filename_parquet}")
        backup_filename = f"db_backup_{dt.datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        s3_path = f"item-costs/backups/{backup_filename}"
        with open(".streamlit/db.db", "rb") as db_file:
            s3.upload_fileobj(db_file, st.secrets.aws.bucket_name, s3_path)
        log_action(conn, "backup", f"Database backed up to S3 as {s3_path}")
        st.success(f"Database backed up successfully as {backup_filename}")
    except Exception as e:
        st.error(f"Backup failed: {str(e)}")

st.subheader("Comments")
comments = conn.query(
    """
    SELECT 
        datetime(date, 'unixepoch') as timestamp,
        comment 
    FROM comments 
    ORDER BY date DESC
    LIMIT 50
    """,
    ttl=0,
)
if comments.empty:
    st.info("No comments yet")
else:
    st.dataframe(comments)

# Show logs
st.subheader("Action Logs")
logs = conn.query(
    """
    SELECT datetime(date, 'unixepoch') as timestamp, action, details 
    FROM logs 
    ORDER BY date DESC
    LIMIT 50
""",
    ttl=0,
)
st.dataframe(logs)
